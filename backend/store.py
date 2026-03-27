import asyncio
import time

incidents: dict[str, dict] = {}
sse_queues: dict[str, asyncio.Queue] = {}
dedup_index: dict[tuple, str] = {}
dedup_timestamps: dict[str, float] = {}


def create_incident(id: str, state: dict) -> None:
    incidents[id] = {**state, "incident_id": id}
    sse_queues[id] = asyncio.Queue()


def update_incident(id: str, partial: dict) -> None:
    if id in incidents:
        incidents[id].update(partial)


def get_incident(id: str) -> dict | None:
    return incidents.get(id)


def get_all_incidents() -> list[dict]:
    return list(incidents.values())


def check_dedup(service_name: str, error_type: str, window_seconds: int = 300) -> str | None:
    key = (service_name, error_type)
    if key in dedup_index:
        existing_id = dedup_index[key]
        if time.time() - dedup_timestamps.get(existing_id, 0) < window_seconds:
            return existing_id
    return None


def register_dedup(service_name: str, error_type: str, id: str) -> None:
    dedup_index[(service_name, error_type)] = id
    dedup_timestamps[id] = time.time()
