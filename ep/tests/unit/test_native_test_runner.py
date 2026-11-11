import psutil

from scripts import verify_native_isolated


def test_native_memory_observer_tolerates_process_exit_race(monkeypatch):
    def vanished(pid):
        raise psutil.NoSuchProcess(pid)

    monkeypatch.setattr(verify_native_isolated.psutil, "Process", vanished)
    assert verify_native_isolated.process_tree(123) == []
