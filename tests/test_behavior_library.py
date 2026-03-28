import pytest
from unittest.mock import patch
from houndmind_ai.behavior.library import BehaviorLibrary, BehaviorLibraryConfig


@pytest.fixture
def base_config():
    return BehaviorLibraryConfig(
        idle_actions=["idle1", "idle2"],
        alert_actions=["bark_alert"],
        avoid_actions=["back_up"],
        play_actions=["play"],
        rest_actions=["rest"],
        patrol_actions=["patrol"],
        explore_actions=["explore"],
        interact_actions=["interact"],
        random_idle_chance=0.05,
    )


def test_pick_idle_action_empty(base_config):
    base_config.idle_actions = []
    library = BehaviorLibrary(base_config)
    assert library.pick_idle_action() == "stand"


@patch("random.random")
def test_pick_idle_action_default(mock_random, base_config):
    # Ensure random.random() returns a value >= random_idle_chance (0.05)
    mock_random.return_value = 0.1
    library = BehaviorLibrary(base_config)
    assert library.pick_idle_action() == "idle1"


@patch("random.random")
@patch("random.choice")
def test_pick_idle_action_random(mock_choice, mock_random, base_config):
    # Ensure random.random() returns a value < random_idle_chance (0.05)
    mock_random.return_value = 0.01
    mock_choice.return_value = "idle2"
    library = BehaviorLibrary(base_config)
    assert library.pick_idle_action() == "idle2"
    mock_choice.assert_called_once_with(["idle1", "idle2"])


def test_pick_alert_action(base_config):
    library = BehaviorLibrary(base_config)
    assert library.pick_alert_action() == "bark_alert"


def test_pick_avoid_action(base_config):
    library = BehaviorLibrary(base_config)
    assert library.pick_avoid_action() == "back_up"


def test_pick_play_action(base_config):
    library = BehaviorLibrary(base_config)
    assert library.pick_play_action() == "play"


def test_pick_rest_action(base_config):
    library = BehaviorLibrary(base_config)
    assert library.pick_rest_action() == "rest"


def test_pick_patrol_action(base_config):
    library = BehaviorLibrary(base_config)
    assert library.pick_patrol_action() == "patrol"


def test_pick_explore_action(base_config):
    library = BehaviorLibrary(base_config)
    assert library.pick_explore_action() == "explore"


def test_pick_interact_action(base_config):
    library = BehaviorLibrary(base_config)
    assert library.pick_interact_action() == "interact"


def test_empty_lists_raise_index_error(base_config):
    base_config.alert_actions = []
    library = BehaviorLibrary(base_config)
    with pytest.raises(IndexError):
        library.pick_alert_action()
