import re
with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "r") as f:
    content = f.read()

content = content.replace(
    "                # Evaluate gentle recovery state at the start\n        self._update_gentle_recovery_context(context, now)\n",
    "        # Evaluate gentle recovery state at the start\n        self._update_gentle_recovery_context(context, now)\n\n"
)

# And inject it again
with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "w") as f:
    f.write(content)
