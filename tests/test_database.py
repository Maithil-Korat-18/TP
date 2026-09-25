import os
import gc
import tempfile
import pytest

from database.db import DatabaseManager


@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    del db
    gc.collect()
    try:
        if os.path.exists(path):
            os.remove(path)
    except PermissionError:
        pass



def test_init_and_save_count(temp_db):
    row_id = temp_db.save_count("SIH1234", "Crop Disease Detection", 37, source="test")
    assert row_id is not None
    assert row_id > 0

    latest = temp_db.get_latest_count("SIH1234")
    assert latest == 37


def test_count_history(temp_db):
    temp_db.save_count("SIH1234", "Crop Disease Detection", 37, source="test")
    temp_db.save_count("SIH1234", "Crop Disease Detection", 42, source="test")
    temp_db.save_count("SIH1234", "Crop Disease Detection", 45, source="test")

    history = temp_db.get_count_history("SIH1234", limit=5)
    assert len(history) == 3
    # Ordered descending by id
    assert history[0]["count"] == 45
    assert history[1]["count"] == 42
    assert history[2]["count"] == 37


def test_nonexistent_ps(temp_db):
    assert temp_db.get_latest_count("NONEXISTENT") is None
    assert temp_db.get_count_history("NONEXISTENT") == []
    assert temp_db.get_last_notification("NONEXISTENT") is None


def test_notification_logging_and_cooldown(temp_db):
    assert not temp_db.is_in_cooldown("SIH1234", cooldown_seconds=60)

    temp_db.record_notification(
        ps_id="SIH1234",
        previous_count=37,
        new_count=42,
        channels="email,whatsapp",
        status="sent"
    )

    last = temp_db.get_last_notification("SIH1234")
    assert last is not None
    assert last["previous_count"] == 37
    assert last["new_count"] == 42
    assert last["increase"] == 5
    assert last["channels"] == "email,whatsapp"

    # Immediately after alert, it should be in cooldown
    assert temp_db.is_in_cooldown("SIH1234", cooldown_seconds=60)
    # With 0 second cooldown, should not be in cooldown
    assert not temp_db.is_in_cooldown("SIH1234", cooldown_seconds=0)


def test_summary_query(temp_db):
    temp_db.save_count("SIH001", "PS One", 10)
    temp_db.save_count("SIH001", "PS One", 15)
    temp_db.save_count("SIH002", "PS Two", 50)

    summary = temp_db.get_all_monitored_summary()
    assert len(summary) == 2
    
    ps_map = {r["ps_id"]: r for r in summary}
    assert ps_map["SIH001"]["latest_count"] == 15
    assert ps_map["SIH001"]["total_checks"] == 2
    assert ps_map["SIH002"]["latest_count"] == 50
    assert ps_map["SIH002"]["total_checks"] == 1
