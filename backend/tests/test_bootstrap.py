import asyncio

from app.core import schema_upgrade
from app.core.schema_upgrade import BASE_SCHEMA, bootstrap_if_empty


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _Raw:
    def __init__(self):
        self.scripts = []

    async def execute(self, script):
        self.scripts.append(script)


class _Conn:
    def __init__(self, raw):
        self._raw = raw

    async def get_raw_connection(self):
        return type("RawWrapper", (), {"driver_connection": self._raw})()


class _Session:
    def __init__(self, repositories_exists):
        self.exists = repositories_exists
        self.raw = _Raw()
        self.sql = []
        self.commits = 0

    async def execute(self, stmt):
        self.sql.append(str(stmt))
        return _Result("repositories" if self.exists else None)

    async def connection(self):
        return _Conn(self.raw)

    async def commit(self):
        self.commits += 1


def test_base_schema_ships_inside_the_backend_package():
    # Render builds from backend/, so the file has to live under it.
    assert BASE_SCHEMA.exists()
    assert BASE_SCHEMA.parent == __import__("pathlib").Path(schema_upgrade.__file__).parent
    sql = BASE_SCHEMA.read_text(encoding="utf-8")
    assert "CREATE TABLE repositories" in sql
    assert "INSERT INTO technology_categories" in sql


def test_empty_database_gets_the_base_schema_once_under_a_lock():
    s = _Session(repositories_exists=False)
    assert asyncio.run(bootstrap_if_empty(s)) is True
    assert "pg_advisory_xact_lock" in s.sql[0]
    assert len(s.raw.scripts) == 1 and "CREATE TABLE repositories" in s.raw.scripts[0]
    assert s.commits == 1


def test_existing_database_is_left_alone():
    s = _Session(repositories_exists=True)
    assert asyncio.run(bootstrap_if_empty(s)) is False
    assert s.raw.scripts == []
