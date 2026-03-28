from unittest.mock import patch
from houndmind_ai.safety.service_watchdog import ServiceWatchdogModule


class DummyContext:
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value


def test_service_watchdog_module_initialization():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    assert module.status.enabled is True


def test_tick_disabled():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    ctx = DummyContext({"settings": {"service_watchdog": {"enabled": False}}})

    with patch("time.time", return_value=100.0):
        module.tick(ctx)

    # Should not set any status or restart anything
    assert "service_watchdog_status" not in ctx.data
    assert "restart_modules" not in ctx.data


def test_tick_status_update():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    ctx = DummyContext(
        {"settings": {"service_watchdog": {"enabled": True, "status_interval_s": 1.0}}}
    )

    with patch("time.time", return_value=100.0):
        module.tick(ctx)

    assert "service_watchdog_status" in ctx.data
    status = ctx.data["service_watchdog_status"]
    assert status["timestamp"] == 100.0
    assert status["restart_counts"] == {}

    # Tick again within the interval, shouldn't update the timestamp
    with patch("time.time", return_value=100.5):
        module.tick(ctx)

    assert ctx.data["service_watchdog_status"]["timestamp"] == 100.0

    # Tick again after the interval, should update
    with patch("time.time", return_value=101.5):
        module.tick(ctx)

    assert ctx.data["service_watchdog_status"]["timestamp"] == 101.5


def test_tick_restart_on_error():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    ctx = DummyContext(
        {
            "settings": {
                "service_watchdog": {
                    "enabled": True,
                    "restart_on_error": True,
                    "restart_on_stale": False,
                    "cooldown": 0.0,
                }
            },
            "module_names": ["failing_module"],
            "module_statuses": {
                "failing_module": {"enabled": True, "last_error": "Some error"}
            },
        }
    )

    with patch("time.time", return_value=100.0):
        module.tick(ctx)

    assert "restart_modules" in ctx.data
    assert ctx.data["restart_modules"] == ["failing_module"]
    assert ctx.data["service_watchdog_restarts"]["reasons"]["failing_module"] == "error"
    assert module._last_error_seen["failing_module"] == "Some error"
    assert module._restart_counts["failing_module"] == 1


def test_tick_no_restart_same_error():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    module._last_error_seen["failing_module"] = "Some error"

    ctx = DummyContext(
        {
            "settings": {
                "service_watchdog": {
                    "enabled": True,
                    "restart_on_error": True,
                    "restart_on_stale": False,
                    "cooldown": 0.0,
                }
            },
            "module_names": ["failing_module"],
            "module_statuses": {
                "failing_module": {"enabled": True, "last_error": "Some error"}
            },
        }
    )

    with patch("time.time", return_value=100.0):
        module.tick(ctx)

    assert "restart_modules" not in ctx.data


def test_tick_restart_on_stale():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    ctx = DummyContext(
        {
            "settings": {
                "service_watchdog": {
                    "enabled": True,
                    "restart_on_error": False,
                    "restart_on_stale": True,
                    "module_timeout_s": 5.0,
                    "cooldown": 0.0,
                }
            },
            "module_names": ["stale_module"],
            "module_statuses": {
                "stale_module": {"enabled": True, "last_heartbeat_ts": 90.0}
            },
        }
    )

    # 100.0 - 90.0 = 10.0 > 5.0 (module_timeout_s)
    with patch("time.time", return_value=100.0):
        module.tick(ctx)

    assert "restart_modules" in ctx.data
    assert ctx.data["restart_modules"] == ["stale_module"]
    assert ctx.data["service_watchdog_restarts"]["reasons"]["stale_module"] == "stale"
    assert module._restart_counts["stale_module"] == 1


def test_tick_restart_cooldown():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    ctx = DummyContext(
        {
            "settings": {
                "service_watchdog": {
                    "enabled": True,
                    "restart_on_error": True,
                    "restart_on_stale": False,
                    "restart_cooldown_s": 5.0,
                }
            },
            "module_names": ["failing_module"],
            "module_statuses": {
                "failing_module": {"enabled": True, "last_error": "Error 1"}
            },
        }
    )

    # First tick requests restart
    with patch("time.time", return_value=100.0):
        module.tick(ctx)

    assert ctx.data.get("restart_modules") == ["failing_module"]
    assert module._restart_counts["failing_module"] == 1

    # Clear data for next tick
    del ctx.data["restart_modules"]

    # Simulate new error but within cooldown (100.0 + 3.0 < 100.0 + 5.0)
    ctx.data["module_statuses"]["failing_module"]["last_error"] = "Error 2"
    with patch("time.time", return_value=103.0):
        module.tick(ctx)

    assert "restart_modules" not in ctx.data
    assert module._restart_counts["failing_module"] == 1

    # Simulate new error after cooldown (100.0 + 6.0 > 100.0 + 5.0)
    ctx.data["module_statuses"]["failing_module"]["last_error"] = "Error 3"
    with patch("time.time", return_value=106.0):
        module.tick(ctx)

    assert ctx.data.get("restart_modules") == ["failing_module"]
    assert module._restart_counts["failing_module"] == 2


def test_tick_max_restarts():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    module._restart_counts["failing_module"] = 3

    ctx = DummyContext(
        {
            "settings": {
                "service_watchdog": {
                    "enabled": True,
                    "restart_on_error": True,
                    "restart_on_stale": False,
                    "restart_cooldown_s": 0.0,
                    "max_restarts": 3,
                }
            },
            "module_names": ["failing_module"],
            "module_statuses": {
                "failing_module": {"enabled": True, "last_error": "New Error"}
            },
        }
    )

    with patch("time.time", return_value=100.0):
        module.tick(ctx)

    assert "restart_modules" not in ctx.data
    assert module._restart_counts["failing_module"] == 3


def test_tick_ignore_modules():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    ctx = DummyContext(
        {
            "settings": {
                "service_watchdog": {
                    "enabled": True,
                    "restart_on_error": True,
                    "ignore_modules": ["ignored_module"],
                }
            },
            "module_names": ["failing_module", "ignored_module"],
            "module_statuses": {
                "failing_module": {"enabled": True, "last_error": "Error 1"},
                "ignored_module": {"enabled": True, "last_error": "Error 2"},
            },
        }
    )

    with patch("time.time", return_value=100.0):
        module.tick(ctx)

    assert "restart_modules" in ctx.data
    assert ctx.data["restart_modules"] == ["failing_module"]
    assert "ignored_module" not in module._restart_counts


def test_reset_method():
    module = ServiceWatchdogModule("watchdog", enabled=True)
    module._last_restart_ts["module_a"] = 100.0
    module._restart_counts["module_a"] = 2
    module._last_error_seen["module_a"] = "err"

    module._last_restart_ts["module_b"] = 100.0
    module._restart_counts["module_b"] = 1
    module._last_error_seen["module_b"] = "err"

    # Reset specific module
    module.reset(["module_a"])
    assert "module_a" not in module._last_restart_ts
    assert "module_a" not in module._restart_counts
    assert "module_a" not in module._last_error_seen

    assert "module_b" in module._last_restart_ts

    # Reset all modules
    module.reset()
    assert not module._last_restart_ts
    assert not module._restart_counts
    assert not module._last_error_seen
