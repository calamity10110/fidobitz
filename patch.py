with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "r") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip() == "_update_gentle_recovery_state()":
        continue

    if line.strip() == "self._gentle_recovery_until = now + gentle_recovery_cooldown":
        new_lines.append(line)
        new_lines.append("                _update_gentle_recovery_state()\n")
        continue

    new_lines.append(line)

with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "w") as f:
    f.writelines(new_lines)
