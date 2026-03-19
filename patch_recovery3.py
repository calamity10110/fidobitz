with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "r") as f:
    content = f.read()

# Add a call right after it activates gentle recovery.
content = content.replace(
    """            if (
                not self._gentle_recovery_active
                and self._stuck_count >= gentle_recovery_threshold
            ):
                self._gentle_recovery_active = True
                self._gentle_recovery_until = now + gentle_recovery_cooldown
            return""",
    """            if (
                not self._gentle_recovery_active
                and self._stuck_count >= gentle_recovery_threshold
            ):
                self._gentle_recovery_active = True
                self._gentle_recovery_until = now + gentle_recovery_cooldown
                self._update_gentle_recovery_context(context, now)
            return"""
)

with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "w") as f:
    f.write(content)
