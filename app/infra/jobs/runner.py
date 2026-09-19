import asyncio
import os
import threading
import time

from app.domain.spellcheck.service import check_unit
from app.infra.jobs.store import JobStore


def process_job(store: JobStore, job_id, units, whitelist, lang, cancel_event):
    total = len(units)
    if total == 0:
        store.update(job_id, status="done", finished_at=time.time())
        yield 0, 0
        return

    step = max(1, total // 100)
    processed = 0
    errors = []
    for unit in units:
        if cancel_event.is_set():
            return
        errors.extend(check_unit(unit, whitelist, lang))
        processed += 1
        if processed % step == 0 or processed == total:
            if not store.update(job_id, processed=processed, progress=processed / total):
                return
            yield processed, total

    store.update(job_id, status="done", errors=errors, finished_at=time.time())


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _fail(store, job_id, error):
    store.update(job_id, status="error", error=str(error), finished_at=time.time())


def _run(store, job_id, path, units, whitelist, lang, cancel_event):
    try:
        for _ in process_job(store, job_id, units, whitelist, lang, cancel_event):
            pass
    except Exception as e:
        _fail(store, job_id, e)
    finally:
        store.release(job_id)
        _remove(path)


def start_job(store: JobStore, path, units, scanned_scenarios, whitelist, lang):
    job_id, cancel_event = store.create(len(units), scanned_scenarios)
    threading.Thread(target=_run, args=(store, job_id, path, units, whitelist, lang, cancel_event), daemon=True).start()
    return job_id, len(units)


async def stream_job(store: JobStore, path, units, scanned_scenarios, whitelist, lang):
    job_id, cancel_event = store.create(len(units), scanned_scenarios)
    try:
        gen = process_job(store, job_id, units, whitelist, lang, cancel_event)

        def next_item():
            try:
                return next(gen)
            except StopIteration:
                return None

        while True:
            try:
                result = await asyncio.to_thread(next_item)
            except Exception as e:
                _fail(store, job_id, e)
                yield {"job_id": job_id, "error": str(e)}
                break
            if result is None:
                break
            processed, total = result
            yield {"job_id": job_id, "processed": processed, "total": total, "progress": (processed / total) if total else 1.0}
    finally:
        store.release(job_id)
        _remove(path)
