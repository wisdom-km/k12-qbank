"""GET /health stays liveness. GET /health/ready checks the database."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.bootstrap.http_app import create_app
from backend.bootstrap.ready import ReadyWindow, database_ready


class _Result:
    def __init__(self, one: tuple[object, ...] | None, many: list[tuple[object, ...]]) -> None:
        self._one = one
        self._many = many

    def fetchone(self) -> tuple[object, ...] | None:
        return self._one

    def fetchall(self) -> list[tuple[object, ...]]:
        return self._many


class _Conn:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def execute(self, sql: str, _params: object = None) -> _Result:
        if "schema_migrations" in sql:
            return _Result(None, self._rows)
        return _Result((1,), [])

    def transaction(self) -> "_Ctx":
        return _Ctx(None)


class _Ctx:
    def __init__(self, value: object) -> None:
        self._value = value

    def __enter__(self) -> object:
        return self._value

    def __exit__(self, *_exc: object) -> bool:
        return False


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    def connection(self) -> _Ctx:
        return _Ctx(self._conn)


class HealthReadyTest(unittest.TestCase):
    def test_live_matches_health_and_memory_ready_is_unavailable(self) -> None:
        app = create_app(seed=False)
        with TestClient(app) as client:
            health = client.get("/health")
            live = client.get("/health/live")
            ready = client.get("/health/ready")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(live.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok"})
        self.assertEqual(live.json(), health.json())
        self.assertEqual(ready.status_code, 503)
        self.assertEqual(ready.json(), {"status": "unavailable"})
        self.assertNotIn("dsn", ready.text)
        self.assertNotIn("set-cookie", {name.lower() for name in ready.headers})

    def test_the_thirty_first_ready_call_is_throttled(self) -> None:
        app = create_app(seed=False)
        with TestClient(app) as client:
            for _ in range(30):
                one = client.get("/health/ready")
                self.assertEqual(one.status_code, 503)
            blocked = client.get("/health/ready")
            health = client.get("/health")
            live = client.get("/health/live")
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["code"], "ip_throttled")
        self.assertEqual(blocked.json()["message"], "ip_throttled")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(live.status_code, 200)
        self.assertEqual(health.json(), {"status": "ok"})

    def test_a_ready_probe_can_report_ok(self) -> None:
        app = create_app(seed=False, openapi=True)
        app.state.ready_probe = lambda: True
        with TestClient(app) as client:
            ready = client.get("/health/ready")
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json(), {"status": "ok"})
        paths = app.openapi()["paths"]
        self.assertIn("/health", paths)
        self.assertIn("/health/live", paths)
        self.assertIn("/health/ready", paths)

    def test_the_window_allows_thirty_then_resets(self) -> None:
        now = [0.0]
        window = ReadyWindow(clock=lambda: now[0])
        for _ in range(30):
            self.assertTrue(window.allow("10.0.0.1"))
        self.assertFalse(window.allow("10.0.0.1"))
        self.assertTrue(window.allow("10.0.0.2"))
        now[0] = 60.0
        self.assertTrue(window.allow("10.0.0.1"))

    def test_database_ready_matches_only_the_shipped_set(self) -> None:
        self.assertFalse(database_ready(object(), Path(".")))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            _ship(root, ["V001", "V002"])
            matched = _Pool(_Conn([("V002",), ("V001",)]))
            self.assertTrue(database_ready(matched, root))
            stale = _Pool(_Conn([("V001",), ("V002",)]))
            self.assertFalse(database_ready(stale, root))
            extra = _Pool(_Conn([("V999",), ("V002",), ("V001",)]))
            self.assertFalse(database_ready(extra, root))
            empty = Path(folder) / "empty"
            empty.mkdir()
            self.assertFalse(database_ready(matched, empty))


def _ship(root: Path, versions: list[str]) -> None:
    folder = root / "backend" / "probe" / "migrations"
    folder.mkdir(parents=True)
    for version in versions:
        (folder / f"{version}__probe.sql").write_text("SELECT 1;\n", encoding="utf-8")
