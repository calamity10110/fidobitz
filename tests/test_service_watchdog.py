import pytest
import time
from unittest.mock import patch
from houndmind_ai.safety.service_watchdog import ServiceWatchdogModule

class DummyContext:
    def __init__(self, data=None):
        self._data = data or {}
        self._set_calls = {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._set_calls[key] = value
        self._data[key] = value

def test_service_watchdog_disabled():
    context = DummyContext({
        "config.safety.service_watchdog": {
            "enabled": False
        },
        "settings": {
            "service_watchdog": {
                "enabled": False
            }
        }
    })
    module = ServiceWatchdogModule("watchdog")
    module.tick(context)
    # Should return immediately, so no 'service_watchdog_status' set
    assert "service_watchdog_status" not in context._set_calls

@patch("time.time")
def test_service_watchdog_status_update(mock_time):
    mock_time.return_value = 1000.0
    context = DummyContext({
        "config.safety.service_watchdog": {
            "enabled": True,
            "status_interval_s": 1.0
        },
        "settings": {
            "service_watchdog": {
                "enabled": True,
                "status_interval_s": 1.0
            }
        }
    })
    module = ServiceWatchdogModule("watchdog")
    # Initial status
    module.tick(context)
    assert "service_watchdog_status" in context._set_calls
    assert context._set_calls["service_watchdog_status"]["timestamp"] == 1000.0

    # Tick again without time change -> no update (due to interval)
    context._set_calls.clear()
    module.tick(context)
    assert "service_watchdog_status" not in context._set_calls

    # Tick after interval -> update
    mock_time.return_value = 1001.0
    module.tick(context)
    assert "service_watchdog_status" in context._set_calls

@patch("time.time")
def test_restart_on_error(mock_time):
    mock_time.return_value = 1000.0
    context = DummyContext({
        "config.safety.service_watchdog": {
            "enabled": True,
            "monitor_modules": ["test_module"],
            "restart_on_error": True,
            "restart_on_stale": False,
            "restart_cooldown_s": 5.0,
            "max_restarts": 3
        },
        "settings": {
            "service_watchdog": {
                "enabled": True,
                "monitor_modules": ["test_module"],
                "restart_on_error": True,
                "restart_on_stale": False,
                "restart_cooldown_s": 5.0,
                "max_restarts": 3
            }
        },
        "module_statuses": {
            "test_module": {
                "enabled": True,
                "last_error": "crash!"
            }
        }
    })
    module = ServiceWatchdogModule("watchdog")
    module.tick(context)

    assert "restart_modules" in context._set_calls
    assert "test_module" in context._set_calls["restart_modules"]
    restarts = context._set_calls["service_watchdog_restarts"]
    assert restarts["reasons"]["test_module"] == "error"

    # Test cooldown
    context._set_calls.clear()
    mock_time.return_value = 1002.0 # Less than cooldown 5.0
    # Provide new error to bypass last_error check
    context._data["module_statuses"]["test_module"]["last_error"] = "crash 2!"
    module.tick(context)
    assert "restart_modules" not in context._set_calls

@patch("time.time")
def test_restart_on_stale(mock_time):
    mock_time.return_value = 1000.0
    context = DummyContext({
        "config.safety.service_watchdog": {
            "enabled": True,
            "monitor_modules": ["test_module"],
            "restart_on_error": False,
            "restart_on_stale": True,
            "module_timeout_s": 6.0,
            "restart_cooldown_s": 5.0,
            "max_restarts": 3
        },
        "settings": {
            "service_watchdog": {
                "enabled": True,
                "monitor_modules": ["test_module"],
                "restart_on_error": False,
                "restart_on_stale": True,
                "module_timeout_s": 6.0,
                "restart_cooldown_s": 5.0,
                "max_restarts": 3
            }
        },
        "module_statuses": {
            "test_module": {
                "enabled": True,
                "last_heartbeat_ts": 993.0 # 1000 - 993 = 7 > 6 timeout
            }
        }
    })
    module = ServiceWatchdogModule("watchdog")
    module.tick(context)

    assert "restart_modules" in context._set_calls
    assert "test_module" in context._set_calls["restart_modules"]
    restarts = context._set_calls["service_watchdog_restarts"]
    assert restarts["reasons"]["test_module"] == "stale"

@patch("time.time")
def test_eligible_restart_max_restarts(mock_time):
    mock_time.return_value = 1000.0
    context = DummyContext({
        "config.safety.service_watchdog": {
            "enabled": True,
            "monitor_modules": ["test_module"],
            "restart_on_error": True,
            "restart_on_stale": False,
            "restart_cooldown_s": 0.0, # no cooldown
            "max_restarts": 2
        },
        "settings": {
            "service_watchdog": {
                "enabled": True,
                "monitor_modules": ["test_module"],
                "restart_on_error": True,
                "restart_on_stale": False,
                "restart_cooldown_s": 0.0, # no cooldown
                "max_restarts": 2
            }
        },
        "module_statuses": {
            "test_module": {
                "enabled": True,
                "last_error": "error 1"
            }
        }
    })
    module = ServiceWatchdogModule("watchdog")

    # 1st restart
    module.tick(context)
    assert "restart_modules" in context._set_calls
    context._set_calls.clear()

    # 2nd restart
    context._data["module_statuses"]["test_module"]["last_error"] = "error 2"
    module.tick(context)
    assert "restart_modules" in context._set_calls
    context._set_calls.clear()

    # 3rd restart (should fail due to max_restarts)
    context._data["module_statuses"]["test_module"]["last_error"] = "error 3"
    module.tick(context)
    assert "restart_modules" not in context._set_calls

def test_missing_or_disabled_status():
    context = DummyContext({
        "config.safety.service_watchdog": {
            "enabled": True,
            "monitor_modules": ["mod_missing", "mod_disabled", "mod_ok"],
            "restart_on_error": True,
            "max_restarts": 1
        },
        "settings": {
            "service_watchdog": {
                "enabled": True,
                "monitor_modules": ["mod_missing", "mod_disabled", "mod_ok"],
                "restart_on_error": True,
                "max_restarts": 1
            }
        },
        "module_statuses": {
            "mod_disabled": {
                "enabled": False,
                "last_error": "err"
            },
            "mod_ok": {
                "enabled": True,
                "last_error": "err"
            }
            # mod_missing has no status
        }
    })
    module = ServiceWatchdogModule("watchdog")
    module.tick(context)

    assert "restart_modules" in context._set_calls
    assert "mod_ok" in context._set_calls["restart_modules"]
    assert "mod_missing" not in context._set_calls["restart_modules"]
    assert "mod_disabled" not in context._set_calls["restart_modules"]

def test_reset():
    module = ServiceWatchdogModule("watchdog")
    module._last_restart_ts["mod_a"] = 100.0
    module._restart_counts["mod_a"] = 2
    module._last_error_seen["mod_a"] = "err"

    module._last_restart_ts["mod_b"] = 200.0
    module._restart_counts["mod_b"] = 1
    module._last_error_seen["mod_b"] = "err_b"

    # Reset specific module
    module.reset(["mod_a"])
    assert "mod_a" not in module._last_restart_ts
    assert "mod_b" in module._last_restart_ts

    # Reset all
    module.reset()
    assert not module._last_restart_ts
    assert not module._restart_counts
    assert not module._last_error_seen
