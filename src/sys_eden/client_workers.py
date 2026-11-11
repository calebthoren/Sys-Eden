"""Bounded client RPC workers that do not own Core or keep a closed CLI alive."""

from collections.abc import Callable
from concurrent.futures import Future
from threading import RLock, Semaphore, Thread
from typing import Any


class ClientRequestWorkers:
    """Core keeps accepted work; exiting a client drops its daemon RPC waiters."""

    def __init__(self, max_workers: int = 4) -> None:
        self._slots = Semaphore(max_workers)
        self._lock = RLock()
        self._closed = False
        self._requests: dict[Future[Any], Thread] = {}

    def submit(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
        future: Future[Any] = Future()

        def run() -> None:
            try:
                with self._slots:
                    if not future.set_running_or_notify_cancel():
                        return
                    try:
                        result = function(*args, **kwargs)
                    except BaseException as error:  # noqa: BLE001 - transfer worker failures to its Future
                        future.set_exception(error)
                    else:
                        future.set_result(result)
            finally:
                with self._lock:
                    self._requests.pop(future, None)

        thread = Thread(target=run, name="eden-cli-request", daemon=True)
        with self._lock:
            if self._closed:
                raise RuntimeError("The CLI request workers are closed")
            self._requests[future] = thread
            thread.start()
        return future

    def shutdown(self, *, wait: bool = True, cancel_futures: bool = False) -> None:
        with self._lock:
            self._closed = True
            requests = list(self._requests.items())
            if cancel_futures:
                for future, _ in requests:
                    future.cancel()
        if wait:
            for _, thread in requests:
                thread.join()
