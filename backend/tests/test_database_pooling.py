from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.database import _pool_options_for_url


def test_postgres_pool_is_bounded_for_supabase_session_mode():
    assert _pool_options_for_url("postgresql://example/db") == {
        "pool_size": 2,
        "max_overflow": 0,
        "pool_timeout": 15,
    }
    assert _pool_options_for_url("sqlite:///local.db") == {}


def test_concurrent_sessions_wait_within_small_pool(tmp_path):
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'bounded-pool.db').as_posix()}",
        connect_args={"check_same_thread": False},
        pool_size=2,
        max_overflow=0,
        pool_timeout=5,
    )
    factory = sessionmaker(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("SELECT 1"))

    lock = Lock()
    pair = Barrier(2)
    active = 0
    maximum_active = 0

    def checked_out(*_args):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)

    def checked_in(*_args):
        nonlocal active
        with lock:
            active -= 1

    event.listen(engine, "checkout", checked_out)
    event.listen(engine, "checkin", checked_in)
    try:
        def query(_):
            with factory() as db:
                result = db.execute(text("SELECT 1")).scalar()
                pair.wait(timeout=5)
                return result

        with ThreadPoolExecutor(max_workers=8) as workers:
            assert list(workers.map(query, range(8))) == [1] * 8
        assert maximum_active <= 2
        assert engine.pool.checkedout() == 0
    finally:
        event.remove(engine, "checkout", checked_out)
        event.remove(engine, "checkin", checked_in)
        engine.dispose()
