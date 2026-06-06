"""Per-request context (client IP + user-agent) for cross-cutting concerns.

Audit logging needs the request's IP/user-agent, but threading the FastAPI
`Request` through every service signature would be invasive. Instead a thin
HTTP middleware (see app.main) stashes these values in ContextVars at the start
of each request; `audit.service.record_audit` reads them.

Starlette runs sync endpoints in a threadpool via anyio, which copies the
current contextvars Context into the worker thread, so values set in the async
middleware are visible to the sync service code that runs the request.
"""
from contextvars import ContextVar

_ip_var: ContextVar[str | None] = ContextVar("request_ip", default=None)
_user_agent_var: ContextVar[str | None] = ContextVar("request_user_agent", default=None)


def set_request_context(*, ip: str | None, user_agent: str | None) -> None:
    _ip_var.set(ip)
    _user_agent_var.set(user_agent)


def get_request_ip() -> str | None:
    return _ip_var.get()


def get_request_user_agent() -> str | None:
    return _user_agent_var.get()
