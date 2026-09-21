import threading
import time
import uuid
from typing import Optional

_JOB_TTL_SECONDS = 3600


class QcJobStore:
    def __init__(self):
        self._jobs: dict = {}
        self._lock = threading.Lock()

    def _purge_expired(self):
        cutoff = time.time() - _JOB_TTL_SECONDS
        expired = [jid for jid, job in self._jobs.items() if job.get("created_at", 0) < cutoff]
        for jid in expired:
            self._jobs.pop(jid, None)

    def create(self, total: int):
        job_id = uuid.uuid4().hex
        with self._lock:
            self._purge_expired()
            self._jobs[job_id] = {
                "status": "queued",
                "total": total,
                "content_blocks": None,
                "scanned_scenarios": None,
                "mismatch_report": None,
                "models": None,
                "error": None,
                "created_at": time.time(),
            }
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None

    def update(self, job_id: str, **fields) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.update(fields)
            return True


_store = QcJobStore()


def get_qc_store() -> QcJobStore:
    return _store
