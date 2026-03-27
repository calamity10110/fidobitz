from houndmind_ai.behavior.registry import BehaviorRegistry


def test_pick_sequential_happy_path():
    registry = BehaviorRegistry()
    registry.register("action1", lambda: "1")
    registry.register("action2", lambda: "2")
    registry.register("action3", lambda: "3")

    choices = ["action1", "action2", "action3"]

    assert registry.pick_sequential(choices) == "action1"
    assert registry.pick_sequential(choices) == "action2"
    assert registry.pick_sequential(choices) == "action3"
    # Should cycle back
    assert registry.pick_sequential(choices) == "action1"


def test_pick_sequential_unregistered_choices():
    registry = BehaviorRegistry()
    registry.register("action1", lambda: "1")
    registry.register("action3", lambda: "3")

    choices = ["action1", "action2", "action3"]

    assert registry.pick_sequential(choices) == "action1"
    assert registry.pick_sequential(choices) == "action3"
    # Should cycle back
    assert registry.pick_sequential(choices) == "action1"


def test_pick_sequential_no_eligible_choices():
    registry = BehaviorRegistry()

    choices = ["action1", "action2"]
    assert registry.pick_sequential(choices) is None

    assert registry.pick_sequential([]) is None


def test_pick_sequential_changing_choices():
    registry = BehaviorRegistry()
    registry.register("action1", lambda: "1")
    registry.register("action2", lambda: "2")
    registry.register("action3", lambda: "3")

    # First call with two choices
    choices_two = ["action1", "action2"]
    assert registry.pick_sequential(choices_two) == "action1"
    assert registry.pick_sequential(choices_two) == "action2"

    # Next call with three choices
    choices_three = ["action1", "action2", "action3"]
    # The sequence index is currently 2, so it should pick "action3"
    assert registry.pick_sequential(choices_three) == "action3"

    # Next call with one choice
    choices_one = ["action1"]
    # The sequence index is currently 3, which is >= len(choices_one), so it wraps to 0
    assert registry.pick_sequential(choices_one) == "action1"
