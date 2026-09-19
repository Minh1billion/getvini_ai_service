import threading
import time
import uuid
from typing import Optional, Protocol, Tuple


class JobStore(Protocol):
    def create(self, total: int, scanned_scenarios: list) -> Tuple[str, threading.Event]: ...

    def get(self, job_id: str) -> Optional[dict]: ...

    def update(self, job_id: str, **fields) -> bool: ...

    def delete(self, job_id: str) -> bool: ...

    def release(self, job_id: str) -> None: ...


class InMemoryJobStore:
    def __init__(self):
        self._jobs: dict = {}
        self._cancel_events: dict = {}
        self._lock = threading.Lock()

    def create(self, total, scanned_scenarios):
        job_id = uuid.uuid4().hex
        cancel_event = threading.Event()
        with self._lock:
            self._jobs[job_id] = {
                "status": "running",
                "processed": 0,
                "total": total,
                "progress": 0.0,
                "errors": [],
                "scanned_scenarios": scanned_scenarios,
                "created_at": time.time(),
            }
            self._cancel_events[job_id] = cancel_event
        return job_id, cancel_event

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None

    def update(self, job_id, **fields):
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.update(fields)
            return True

    def delete(self, job_id):
        with self._lock:
            cancel_event = self._cancel_events.pop(job_id, None)
            if cancel_event is not None:
                cancel_event.set()
            return self._jobs.pop(job_id, None) is not None

    def release(self, job_id):
        with self._lock:
            self._cancel_events.pop(job_id, None)


_store = InMemoryJobStore()


def get_store() -> JobStore:
    return _store
