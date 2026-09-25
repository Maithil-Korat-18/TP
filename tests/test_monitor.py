import os
import gc
import tempfile
from unittest.mock import MagicMock
import pytest

from database.db import DatabaseManager
from scraper.base import BaseScraper
from monitor.monitor import SihMonitor, ChangeResult
from notifications import NotificationDispatcher


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



@pytest.fixture
def mock_dispatcher():
    dispatcher = MagicMock(spec=NotificationDispatcher)
    dispatcher.broadcast.return_value = {"EmailNotification": True}
    return dispatcher


@pytest.fixture
def sample_config():
    return {
        "sih": {"url": "https://sih.gov.in/sih2026PS"},
        "problem_statements": [
            {"id": "SIH1234", "title": "Crop Disease Detection", "enabled": True},
            {"id": "SIH5678", "title": "Smart Agriculture", "enabled": True},
        ],
        "monitor": {
            "interval_seconds": 300,
            "max_retries": 3,
        },
        "notification": {
            "cooldown_seconds": 0,
            "email": {"enabled": True},
            "whatsapp": {"enabled": False},
        },
    }


def make_mock_scraper(counts_map):
    """counts_map: dict of ps_id -> count"""
    scraper = MagicMock(spec=BaseScraper)
    mock_data = {}
    for pid, count in counts_map.items():
        mock_data[pid] = {
            "ps_id": pid,
            "title": f"Title for {pid}",
            "current_count": count,
            "max_capacity": 500,
            "raw_count": f"{count}/500",
            "category": "Software",
            "organization": "Test Org",
            "source": "mock",
        }
    scraper.fetch_all.return_value = mock_data
    return scraper


def test_transition_none_to_42_baseline(sample_config, temp_db, mock_dispatcher):
    scraper = make_mock_scraper({"SIH1234": 42})
    monitor = SihMonitor(sample_config, scraper, temp_db, mock_dispatcher)

    res = monitor.check_ps({"id": "SIH1234", "title": "Crop Disease Detection"}, scraper.fetch_all())

    assert res["change_type"] == ChangeResult.BASELINE
    assert res["current_count"] == 42
    assert res["previous_count"] is None
    # No notification on baseline!
    assert not mock_dispatcher.broadcast.called
    # But saved to DB!
    assert temp_db.get_latest_count("SIH1234") == 42


def test_transition_37_to_42_notification(sample_config, temp_db, mock_dispatcher):
    temp_db.save_count("SIH1234", "Crop Disease Detection", 37)

    scraper = make_mock_scraper({"SIH1234": 42})
    monitor = SihMonitor(sample_config, scraper, temp_db, mock_dispatcher)

    res = monitor.check_ps({"id": "SIH1234", "title": "Crop Disease Detection"}, scraper.fetch_all())

    assert res["change_type"] == ChangeResult.INCREASED
    assert res["increase"] == 5
    assert res["previous_count"] == 37
    assert res["current_count"] == 42

    # Notification MUST be broadcasted!
    assert mock_dispatcher.broadcast.called
    assert temp_db.get_latest_count("SIH1234") == 42


def test_transition_42_to_42_no_notification(sample_config, temp_db, mock_dispatcher):
    temp_db.save_count("SIH1234", "Crop Disease Detection", 42)

    scraper = make_mock_scraper({"SIH1234": 42})
    monitor = SihMonitor(sample_config, scraper, temp_db, mock_dispatcher)

    res = monitor.check_ps({"id": "SIH1234", "title": "Crop Disease Detection"}, scraper.fetch_all())

    assert res["change_type"] == ChangeResult.UNCHANGED
    assert res["increase"] == 0
    # Notification must NOT be sent
    assert not mock_dispatcher.broadcast.called


def test_transition_42_to_40_decrease_no_increase_notification(sample_config, temp_db, mock_dispatcher):
    temp_db.save_count("SIH1234", "Crop Disease Detection", 42)

    scraper = make_mock_scraper({"SIH1234": 40})
    monitor = SihMonitor(sample_config, scraper, temp_db, mock_dispatcher)

    res = monitor.check_ps({"id": "SIH1234", "title": "Crop Disease Detection"}, scraper.fetch_all())

    assert res["change_type"] == ChangeResult.DECREASED
    assert res["increase"] == -2
    # Notification must NOT be sent
    assert not mock_dispatcher.broadcast.called
    # Saved count
    assert temp_db.get_latest_count("SIH1234") == 40


def test_transition_42_to_43_notification(sample_config, temp_db, mock_dispatcher):
    temp_db.save_count("SIH1234", "Crop Disease Detection", 42)

    scraper = make_mock_scraper({"SIH1234": 43})
    monitor = SihMonitor(sample_config, scraper, temp_db, mock_dispatcher)

    res = monitor.check_ps({"id": "SIH1234", "title": "Crop Disease Detection"}, scraper.fetch_all())

    assert res["change_type"] == ChangeResult.INCREASED
    assert res["increase"] == 1
    assert mock_dispatcher.broadcast.called


def test_duplicate_prevention_across_repeated_checks(sample_config, temp_db, mock_dispatcher):
    # Initial 37
    temp_db.save_count("SIH1234", "Crop Disease Detection", 37)

    # 1st check: 37 -> 42 triggers 1 alert
    scraper = make_mock_scraper({"SIH1234": 42})
    monitor = SihMonitor(sample_config, scraper, temp_db, mock_dispatcher)
    monitor.check_ps({"id": "SIH1234", "title": "Crop Disease Detection"}, scraper.fetch_all())
    assert mock_dispatcher.broadcast.call_count == 1

    # Next 10 checks returning 42 must NOT trigger any new alerts
    for _ in range(10):
        monitor.check_ps({"id": "SIH1234", "title": "Crop Disease Detection"}, scraper.fetch_all())
    assert mock_dispatcher.broadcast.call_count == 1

    # 12th check: 42 -> 43 triggers exactly 1 new alert
    scraper_new = make_mock_scraper({"SIH1234": 43})
    monitor.check_ps({"id": "SIH1234", "title": "Crop Disease Detection"}, scraper_new.fetch_all())
    assert mock_dispatcher.broadcast.call_count == 2


def test_multi_ps_monitoring(sample_config, temp_db, mock_dispatcher):
    temp_db.save_count("SIH1234", "Crop Disease Detection", 37)
    temp_db.save_count("SIH5678", "Smart Agriculture", 91)

    scraper = make_mock_scraper({"SIH1234": 42, "SIH5678": 94})
    monitor = SihMonitor(sample_config, scraper, temp_db, mock_dispatcher)

    results = monitor.run_check_cycle()
    assert len(results) == 2
    # Both increased, so broadcast called twice
    assert mock_dispatcher.broadcast.call_count == 2


def test_api_unavailable_retry_failure(sample_config, temp_db, mock_dispatcher):
    scraper = MagicMock(spec=BaseScraper)
    scraper.fetch_all.side_effect = ConnectionError("SIH Portal Down")

    monitor = SihMonitor(sample_config, scraper, temp_db, mock_dispatcher)
    monitor.RETRY_DELAYS = [0, 0, 0]  # Instant for unit tests
    results = monitor.run_check_cycle()
    assert results == []


def test_notification_failure_does_not_crash_cycle(sample_config, temp_db):
    failing_dispatcher = MagicMock(spec=NotificationDispatcher)
    failing_dispatcher.broadcast.side_effect = RuntimeError("SMTP Socket Connection Timeout")

    # Monitor single PS for this test
    config = dict(sample_config)
    config["problem_statements"] = [{"id": "SIH1234", "title": "Crop Disease Detection", "enabled": True}]

    temp_db.save_count("SIH1234", "Crop Disease Detection", 37)
    scraper = make_mock_scraper({"SIH1234": 42})

    monitor = SihMonitor(config, scraper, temp_db, failing_dispatcher)
    results = monitor.run_check_cycle()

    assert len(results) == 1
    assert results[0]["current_count"] == 42
    # Saved despite notification failure
    assert temp_db.get_latest_count("SIH1234") == 42

