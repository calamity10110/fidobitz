import pytest
from houndmind_ai.navigation.obstacle_avoidance import ObstacleAvoidanceModule

def test_sanity():
    module = ObstacleAvoidanceModule("test")
    assert module is not None
