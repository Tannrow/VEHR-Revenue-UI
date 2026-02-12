from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class CallCenterEventBus:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._listeners: dict[str, dict[str, asyncio.Queue[dict[str, object]]]] = {}
        self._last_webhook_at: dict[str, datetime] = {}

    async def subscribe(self, organization_id: str) -> tuple[str, asyncio.Queue[dict[str, object]]]:
        listener_id = str(uuid4())
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=100)
        async with self._lock:
            listeners = self._listeners.setdefault(organization_id, {})
            listeners[listener_id] = queue
        return listener_id, queue

    async def unsubscribe(self, organization_id: str, listener_id: str) -> None:
        async with self._lock:
            listeners = self._listeners.get(organization_id)
            if not listeners:
                return
            listeners.pop(listener_id, None)
            if not listeners:
                self._listeners.pop(organization_id, None)

    async def publish(
        self,
        *,
        organization_id: str,
        event: str,
        data: dict[str, object],
        source: str = "api",
    ) -> None:
        payload = {"event": event, "data": data}
        async with self._lock:
            listeners = list(self._listeners.get(organization_id, {}).values())
            if source == "webhook":
                self._last_webhook_at[organization_id] = _now_utc()

        for queue in listeners:
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            queue.put_nowait(payload)

    async def get_last_webhook_at(self, organization_id: str) -> datetime | None:
        async with self._lock:
            return self._last_webhook_at.get(organization_id)


call_center_event_bus = CallCenterEventBus()


async def publish_event(organization_id: str, event_dict: dict[str, object]) -> None:
    event_name = str(event_dict.get("event", "message"))
    data = event_dict.get("data")
    payload = data if isinstance(data, dict) else dict(event_dict)
    source = str(event_dict.get("source", "api"))
    await call_center_event_bus.publish(
        organization_id=organization_id,
        event=event_name,
        data=payload,
        source=source,
    )
