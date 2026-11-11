"""JSON REST access to switch APIs (thin layer over httpx, with a test double)."""

from typing import Any, Protocol

import httpx


class HttpError(Exception):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class Http(Protocol):
    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        read_timeout: float | None = None,
    ) -> Any:
        """Send a request relative to the base URL; returns parsed JSON, text or None.

        ``read_timeout`` overrides the client default for slow calls (e.g. saving the config).
        """
        ...

    async def close(self) -> None: ...


class HttpxClient:
    def __init__(self, base_url: str, *, verify_tls: bool, timeout: float = 30) -> None:
        self._client = httpx.AsyncClient(base_url=base_url, verify=verify_tls, timeout=timeout)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        read_timeout: float | None = None,
    ) -> Any:
        try:
            response = await self._client.request(
                method,
                path,
                json=json,
                data=data,
                headers=headers,
                timeout=read_timeout if read_timeout is not None else httpx.USE_CLIENT_DEFAULT,
            )
        except httpx.HTTPError as exc:
            # timeouts have no message of their own: name the error type
            raise HttpError(f"{method} {path}: {type(exc).__name__} {exc}".rstrip()) from exc
        if response.status_code >= 400:
            raise HttpError(
                f"{method} {path}: HTTP {response.status_code} {response.text[:300]}",
                response.status_code,
            )
        if not response.content:
            return None
        if "json" in response.headers.get("content-type", ""):
            return response.json()
        return response.text

    async def close(self) -> None:
        await self._client.aclose()


class FakeHttp:
    """Records calls; answers from ``responses[(method, path)]`` (default: None)."""

    def __init__(self, responses: dict[tuple[str, str], Any] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, str, Any]] = []
        self.closed = False

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        read_timeout: float | None = None,
    ) -> Any:
        self.calls.append((method, path, json if json is not None else data))
        return self.responses.get((method, path))

    async def close(self) -> None:
        self.closed = True
