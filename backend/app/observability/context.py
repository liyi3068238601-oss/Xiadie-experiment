"""Trace context propagation for requests, tasks and tool runs."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, replace
import secrets
from typing import Iterator


def _id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def new_trace_id() -> str:
    return _id("trc")


def new_span_id() -> str:
    return _id("spn")


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str = ""
    span_id: str = ""
    parent_span_id: str = ""
    request_id: str = ""
    session_id: str = ""
    task_run_id: str = ""
    tool_run_id: str = ""
    plugin_id: str = ""
    model_call_id: str = ""

    def fields(self) -> dict[str, str]:
        return {key: value for key, value in asdict(self).items() if value}


_CONTEXT: ContextVar[TraceContext] = ContextVar("xiadie_trace_context", default=TraceContext())


def current_context() -> TraceContext:
    return _CONTEXT.get()


@contextmanager
def bind_context(**fields: str) -> Iterator[TraceContext]:
    current = current_context()
    clean = {key: str(value) for key, value in fields.items() if value is not None}
    token: Token[TraceContext] = _CONTEXT.set(replace(current, **clean))
    try:
        yield _CONTEXT.get()
    finally:
        _CONTEXT.reset(token)


@contextmanager
def span(**fields: str) -> Iterator[TraceContext]:
    current = current_context()
    trace_id = fields.pop("trace_id", "") or current.trace_id or new_trace_id()
    parent = current.span_id
    with bind_context(
        trace_id=trace_id,
        parent_span_id=parent,
        span_id=new_span_id(),
        **fields,
    ) as child:
        yield child
