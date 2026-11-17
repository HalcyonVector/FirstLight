import asyncio

from app.core.schema_upgrade import LOCK_DOWN, lock_down_public_tables


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _Session:
    def __init__(self, fail=False, still_open=0):
        self.fail, self.still_open, self.rolled_back, self.sql = fail, still_open, False, []

    async def execute(self, stmt):
        self.sql.append(str(stmt))
        if self.fail and "DO $$" in str(stmt):
            raise RuntimeError("permission denied")
        return _Result(self.still_open)

    async def commit(self):
        pass

    async def rollback(self):
        self.rolled_back = True


def test_lockdown_only_touches_tables_this_role_owns():
    assert "ENABLE ROW LEVEL SECURITY" in LOCK_DOWN
    assert "= current_user" in LOCK_DOWN
    assert "FORCE" not in LOCK_DOWN  # owners must keep bypassing RLS


def test_lockdown_reports_open_tables():
    assert asyncio.run(lock_down_public_tables(_Session(still_open=0))) == 0
    assert asyncio.run(lock_down_public_tables(_Session(still_open=2))) == 2


def test_lockdown_failure_never_raises():
    s = _Session(fail=True)
    assert asyncio.run(lock_down_public_tables(s)) == -1
    assert s.rolled_back
