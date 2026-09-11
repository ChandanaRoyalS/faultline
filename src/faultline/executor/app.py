"""The served executor: `POST /execute` for the approval surface T6.3 will build.

Reachable on the deployment's compose network only - Caddy forwards nothing to it, and
`tests/test_deploy.py` says so. A token is the whole request; the response is the audit row.
There is no route that mints, lists, or revokes: minting is the approver's, and the ledger is
read from the database by whoever may read the database.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from faultline.executor.settings import ExecutorSettings


class ExecuteRequest(BaseModel):
    token: str = Field(min_length=1)
    caller: str = Field(default="approval-surface", max_length=120)


def build_app(settings: ExecutorSettings, executor: Any | None = None) -> FastAPI:
    app = FastAPI(title="faultline-execute", docs_url=None, redoc_url=None)

    def _executor() -> Any:
        nonlocal executor
        if executor is None:
            from faultline.executor.cli import build_executor

            executor = build_executor(settings)
        return executor

    @app.get("/healthz")
    def healthz() -> dict[str, Any]:
        return {"status": "ok", "kill_switch": settings.kill_switch}

    @app.post("/execute")
    def execute(request: ExecuteRequest) -> dict[str, Any]:
        record = _executor().execute(request.token, caller=request.caller)
        row: dict[str, Any] = record.as_dict()
        return row

    return app
