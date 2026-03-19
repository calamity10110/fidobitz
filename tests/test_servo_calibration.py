import pytest
from unittest.mock import MagicMock, patch

from houndmind_ai.calibration.servo_calibration import apply_servo_offsets, collect_servo_defaults

def test_apply_servo_offsets_none_dog():
    # Should return early, not raise
    apply_servo_offsets(None, {"head_pan": 10.0})

def test_apply_servo_offsets_empty():
    dog = MagicMock()
    # Test with None or empty offsets
    apply_servo_offsets(dog, None)
    apply_servo_offsets(dog, {})
    dog.set_servo_zero.assert_not_called()

def test_apply_servo_offsets_with_set_servo_zero():
    dog = MagicMock()
    dog.set_servo_zero = MagicMock()
    # Also attach a servos property to make sure it prioritizes set_servo_zero
    dog.servos = {"head_pan": MagicMock()}

    offsets = {"head_pan": 10.5, "head_tilt": -5.0}
    apply_servo_offsets(dog, offsets)

    assert dog.set_servo_zero.call_count == 2
    dog.set_servo_zero.assert_any_call("head_pan", 10.5)
    dog.set_servo_zero.assert_any_call("head_tilt", -5.0)

def test_apply_servo_offsets_with_servos_dict():
    dog = MagicMock(spec=["servos"])
    mock_servo1 = MagicMock()
    mock_servo2 = MagicMock()
    dog.servos = {"head_pan": mock_servo1, "head_tilt": mock_servo2}

    offsets = {"head_pan": 10.5, "head_tilt": -5.0, "unknown_servo": 1.0}
    apply_servo_offsets(dog, offsets)

    assert mock_servo1.zero_offset == 10.5
    assert mock_servo2.zero_offset == -5.0

def test_apply_servo_offsets_exception():
    dog = MagicMock()
    dog.set_servo_zero.side_effect = Exception("Test exception")

    offsets = {"head_pan": 10.5}
    # This should log a warning but not raise the exception
    apply_servo_offsets(dog, offsets)

def test_collect_servo_defaults_none_dog():
    assert collect_servo_defaults(None) == {}

def test_collect_servo_defaults_get_servo_zero():
    dog = MagicMock()
    dog.servo_names = ["head_pan", "head_tilt", "unknown"]
    def mock_get_servo_zero(name):
        if name == "head_pan":
            return 10.5
        elif name == "head_tilt":
            return -5.0
        raise ValueError("Unknown servo")

    dog.get_servo_zero.side_effect = mock_get_servo_zero

    defaults = collect_servo_defaults(dog)
    assert defaults == {"head_pan": 10.5, "head_tilt": -5.0}

def test_collect_servo_defaults_servos_dict():
    # Only supply servos dict, not get_servo_zero
    dog = MagicMock(spec=["servos"])
    mock_servo1 = MagicMock()
    mock_servo1.zero_offset = 10.5
    mock_servo2 = MagicMock()
    mock_servo2.zero_offset = -5.0
    mock_servo3 = MagicMock()
    del mock_servo3.zero_offset  # Missing attribute

    dog.servos = {"head_pan": mock_servo1, "head_tilt": mock_servo2, "broken": mock_servo3}

    defaults = collect_servo_defaults(dog)
    # The default returned value for broken should be 0.0 (per code getattr(s, 'zero_offset', 0.0))
    assert defaults == {"head_pan": 10.5, "head_tilt": -5.0, "broken": 0.0}

def test_collect_servo_defaults_exceptions():
    dog = MagicMock()
    # Mock servo_names so the loop runs, but make get_servo_zero raise
    dog.servo_names = ["head_pan"]
    dog.get_servo_zero.side_effect = Exception("General error")

    defaults = collect_servo_defaults(dog)
    assert defaults == {}

    # Next, mock a broken servos dict
    dog2 = MagicMock(spec=["servos"])
    type(dog2).servos = property(lambda self: Exception("Property error"))
    defaults2 = collect_servo_defaults(dog2)
    assert defaults2 == {}
