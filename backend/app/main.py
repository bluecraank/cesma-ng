"""Application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1 import admin, audit, auth, clients, config, devices, inventory, notifications, org
from app.auth.authenticators import Authenticator, build_authenticator
from app.core.config import Settings, get_settings
from app.core.crypto import SecretBox
from app.core.db import Database
from app.core.errors import DomainError

APP_VERSION = version("cesma-ng")


def create_app(
    settings: Settings | None = None, authenticator: Authenticator | None = None
) -> FastAPI:
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        await app.state.database.dispose()

    app = FastAPI(
        title="Cesma NG",
        version=APP_VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.database = Database(settings.database_url)
    app.state.secret_box = SecretBox(settings.secret_key.get_secret_value())
    app.state.authenticator = authenticator or build_authenticator(settings)

    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse({"detail": exc.message}, status_code=exc.status_code)

    v1 = APIRouter(prefix="/api/v1")
    for module in (auth, org, devices, inventory, config, clients, notifications, admin, audit):
        v1.include_router(module.router)

    @v1.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": APP_VERSION}

    app.include_router(v1)
    return app
