with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "r") as f:
    content = f.read()

# Make the gentle recovery state evaluation its own helper function
new_content = content.replace(
    "# Always set gentle recovery state at the END of tick, using latest time\n        now = time.time()\n        if self._gentle_recovery_active or now < self._gentle_recovery_until:\n            if now >= self._gentle_recovery_until:\n                self._gentle_recovery_active = False\n                self._stuck_count = 0\n                context.set(\"gentle_recovery_active\", False)\n                context.set(\"energy_speed_hint\", None)\n            else:\n                context.set(\"gentle_recovery_active\", True)\n                context.set(\"gentle_recovery_until\", self._gentle_recovery_until)\n                context.set(\"energy_speed_hint\", \"slow\")\n        else:\n            context.set(\"gentle_recovery_active\", False)\n            context.set(\"energy_speed_hint\", None)\n",
    """        # Evaluate gentle recovery state at the start
        self._update_gentle_recovery_context(context, now)"""
)

# And inject it into the class
method_to_add = """
    def _update_gentle_recovery_context(self, context, now: float) -> None:
        if self._gentle_recovery_active or now < self._gentle_recovery_until:
            if now >= self._gentle_recovery_until:
                self._gentle_recovery_active = False
                self._stuck_count = 0
                context.set("gentle_recovery_active", False)
                context.set("energy_speed_hint", None)
            else:
                context.set("gentle_recovery_active", True)
                context.set("gentle_recovery_until", self._gentle_recovery_until)
                context.set("energy_speed_hint", "slow")
        else:
            context.set("gentle_recovery_active", False)
            context.set("energy_speed_hint", None)
"""

with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "w") as f:
    f.write(new_content)
    f.write(method_to_add)
