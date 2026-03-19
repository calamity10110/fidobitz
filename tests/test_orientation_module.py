import time
from unittest.mock import patch

from houndmind_ai.navigation.orientation import OrientationModule


class DummyContext:
    def __init__(self):
        self.data = {}
        self.reading_queue = []

    def set(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        if key == "sensor_reading" and self.reading_queue:
            return self.reading_queue.pop(0)
        return self.data.get(key, default)


class DummyReading:
    def __init__(self, gyro):
        self.gyro = gyro


def test_calibrate_bias_success():
    ctx = DummyContext()
    ctx.set("settings", {
        "orientation": {
            "calibration_settle_s": 0.0,
            "calibration_duration_s": 1.0,
            "calibration_samples": 3,
        }
    })
    ctx.reading_queue = [
        DummyReading(gyro=(0.0, 0.0, 1.0)),
        DummyReading(gyro=(0.0, 0.0, 2.0)),
        DummyReading(gyro=(0.0, 0.0, 3.0)),
    ]

    module = OrientationModule("orientation")

    # We mock time.sleep so the test runs instantly instead of waiting 0.05s per loop
    with patch("time.sleep"):
        module._calibrate_bias(ctx, ctx.get("settings").get("orientation"))

    assert ctx.get("orientation_calibration_ok") is True
    assert ctx.get("orientation_bias_z") == 2.0  # (1.0 + 2.0 + 3.0) / 3


def test_calibrate_bias_no_samples():
    ctx = DummyContext()
    ctx.set("settings", {
        "orientation": {
            "calibration_settle_s": 0.0,
            "calibration_duration_s": 0.1,  # Short duration
            "calibration_samples": 3,
        }
    })
    # Queue is empty, so it will get None for sensor_reading

    module = OrientationModule("orientation")

    # Mock time.time to simulate time passing so loop exits, and mock time.sleep
    with patch("time.sleep"):
        # We need time.time to return start, then start + 0.2 to break the loop.
        # Add a fourth call for the logger's use of time.time() inside the failure path.
        start_time = 1000.0
        with patch("time.time", side_effect=[start_time, start_time, start_time + 0.2, start_time + 0.2]):
            module._calibrate_bias(ctx, ctx.get("settings").get("orientation"))

    assert ctx.get("orientation_calibration_ok") is False
    assert ctx.get("orientation_bias_z") is None


def test_calibrate_bias_max_bias_cap():
    ctx = DummyContext()
    ctx.set("settings", {
        "orientation": {
            "calibration_settle_s": 0.0,
            "calibration_duration_s": 1.0,
            "calibration_samples": 2,
            "calibration_max_bias_abs": 1.5,
        }
    })
    # The average will be 5.0, but should be capped at 1.5
    ctx.reading_queue = [
        DummyReading(gyro=(0.0, 0.0, 5.0)),
        DummyReading(gyro=(0.0, 0.0, 5.0)),
    ]

    module = OrientationModule("orientation")

    with patch("time.sleep"):
        module._calibrate_bias(ctx, ctx.get("settings").get("orientation"))

    assert ctx.get("orientation_calibration_ok") is True
    assert ctx.get("orientation_bias_z") == 1.5

    # Test negative capping
    ctx2 = DummyContext()
    ctx2.set("settings", {
        "orientation": {
            "calibration_settle_s": 0.0,
            "calibration_duration_s": 1.0,
            "calibration_samples": 2,
            "calibration_max_bias_abs": 1.5,
        }
    })
    # The average will be -5.0, but should be capped at -1.5
    ctx2.reading_queue = [
        DummyReading(gyro=(0.0, 0.0, -5.0)),
        DummyReading(gyro=(0.0, 0.0, -5.0)),
    ]

    with patch("time.sleep"):
        module._calibrate_bias(ctx2, ctx2.get("settings").get("orientation"))

    assert ctx2.get("orientation_calibration_ok") is True
    assert ctx2.get("orientation_bias_z") == -1.5


def test_calibrate_bias_with_settle_time():
    ctx = DummyContext()
    ctx.set("settings", {
        "orientation": {
            "calibration_settle_s": 1.5,
            "calibration_duration_s": 1.0,
            "calibration_samples": 1,
        }
    })
    ctx.reading_queue = [
        DummyReading(gyro=(0.0, 0.0, 1.0)),
    ]

    module = OrientationModule("orientation")

    with patch("time.sleep") as mock_sleep:
        module._calibrate_bias(ctx, ctx.get("settings").get("orientation"))

    # It should have called time.sleep(1.5) first
    mock_sleep.assert_any_call(1.5)
    assert ctx.get("orientation_calibration_ok") is True
