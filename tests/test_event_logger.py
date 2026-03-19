import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from houndmind_ai.logging.event_logger import EventLoggerModule, SCHEMA_VERSION


class DummyContext:
    def __init__(self):
        self.data = {}

    def set(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, default)


def test_initialization():
    logger = EventLoggerModule("test_logger")
    assert logger.name == "test_logger"
    assert logger._events == []
    assert logger._last_snapshot == {}
    assert logger._last_log_ts == 0.0


def test_summarize_module_statuses():
    # Test non-dict input
    assert EventLoggerModule._summarize_module_statuses(None) is None
    assert EventLoggerModule._summarize_module_statuses([]) is None
    assert EventLoggerModule._summarize_module_statuses("status") is None

    # Test empty dict
    assert EventLoggerModule._summarize_module_statuses({}) == {
        "enabled": 0,
        "disabled": 0,
        "errors": {},
    }

    # Test various statuses
    statuses = {
        "module1": {"enabled": True},
        "module2": {"enabled": False, "last_error": "Some error"},
        "module3": {"enabled": True, "last_error": "Warning-like error"},
        "invalid": "not a dict",
    }
    summary = EventLoggerModule._summarize_module_statuses(statuses)
    assert summary == {
        "enabled": 2,
        "disabled": 1,
        "errors": {
            "module2": "Some error",
            "module3": "Warning-like error",
        },
    }


def test_count_actions():
    logger = EventLoggerModule("test_logger")
    logger._events = [
        {"navigation_action": "turn_left"},
        {"navigation_action": "turn_right"},
        {"navigation_action": "turn_left"},
        {"navigation_action": None},
        {"other_key": "some_value"},
        {"navigation_action": "move_forward"},
    ]

    counts = logger._count_actions("navigation_action")
    assert counts == {
        "turn_left": 2,
        "turn_right": 1,
        "move_forward": 1,
    }

    # Test key that doesn't exist in any event
    assert logger._count_actions("non_existent") == {}


def test_generate_report():
    logger = EventLoggerModule("test_logger")
    logger._events = [
        {"stuck_recovery": True, "navigation_action": "recovery_spin"},
        {"safety_action": "stop", "navigation_action": "emergency_stop"},
        {"watchdog_action": "reboot", "navigation_action": "none"},
        {"mapping_hint": "obstacle_ahead"},
        {"stuck_recovery": True},
        {"navigation_action": "move_forward"},
    ]

    report = logger._generate_report()
    assert report["schema_version"] == SCHEMA_VERSION
    assert report["total_events"] == 6
    assert report["stuck_events"] == 2
    assert report["safety_events"] == 1
    assert report["watchdog_events"] == 1
    assert report["mapping_hint_events"] == 1
    assert report["navigation_action_counts"] == {
        "recovery_spin": 1,
        "emergency_stop": 1,
        "none": 1,
        "move_forward": 1,
    }
    assert "timestamp" in report


def test_write_jsonl_success_relative_path(tmp_path):
    logger = EventLoggerModule("test_logger")
    event = {"key": "value"}

    # Use tmp_path as the base so we don't write to the actual repository
    base_dir = tmp_path / "base"
    base_dir.mkdir()

    mock_file = tmp_path / "src" / "houndmind_ai" / "logging" / "event_logger.py"
    mock_file.parent.mkdir(parents=True, exist_ok=True)
    mock_file.touch()

    import houndmind_ai.logging.event_logger as event_logger_module

    with patch.object(event_logger_module, "__file__", str(mock_file)):
        settings = {"event_log_path": "logs/test.jsonl"}

        logger._write_jsonl(event, settings)

        expected_file = tmp_path / "logs" / "test.jsonl"
        assert expected_file.exists()

        with open(expected_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == 1
            assert json.loads(lines[0]) == event


def test_write_jsonl_success_absolute_path(tmp_path):
    logger = EventLoggerModule("test_logger")
    event = {"key": "value"}

    # Use an absolute path inside tmp_path
    abs_path = tmp_path / "var" / "log" / "houndmind_events.jsonl"
    settings = {"event_log_path": str(abs_path)}

    logger._write_jsonl(event, settings)

    assert abs_path.exists()
    with open(abs_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
        assert len(lines) == 1
        assert json.loads(lines[0]) == event


def test_write_jsonl_failure():
    logger = EventLoggerModule("test_logger")
    event = {"key": "value"}
    settings = {"event_log_path": "test.jsonl"}

    with patch("pathlib.Path.is_absolute", return_value=True), \
         patch("pathlib.Path.open", side_effect=OSError("Disk full")), \
         patch("pathlib.Path.mkdir"), \
         patch("houndmind_ai.logging.event_logger.logger.warning") as m_warning:
        # Should not raise exception
        logger._write_jsonl(event, settings)
        m_warning.assert_called_once()
        assert "Failed to write event log" in m_warning.call_args[0][0]



def test_tick_disabled():
    logger = EventLoggerModule("test_logger")
    ctx = DummyContext()
    ctx.set("settings", {"logging": {"event_log_enabled": False}})

    with patch.object(logger, "_append_event") as m_append:
        logger.tick(ctx)
        m_append.assert_not_called()


def test_tick_rate_limiting():
    logger = EventLoggerModule("test_logger")
    ctx = DummyContext()
    ctx.set("settings", {"logging": {"event_log_enabled": True, "event_log_interval_s": 1.0}})

    with patch("time.time", side_effect=[100.0, 100.5, 101.1, 101.1, 101.1]), \
         patch.object(logger, "_append_event") as m_append:
        # First tick should log
        logger.tick(ctx)
        assert m_append.call_count == 1
        assert logger._last_log_ts == 100.0

        # Second tick (0.5s later) should not log
        logger.tick(ctx)
        assert m_append.call_count == 1

        # Third tick (1.1s later) should log
        # context must be different for it to proceed past snapshot check
        ctx.set("behavior_action", "moving")
        logger.tick(ctx)
        assert m_append.call_count == 2
        assert logger._last_log_ts == 101.1


def test_tick_duplicate_snapshot():
    logger = EventLoggerModule("test_logger")
    ctx = DummyContext()
    ctx.set("settings", {"logging": {"event_log_enabled": True, "event_log_interval_s": 0.0}})
    ctx.set("behavior_action", "idle")

    with patch.object(logger, "_append_event") as m_append:
        # First tick
        logger.tick(ctx)
        assert m_append.call_count == 1
        assert logger._last_snapshot["behavior_action"] == "idle"

        # Second tick with same context
        logger.tick(ctx)
        assert m_append.call_count == 1

        # Third tick with different context
        ctx.set("behavior_action", "walking")
        logger.tick(ctx)
        assert m_append.call_count == 2
        assert logger._last_snapshot["behavior_action"] == "walking"


def test_tick_data_capture():
    logger = EventLoggerModule("test_logger")
    ctx = DummyContext()
    ctx.set("settings", {"logging": {"event_log_enabled": True, "event_log_interval_s": 0.0}})
    ctx.set("behavior_action", "barking")
    ctx.set("module_statuses", {"brain": {"enabled": True}})

    with patch.object(logger, "_append_event") as m_append:
        logger.tick(ctx)
        m_append.assert_called_once()
        event = m_append.call_args[0][0]
        assert event["type"] == "snapshot"
        assert event["behavior_action"] == "barking"
        assert event["module_status_summary"] == {"enabled": 1, "disabled": 0, "errors": {}}


def test_append_event_trimming():
    logger = EventLoggerModule("test_logger")
    settings = {"event_log_max_entries": 3, "event_log_file_enabled": False}

    logger._append_event({"n": 1}, settings)
    logger._append_event({"n": 2}, settings)
    logger._append_event({"n": 3}, settings)
    assert len(logger._events) == 3

    logger._append_event({"n": 4}, settings)
    assert len(logger._events) == 3
    assert logger._events[0]["n"] == 2
    assert logger._events[2]["n"] == 4


def test_append_event_write_jsonl():
    logger = EventLoggerModule("test_logger")
    settings = {"event_log_file_enabled": True}

    with patch.object(logger, "_write_jsonl") as m_write:
        # Should write because event_log_file_enabled is True
        logger._append_event({"n": 1}, settings)
        m_write.assert_called_once_with({"n": 1}, settings)

        m_write.reset_mock()
        # Should also write when event_log_file_enabled is not specified (defaults to True)
        logger._append_event({"n": 2}, {})
        m_write.assert_called_once_with({"n": 2}, {})


def test_stop():
    logger = EventLoggerModule("test_logger")
    ctx = DummyContext()
    ctx.set("settings", {"logging": {"event_log_file_enabled": True}})
    logger._events = [{"stuck_recovery": True}]

    with patch.object(logger, "_write_jsonl") as m_write:
        logger.stop(ctx)

        report = ctx.get("event_log_report")
        assert report["total_events"] == 1
        assert report["stuck_events"] == 1
        m_write.assert_called_once()
        assert m_write.call_args[0][0]["type"] == "summary"
