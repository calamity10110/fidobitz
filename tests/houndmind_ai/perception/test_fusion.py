import pytest
from houndmind_ai.perception.fusion import PerceptionModule

class DummySensorService:
    def __init__(self):
        self.subscribers = []
        self.unsubscribed = []

    def subscribe(self, callback):
        self.subscribers.append(callback)

    def unsubscribe(self, callback):
        self.unsubscribed.append(callback)

class DummyContext:
    def __init__(self, data=None):
        self._data = data or {}

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value

def test_perception_module_initialization():
    module = PerceptionModule("perception", enabled=True)
    assert module.status.enabled is True

def test_start_subscribes_to_sensor_service():
    service = DummySensorService()
    context = DummyContext({"sensor_service": service})
    module = PerceptionModule("perception", enabled=True)

    module.start(context)

    assert module._sensor_service == service
    assert module._on_sensor_reading in service.subscribers

def test_start_handles_missing_sensor_service():
    context = DummyContext()
    module = PerceptionModule("perception", enabled=True)

    module.start(context)

    assert module._sensor_service is None

def test_stop_unsubscribes_from_sensor_service():
    service = DummySensorService()
    context = DummyContext({"sensor_service": service})
    module = PerceptionModule("perception", enabled=True)

    module.start(context)
    module.stop(context)

    assert module._on_sensor_reading in service.unsubscribed

def test_stop_handles_exception_during_unsubscribe():
    class ExceptionSensorService(DummySensorService):
        def unsubscribe(self, callback):
            raise Exception("Unsubscribe failed")

    service = ExceptionSensorService()
    context = DummyContext({"sensor_service": service})
    module = PerceptionModule("perception", enabled=True)

    module.start(context)
    # This should not raise an exception
    module.stop(context)

class DummyReading:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

def test_tick_updates_from_context_reading():
    reading = DummyReading(distance_cm=15)
    context = DummyContext({"sensor_reading": reading})
    module = PerceptionModule("perception", enabled=True)

    module.tick(context)

    perception = context.get("perception")
    assert perception is not None
    assert perception["distance"] == 15

def test_on_sensor_reading_updates_from_reading():
    reading = DummyReading(distance_cm=10)
    context = DummyContext()
    module = PerceptionModule("perception", enabled=True)

    module.start(context)
    module._on_sensor_reading(reading)

    perception = context.get("perception")
    assert perception is not None
    assert perception["distance"] == 10

def test_on_sensor_reading_no_context():
    reading = DummyReading(distance_cm=10)
    module = PerceptionModule("perception", enabled=True)

    # Call without start() -> _context is None
    module._on_sensor_reading(reading)

    assert getattr(module, "_context", None) is None

def test_update_from_reading_detects_obstacle():
    # default obstacle_cm is 20
    reading_obstacle = DummyReading(distance_cm=15)
    reading_clear = DummyReading(distance_cm=25)

    context = DummyContext()
    module = PerceptionModule("perception", enabled=True)

    module._update_from_reading(context, reading_obstacle)
    assert context.get("perception")["obstacle"] is True

    module._update_from_reading(context, reading_clear)
    assert context.get("perception")["obstacle"] is False

def test_update_from_reading_respects_settings():
    reading = DummyReading(distance_cm=15)
    # Customize obstacle threshold to 10cm
    settings = {"perception": {"obstacle_cm": 10}}
    context = DummyContext({"settings": settings})

    module = PerceptionModule("perception", enabled=True)
    module._update_from_reading(context, reading)

    # Distance 15 > threshold 10, so no obstacle
    assert context.get("perception")["obstacle"] is False

def test_update_from_reading_handles_missing_attributes():
    reading = DummyReading() # No distance, touch, sound, etc.
    context = DummyContext()
    module = PerceptionModule("perception", enabled=True)

    module._update_from_reading(context, reading)

    perception = context.get("perception")
    assert perception["distance"] is None
    assert perception["touch"] == "N"
    assert perception["sound"] is False
    assert perception["sound_direction"] is None
    assert perception["obstacle"] is False

def test_update_from_reading_parses_all_fields():
    reading = DummyReading(
        distance_cm=5,
        touch="Y",
        sound_detected=True,
        sound_direction=90
    )
    context = DummyContext()
    module = PerceptionModule("perception", enabled=True)

    module._update_from_reading(context, reading)

    perception = context.get("perception")
    assert perception["distance"] == 5
    assert perception["touch"] == "Y"
    assert perception["sound"] is True
    assert perception["sound_direction"] == 90
    assert perception["obstacle"] is True

def test_update_from_reading_generates_pose_hint():
    # Distance is 60 (which is <= anchor_max_cm 120), heading is 45
    reading = DummyReading(distance_cm=60, timestamp=1000)
    context = DummyContext({"current_heading": 45})
    module = PerceptionModule("perception", enabled=True)

    module._update_from_reading(context, reading)

    hint = context.get("pose_hint")
    assert hint is not None
    assert hint["type"] == "anchor_distance"
    assert hint["distance_cm"] == 60.0
    assert hint["heading_deg"] == 45.0
    assert hint["timestamp"] == 1000
    # confidence = (120 - 60) / 120 = 0.5
    assert hint["confidence"] == 0.5

def test_update_from_reading_skips_pose_hint_low_confidence():
    # Setting distance to 100 (confidence = 20 / 120 = 0.166)
    # Default min_conf is 0.3
    reading = DummyReading(distance_cm=100, timestamp=1000)
    context = DummyContext({"current_heading": 45})
    module = PerceptionModule("perception", enabled=True)

    module._update_from_reading(context, reading)

    # Pose hint shouldn't be set due to low confidence
    assert context.get("pose_hint") is None

def test_update_from_reading_respects_custom_fusion_settings():
    reading = DummyReading(distance_cm=100, timestamp=1000)
    # Distance 100 with max 200 => conf 0.5
    # Min conf 0.4 => should pass
    settings = {
        "perception": {
            "fusion": {
                "fusion_anchor_distance_cm": 200,
                "fusion_min_confidence": 0.4
            }
        }
    }
    context = DummyContext({"settings": settings, "current_heading": 90})
    module = PerceptionModule("perception", enabled=True)

    module._update_from_reading(context, reading)

    hint = context.get("pose_hint")
    assert hint is not None
    assert hint["confidence"] == 0.5

def test_update_from_reading_pose_hint_orientation_fallback():
    # current_heading is missing, fallback to orientation dict
    reading = DummyReading(distance_cm=60, timestamp=1000)
    context = DummyContext({"orientation": {"heading": 120}})
    module = PerceptionModule("perception", enabled=True)

    module._update_from_reading(context, reading)

    hint = context.get("pose_hint")
    assert hint is not None
    assert hint["heading_deg"] == 120.0

def test_update_from_reading_pose_hint_no_heading():
    reading = DummyReading(distance_cm=60, timestamp=1000)
    context = DummyContext()  # No current_heading or orientation
    module = PerceptionModule("perception", enabled=True)

    module._update_from_reading(context, reading)

    assert context.get("pose_hint") is None

def test_update_from_reading_pose_hint_distance_out_of_bounds():
    # Distance is greater than max anchor
    reading = DummyReading(distance_cm=130, timestamp=1000)
    context = DummyContext({"current_heading": 45})
    module = PerceptionModule("perception", enabled=True)

    module._update_from_reading(context, reading)

    assert context.get("pose_hint") is None

def test_update_from_reading_pose_hint_invalid_data_handled_gracefully():
    # Simulate an exception in pose_hint logic. For example, pass invalid distance.
    # While _safe_float protects against strings, it returns 0.0 which skips the 0 < distance <= anchor check.
    reading = DummyReading(distance_cm="invalid", timestamp=1000)
    context = DummyContext({"current_heading": 45})
    module = PerceptionModule("perception", enabled=True)

    # Should not raise exception
    module._update_from_reading(context, reading)

    assert context.get("pose_hint") is None
