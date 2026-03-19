with open("tests/test_gentle_recovery.py", "r") as f:
    content = f.read()

# Fix the test cleanly
content = content.replace(
    """    # Gentle recovery should activate after the first tick
    module.tick(context)
    print(f"Tick 1: context={dict(context)}, _gentle_recovery_active={module._gentle_recovery_active}")
    assert context.get("gentle_recovery_active") is True
    assert module._gentle_recovery_active is True
    assert context.get("energy_speed_hint") == "slow"
    # Remain active for subsequent ticks
    module.tick(context)
    print(f"Tick 2: context={dict(context)}, _gentle_recovery_active={module._gentle_recovery_active}")
    assert context.get("gentle_recovery_active") is True""",
    """    # Tick 2: _stuck_count reaches 2, still inactive
    module.tick(context)
    assert context.get("gentle_recovery_active") is False
    assert module._gentle_recovery_active is False
    assert context.get("energy_speed_hint") is None
    # Tick 3: _stuck_count reaches 3, gentle recovery activates
    module.tick(context)
    assert context.get("gentle_recovery_active") is True
    assert module._gentle_recovery_active is True
    assert context.get("energy_speed_hint") == "slow"
    # Tick 4: Remain active for subsequent ticks
    module.tick(context)
    assert context.get("gentle_recovery_active") is True"""
)

with open("tests/test_gentle_recovery.py", "w") as f:
    f.write(content)
