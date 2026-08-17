"""Regression test: concurrent access to ConnectionSession.executor is safe.

Schema indexing spawns one thread worker each for tables, views and procedures,
and every one of them reaches for ``session.executor`` immediately. When the
lazy init was unsynchronized they each built their own single-thread executor,
so three threads ended up running queries on the same DB-API connection. For
pymysql that desyncs the MySQL wire protocol ("Packet sequence number wrong"),
the schema load fails, and autocomplete silently loses every table.
"""

from __future__ import annotations

import threading

from sqlit.domains.connections.app.session import ConnectionSession
from tests.helpers import ConnectionConfig


class _FakeConnection:
    def close(self) -> None:  # pragma: no cover - not exercised here
        pass


def _make_session() -> ConnectionSession:
    config = ConnectionConfig(name="test", db_type="mysql", server="localhost", database="test")
    return ConnectionSession(connection=_FakeConnection(), provider=None, config=config)


def test_concurrent_executor_access_yields_one_executor() -> None:
    session = _make_session()
    start = threading.Barrier(8)
    seen: list[object] = []
    lock = threading.Lock()

    def grab() -> None:
        start.wait()
        executor = session.executor
        with lock:
            seen.append(executor)

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(seen) == 8
    assert len({id(executor) for executor in seen}) == 1, (
        "every caller must share one executor; separate executors would put "
        "several threads on the same connection"
    )

    session.executor.shutdown(wait=True)
