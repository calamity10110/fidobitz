import time
from houndmind_ai.navigation.local_planner import LocalPlannerModule

class DummyContext:
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

def test_local_planner_tick_disabled():
    module = LocalPlannerModule()
    ctx = DummyContext({"settings": {"navigation": {"planner_enabled": False}}})
    module.tick(ctx)
    assert "local_plan" not in ctx.data

def test_local_planner_tick_no_best_path():
    module = LocalPlannerModule()
    ctx = DummyContext({"settings": {"navigation": {"planner_enabled": True}}, "mapping_openings": {}})
    module.tick(ctx)
    plan = ctx.get("local_plan")
    assert plan is not None
    assert plan["valid"] is False

def test_local_planner_tick_valid_path():
    module = LocalPlannerModule()
    now = time.time()
    ctx = DummyContext({
        "settings": {
            "navigation": {
                "planner_enabled": True,
                "planner_min_confidence": 0.5,
                "planner_max_age_s": 2.0
            }
        },
        "mapping_openings": {
            "timestamp": now - 1.0, # 1 second ago, age is ok
            "best_path": {
                "confidence": 0.8,
                "yaw": -1.5,
                "score": 0.9
            }
        }
    })
    module.tick(ctx)
    plan = ctx.get("local_plan")
    assert plan is not None
    assert plan["valid"] is True
    assert plan["direction"] == "left"
    assert plan["confidence"] == 0.8
    assert plan["yaw"] == -1.5
    assert plan["score"] == 0.9

    rec = ctx.get("mapping_recommendation")
    assert rec is not None
    assert rec["direction"] == "left"
    assert rec["confidence"] == 0.8

def test_local_planner_tick_invalid_age():
    module = LocalPlannerModule()
    now = time.time()
    ctx = DummyContext({
        "settings": {
            "navigation": {
                "planner_enabled": True,
                "planner_min_confidence": 0.5,
                "planner_max_age_s": 2.0
            }
        },
        "mapping_openings": {
            "timestamp": now - 3.0, # 3 seconds ago, age NOT ok
            "best_path": {
                "confidence": 0.8,
                "yaw": -1.5,
                "score": 0.9
            }
        }
    })
    module.tick(ctx)
    plan = ctx.get("local_plan")
    assert plan is not None
    assert plan["valid"] is False

def test_local_planner_tick_invalid_confidence():
    module = LocalPlannerModule()
    now = time.time()
    ctx = DummyContext({
        "settings": {
            "navigation": {
                "planner_enabled": True,
                "planner_min_confidence": 0.8,
                "planner_max_age_s": 2.0
            }
        },
        "mapping_openings": {
            "timestamp": now - 1.0,
            "best_path": {
                "confidence": 0.5, # < min_conf
                "yaw": -1.5,
                "score": 0.9
            }
        }
    })
    module.tick(ctx)
    plan = ctx.get("local_plan")
    assert plan is not None
    assert plan["valid"] is False
