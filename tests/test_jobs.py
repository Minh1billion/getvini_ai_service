import threading

from app.infra.jobs.runner import process_job
from app.infra.jobs.store import InMemoryJobStore

UNITS = [{"location": "L1", "text": "hello wrold", "sheet": None, "scenario": None, "scenarioId": None}] * 3


def test_store_lifecycle():
    store = InMemoryJobStore()
    job_id, event = store.create(3, [])
    assert store.get(job_id)["status"] == "running"
    assert store.update(job_id, processed=1)
    assert store.get(job_id)["processed"] == 1
    assert store.delete(job_id)
    assert event.is_set()
    assert store.get(job_id) is None
    assert not store.update(job_id, processed=2)
    assert not store.delete(job_id)


def test_process_job_done():
    store = InMemoryJobStore()
    job_id, event = store.create(len(UNITS), [])
    list(process_job(store, job_id, UNITS, set(), "en", event))
    job = store.get(job_id)
    assert job["status"] == "done"
    assert [e["token"] for e in job["errors"]] == ["wrold"] * 3


def test_process_job_empty():
    store = InMemoryJobStore()
    job_id, event = store.create(0, [])
    assert list(process_job(store, job_id, [], set(), "en", event)) == [(0, 0)]
    assert store.get(job_id)["status"] == "done"


def test_process_job_cancelled():
    store = InMemoryJobStore()
    job_id, _ = store.create(len(UNITS), [])
    event = threading.Event()
    event.set()
    assert list(process_job(store, job_id, UNITS, set(), "en", event)) == []
    assert store.get(job_id)["status"] == "running"
