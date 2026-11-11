"""Separate normal-user Core host process for local CLI clients."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from multiprocessing.connection import Listener
from pathlib import Path
from threading import Event, Thread

from sys_eden.config import load_settings
from sys_eden.core_application import CoreApplication
from sys_eden.core_rpc import (
    ByteConnection,
    CoreRpcDispatcher,
    RpcRequest,
    _receive,
    _send,
    read_core_authkey,
    rpc_endpoint,
)


def run() -> int:
    settings = load_settings()
    address, family = rpc_endpoint(settings)
    authkey = read_core_authkey(settings)
    if family == "AF_UNIX":
        try:
            Path(address).unlink()
        except FileNotFoundError:
            pass
    application = CoreApplication(settings)
    dispatcher = CoreRpcDispatcher(application)
    listener = Listener(address, family=family, authkey=authkey)
    workers = ThreadPoolExecutor(max_workers=8, thread_name_prefix="eden-core-rpc")
    janitor_stop = Event()
    janitor = Thread(
        target=_expire_client_leases,
        args=(application, janitor_stop),
        name="eden-client-lease",
        daemon=True,
    )
    try:
        application.start()
        janitor.start()
        while not dispatcher.stop_requested:
            connection = listener.accept()
            try:
                request = RpcRequest.model_validate_json(_receive(connection))
            except (OSError, EOFError, ValueError):
                connection.close()
                continue
            if request.method == "core.stop":
                # Stop accepting new work and let active request handlers reach their
                # normal safe completion before Core checkpoints and closes storage.
                application.prepare_stop()
                workers.shutdown(wait=True, cancel_futures=True)
                response = dispatcher.dispatch(request)
                try:
                    _send(connection, response.model_dump_json().encode("utf-8"))
                finally:
                    connection.close()
                break
            workers.submit(_handle_connection, dispatcher, request, connection)
    finally:
        janitor_stop.set()
        if janitor.is_alive():
            janitor.join(timeout=5)
        workers.shutdown(wait=True, cancel_futures=True)
        if application.status.state.value == "running":
            application.stop()
        application.close()
        listener.close()
        if family == "AF_UNIX":
            try:
                os.unlink(address)
            except FileNotFoundError:
                pass
    return 0


def _handle_connection(
    dispatcher: CoreRpcDispatcher, request: RpcRequest, connection: ByteConnection
) -> None:
    try:
        response = dispatcher.dispatch(request)
        _send(connection, response.model_dump_json().encode("utf-8"))
    except (OSError, EOFError):
        pass
    finally:
        connection.close()


def _expire_client_leases(application: CoreApplication, stop: Event) -> None:
    while not stop.wait(2):
        application.client_sessions.expire_disconnected()


if __name__ == "__main__":
    raise SystemExit(run())
