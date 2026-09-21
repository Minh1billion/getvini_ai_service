import queue
import threading

from app.core.config import get_settings

_task_queue: "queue.Queue" = queue.Queue()
_started = False
_lock = threading.Lock()


class QcQueueFullError(Exception):
    pass


def _worker_loop():
    while True:
        fn = _task_queue.get()
        try:
            fn()
        finally:
            _task_queue.task_done()


def start_workers():
    global _started
    with _lock:
        if _started:
            return
        settings = get_settings()
        for _ in range(settings.qc_queue_workers):
            threading.Thread(target=_worker_loop, daemon=True).start()
        _started = True


def submit(fn):
    settings = get_settings()
    if _task_queue.qsize() >= settings.qc_queue_max_pending:
        raise QcQueueFullError()
    _task_queue.put(fn)
