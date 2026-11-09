"""Background worker: polls switches and runs scheduled jobs.

cesma-worker            (or: python -m app.jobs.worker)
"""

import asyncio
import logging
import signal
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.crypto import SecretBox
from app.core.db import Database, utcnow
from app.models import Job, PollTask
from app.services import jobs as queued_jobs
from app.services.context import Runtime
from app.services.polling import (
    DriverFactory,
    driver_factory_for,
    due_tasks,
    poll_device,
)

log = logging.getLogger("cesma.worker")

START_DELAY = timedelta(seconds=30)

JobFunc = Callable[[AsyncSession], Awaitable[None]]


@dataclass
class ScheduledJob:
    """A maintenance job: every ``every``, daily at ``at`` (local time, optional weekday),
    or - with neither - once right after the worker starts."""

    name: str
    func: JobFunc
    every: timedelta | None = None
    at: time | None = None
    weekday: int | None = None  # 0 = Monday
    next_run: datetime | None = field(default=None, init=False)

    def schedule_next(self, now: datetime) -> None:
        if self.every is None and self.at is None:  # one-shot start job
            self.next_run = now if self.next_run is None else None
            return
        if self.every is not None:
            self.next_run = now + self.every
            return
        assert self.at is not None
        local = now.astimezone()
        candidate = local.replace(hour=self.at.hour, minute=self.at.minute, second=0, microsecond=0)
        while candidate <= local or (
            self.weekday is not None and candidate.weekday() != self.weekday
        ):
            candidate += timedelta(days=1)
        self.next_run = candidate


class Worker:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        box: SecretBox,
        driver_factory: DriverFactory,
        jobs: list[ScheduledJob] | None = None,
    ) -> None:
        self.settings = settings
        self.database = database
        self.box = box
        self.driver_factory = driver_factory
        self.jobs = jobs or []
        self._running: set[tuple[int, PollTask]] = set()
        self._tasks: set[asyncio.Task[None]] = set()
        self._job_task: asyncio.Task[None] | None = None
        self.runtime = Runtime(settings, box)

    async def run(self, stop: asyncio.Event) -> None:
        log.info("Worker started (concurrency %d)", self.settings.poll_concurrency)
        async with self.database.sessionmaker() as db:
            await queued_jobs.fail_interrupted(db)
            await db.commit()
        now = utcnow()
        for job in self.jobs:
            job.schedule_next(now)
            if job.every is not None:
                # interval jobs run soon after start (once the first polls are in)
                job.next_run = now + min(job.every, START_DELAY)
        while not stop.is_set():
            try:
                await self._schedule_polls()
                await self._run_due_jobs()
                await self._start_queued_job()
            except Exception:
                log.exception("Worker loop error")
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=2)
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        log.info("Worker stopped")

    async def _schedule_polls(self) -> None:
        free = self.settings.poll_concurrency - len(self._running)
        if free <= 0:
            return
        async with self.database.sessionmaker() as db:
            due = await due_tasks(db, limit=free + len(self._running))
        for key in due:
            if key in self._running or len(self._running) >= self.settings.poll_concurrency:
                continue
            self._running.add(key)
            task = asyncio.create_task(self._poll(*key))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _poll(self, device_id: int, task: PollTask) -> None:
        try:
            async with self.database.sessionmaker() as db:
                await poll_device(
                    db,
                    device_id,
                    task,
                    settings=self.settings,
                    box=self.box,
                    driver_factory=self.driver_factory,
                )
        except Exception:
            log.exception("Poll %s of device %d crashed", task, device_id)
        finally:
            self._running.discard((device_id, task))

    async def _start_queued_job(self) -> None:
        """Queued jobs (VLAN sync, backups, keys) run one at a time next to the polling."""
        if self._job_task is not None and not self._job_task.done():
            return
        async with self.database.sessionmaker() as db:
            job = await queued_jobs.next_pending(db)
        if job is not None:
            self._job_task = asyncio.create_task(self._run_queued(job.id))
            self._tasks.add(self._job_task)
            self._job_task.add_done_callback(self._tasks.discard)

    async def _run_queued(self, job_id: int) -> None:
        async with self.database.sessionmaker() as db:
            job = await db.get(Job, job_id)
            if job is not None:
                log.info("Running job %s #%d", job.kind, job.id)
                await queued_jobs.run_job(db, job, self.runtime)

    async def _run_due_jobs(self) -> None:
        now = utcnow()
        for job in self.jobs:
            if job.next_run is not None and job.next_run <= now:
                job.schedule_next(now)
                log.info("Running job %s", job.name)
                try:
                    async with self.database.sessionmaker() as db:
                        await job.func(db)
                        await db.commit()
                except Exception:
                    log.exception("Job %s failed", job.name)


def build_worker(settings: Settings) -> Worker:
    from app.jobs.schedule import default_jobs

    factory = driver_factory_for(settings)
    box = SecretBox(settings.secret_key.get_secret_value())
    database = Database(settings.database_url)
    return Worker(settings, database, box, factory, default_jobs(settings, box))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    worker = build_worker(get_settings())

    async def run() -> None:
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):  # not available on Windows
                loop.add_signal_handler(sig, stop.set)
        try:
            await worker.run(stop)
        finally:
            await worker.database.dispose()

    with suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
