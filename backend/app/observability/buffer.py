"""Bounded in-memory diagnostic event buffer with async subscriptions."""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from threading import RLock
from typing import Any


@dataclass(slots=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, Any]]


class DiagnosticBuffer:
    def __init__(self, max_events: int = 5000, max_bytes: int = 8 * 1024 * 1024) -> None:
        self.max_events = max_events
        self.max_bytes = max_bytes
        self._events: deque[tuple[int, int, dict[str, Any]]] = deque()
        self._bytes = 0
        self._cursor = 0
        self._lock = RLock()
        self._subscribers: dict[int, _Subscriber] = {}
        self._subscriber_seq = 0
        self.dropped = 0

    def append(self, event: dict[str, Any], encoded_size: int) -> dict[str, Any]:
        with self._lock:
            self._cursor += 1
            stored = dict(event, cursor=self._cursor)
            size = max(1, int(encoded_size))
            self._events.append((self._cursor, size, stored))
            self._bytes += size
            while len(self._events) > self.max_events or self._bytes > self.max_bytes:
                _cursor, removed, _event = self._events.popleft()
                self._bytes -= removed
                self.dropped += 1
            subscribers = list(self._subscribers.values())
        for subscriber in subscribers:
            def offer(target=subscriber, item=stored) -> None:
                if target.queue.full():
                    try:
                        target.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                try:
                    target.queue.put_nowait(item)
                except asyncio.QueueFull:
                    pass
            try:
                subscriber.loop.call_soon_threadsafe(offer)
            except RuntimeError:
                pass
        return stored

    def snapshot(self, *, after: int = 0, limit: int = 1000) -> dict[str, Any]:
        bounded = max(1, min(int(limit), 5000))
        with self._lock:
            oldest = self._events[0][0] if self._events else self._cursor + 1
            items = [event for cursor, _size, event in self._events if cursor > after][:bounded]
            return {
                "items": items,
                "oldest_cursor": oldest,
                "latest_cursor": self._cursor,
                "gap": bool(after and after < oldest - 1),
                "dropped": self.dropped,
                "capacity": self.max_events,
            }

    def subscribe(self, max_queue: int = 500) -> tuple[int, asyncio.Queue[dict[str, Any]]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=max_queue)
        with self._lock:
            self._subscriber_seq += 1
            key = self._subscriber_seq
            self._subscribers[key] = _Subscriber(loop=loop, queue=queue)
        return key, queue

    def unsubscribe(self, key: int) -> None:
        with self._lock:
            self._subscribers.pop(key, None)


BUFFER = DiagnosticBuffer()
