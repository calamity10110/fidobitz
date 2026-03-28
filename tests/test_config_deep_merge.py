from houndmind_ai.core.config import _deep_merge


def test_deep_merge_simple_update():
    target = {"a": 1, "b": 2}
    overrides = {"a": 10}
    _deep_merge(target, overrides)
    assert target == {"a": 10, "b": 2}


def test_deep_merge_add_new_keys():
    target = {"a": 1}
    overrides = {"b": 2}
    _deep_merge(target, overrides)
    assert target == {"a": 1, "b": 2}


def test_deep_merge_nested_update():
    target = {"a": {"b": 1, "c": 2}}
    overrides = {"a": {"b": 10}}
    _deep_merge(target, overrides)
    assert target == {"a": {"b": 10, "c": 2}}


def test_deep_merge_nested_addition():
    target = {"a": {"b": 1}}
    overrides = {"a": {"c": 2}}
    _deep_merge(target, overrides)
    assert target == {"a": {"b": 1, "c": 2}}


def test_deep_merge_type_change_to_non_dict():
    target = {"a": {"b": 1}}
    overrides = {"a": 10}
    _deep_merge(target, overrides)
    assert target == {"a": 10}


def test_deep_merge_type_change_to_dict():
    target = {"a": 1}
    overrides = {"a": {"b": 10}}
    _deep_merge(target, overrides)
    assert target == {"a": {"b": 10}}


def test_deep_merge_no_overlap():
    target = {"a": 1}
    overrides = {"b": {"c": 2}}
    _deep_merge(target, overrides)
    assert target == {"a": 1, "b": {"c": 2}}


def test_deep_merge_empty_target():
    target = {}
    overrides = {"a": 1}
    _deep_merge(target, overrides)
    assert target == {"a": 1}


def test_deep_merge_empty_overrides():
    target = {"a": 1}
    overrides = {}
    _deep_merge(target, overrides)
    assert target == {"a": 1}


def test_deep_merge_multiple_nesting_levels():
    target = {"level1": {"level2": {"level3": {"a": 1, "b": 2}}}}
    overrides = {"level1": {"level2": {"level3": {"a": 10}, "new_key": "hello"}}}
    _deep_merge(target, overrides)
    assert target == {
        "level1": {"level2": {"level3": {"a": 10, "b": 2}, "new_key": "hello"}}
    }
