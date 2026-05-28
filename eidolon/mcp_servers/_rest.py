from __future__ import annotations

from typing import Any

import httpx


class RestError(Exception):
    """Raised when the orchestrator returns a non-2xx response."""

    def __init__(self, status: int, detail: Any) -> None:
        super().__init__(f"http_{status}: {detail}")
        self.status = status
        self.detail = detail


def _decode(resp: httpx.Response) -> Any:
    if not resp.content:
        return None
    ctype = resp.headers.get("content-type", "")
    if "application/json" in ctype:
        return resp.json()
    return resp.text


async def rest_request(
    rest: httpx.AsyncClient,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    resp = await rest.request(method, path, json=json, params=params)
    if resp.status_code >= 400:
        raise RestError(resp.status_code, _decode(resp))
    return _decode(resp)
