import pytest
from unittest.mock import patch
from houndmind_ai.safety.health_monitor import HealthMonitorModule


class DummyContext:
    def __init__(self, settings=None):
        self._store = {}
        if settings is not None:
            self._store["settings"] = settings
        else:
            self._store["settings"] = {
                "performance": {
                    "health_monitor_interval_s": 0.0,  # no interval throttling
                    "health_load_per_core_warn_multiplier": 1.5,
                    "health_temp_warn_c": 70.0,
                    "health_gpu_temp_warn_c": 75.0,
                    "health_mem_used_warn_pct": 85.0,
                    "health_actions": ["throttle_scans", "throttle_vision"],
                    "health_scan_interval_multiplier": 2.0,
                    "health_scan_interval_abs_delta": 1.0,
                    "health_vision_frame_interval_multiplier": 2.0,
                    "health_vision_frame_interval_abs_delta": 0.2,
                },
                "navigation": {
                    "scan_interval_s": 0.5,
                },
                "logging": {
                    "status_log_enabled": False,
                },
                "vision_pi4": {
                    "frame_interval_s": 0.2,
                },
            }

    def get(self, key, default=None):
        return self._store.get(key, default)

    def set(self, key, value):
        self._store[key] = value


@pytest.fixture
def module():
    return HealthMonitorModule("health_monitor")


def test_initialization(module):
    ctx = DummyContext()
    module.start(ctx)
    assert ctx.get("health_degraded") is False
    assert ctx.get("scan_interval_override_s") is None
    assert ctx.get("vision_frame_interval_override_s") is None
    assert ctx.get("health_status_last_log_ts") == 0.0


@patch("houndmind_ai.safety.health_monitor._read_load_1m")
@patch("houndmind_ai.safety.health_monitor._read_cpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_gpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_mem_used_pct")
@patch("os.cpu_count")
def test_healthy_tick(
    mock_cpu_count, mock_mem, mock_gpu, mock_cpu_temp, mock_load, module
):
    # Setup healthy metrics
    mock_cpu_count.return_value = 4
    mock_load.return_value = 2.0  # 2.0 / 4 = 0.5 (< 1.5)
    mock_cpu_temp.return_value = 50.0  # < 70.0
    mock_gpu.return_value = 55.0  # < 75.0
    mock_mem.return_value = 50.0  # < 85.0

    ctx = DummyContext()
    module.start(ctx)
    module.tick(ctx)

    assert ctx.get("health_degraded") is False
    assert ctx.get("scan_interval_override_s") is None
    assert ctx.get("vision_frame_interval_override_s") is None

    status = ctx.get("health_status")
    assert status is not None
    assert status["load_1m"] == 2.0
    assert status["temp_c"] == 50.0
    assert status["gpu_temp_c"] == 55.0
    assert status["mem_used_pct"] == 50.0
    assert status["cpu_cores"] == 4
    assert status["degraded"] is False
    assert status["degraded_reasons"] == []


@patch("houndmind_ai.safety.health_monitor._read_load_1m")
@patch("houndmind_ai.safety.health_monitor._read_cpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_gpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_mem_used_pct")
@patch("os.cpu_count")
def test_degraded_load(
    mock_cpu_count, mock_mem, mock_gpu, mock_cpu_temp, mock_load, module
):
    # Setup degraded load metrics
    mock_cpu_count.return_value = 4
    mock_load.return_value = 8.0  # 8.0 / 4 = 2.0 (>= 1.5)
    mock_cpu_temp.return_value = 50.0
    mock_gpu.return_value = 55.0
    mock_mem.return_value = 50.0

    ctx = DummyContext()
    module.start(ctx)
    module.tick(ctx)

    assert ctx.get("health_degraded") is True

    # scan override: base=0.5, mult=2.0 (1.0), abs=1.0 (1.5). min(1.0, 1.5) = 1.0
    assert ctx.get("scan_interval_override_s") == 1.0
    # vision override: base=0.2, mult=2.0 (0.4), abs=0.2 (0.4). min(0.4, 0.4) = 0.4
    assert ctx.get("vision_frame_interval_override_s") == 0.4

    status = ctx.get("health_status")
    assert status["degraded"] is True
    assert "load" in status["degraded_reasons"]


@patch("houndmind_ai.safety.health_monitor._read_load_1m")
@patch("houndmind_ai.safety.health_monitor._read_cpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_gpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_mem_used_pct")
@patch("os.cpu_count")
def test_degraded_temp(
    mock_cpu_count, mock_mem, mock_gpu, mock_cpu_temp, mock_load, module
):
    # Setup degraded temp metrics
    mock_cpu_count.return_value = 4
    mock_load.return_value = 2.0
    mock_cpu_temp.return_value = 80.0  # >= 70.0
    mock_gpu.return_value = 55.0
    mock_mem.return_value = 50.0

    ctx = DummyContext()
    module.start(ctx)
    module.tick(ctx)

    assert ctx.get("health_degraded") is True

    status = ctx.get("health_status")
    assert status["degraded"] is True
    assert "temp" in status["degraded_reasons"]


@patch("houndmind_ai.safety.health_monitor._read_load_1m")
@patch("houndmind_ai.safety.health_monitor._read_cpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_gpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_mem_used_pct")
@patch("os.cpu_count")
def test_degraded_memory(
    mock_cpu_count, mock_mem, mock_gpu, mock_cpu_temp, mock_load, module
):
    # Setup degraded memory metrics
    mock_cpu_count.return_value = 4
    mock_load.return_value = 2.0
    mock_cpu_temp.return_value = 50.0
    mock_gpu.return_value = 55.0
    mock_mem.return_value = 90.0  # >= 85.0

    ctx = DummyContext()
    module.start(ctx)
    module.tick(ctx)

    assert ctx.get("health_degraded") is True

    status = ctx.get("health_status")
    assert status["degraded"] is True
    assert "memory" in status["degraded_reasons"]


@patch("houndmind_ai.safety.health_monitor._read_load_1m")
@patch("houndmind_ai.safety.health_monitor._read_cpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_gpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_mem_used_pct")
@patch("os.cpu_count")
def test_missing_metrics(
    mock_cpu_count, mock_mem, mock_gpu, mock_cpu_temp, mock_load, module
):
    # Setup missing metrics (None)
    mock_cpu_count.return_value = None  # Should default to 1
    mock_load.return_value = None
    mock_cpu_temp.return_value = None
    mock_gpu.return_value = None
    mock_mem.return_value = None

    ctx = DummyContext()
    module.start(ctx)
    module.tick(ctx)

    assert ctx.get("health_degraded") is False
    assert ctx.get("scan_interval_override_s") is None
    assert ctx.get("vision_frame_interval_override_s") is None

    status = ctx.get("health_status")
    assert status["load_1m"] is None
    assert status["temp_c"] is None
    assert status["gpu_temp_c"] is None
    assert status["mem_used_pct"] is None
    assert status["cpu_cores"] == 1
    assert status["degraded"] is False
    assert status["degraded_reasons"] == []


@patch("houndmind_ai.safety.health_monitor._read_load_1m")
@patch("houndmind_ai.safety.health_monitor._read_cpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_gpu_temp_c")
@patch("houndmind_ai.safety.health_monitor._read_mem_used_pct")
@patch("os.cpu_count")
def test_throttling_actions(
    mock_cpu_count, mock_mem, mock_gpu, mock_cpu_temp, mock_load, module
):
    mock_cpu_count.return_value = 4
    mock_load.return_value = 2.0
    mock_cpu_temp.return_value = 80.0  # >= 70.0
    mock_gpu.return_value = 55.0
    mock_mem.return_value = 50.0

    ctx = DummyContext()
    # Change health actions to not throttle vision
    ctx._store["settings"]["performance"]["health_actions"] = ["throttle_scans"]

    module.start(ctx)
    module.tick(ctx)

    assert ctx.get("health_degraded") is True
    assert ctx.get("scan_interval_override_s") == 1.0
    assert ctx.get("vision_frame_interval_override_s") is None
