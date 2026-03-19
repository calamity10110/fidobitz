import re

with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "r") as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    if line.strip() == "# Action/result variables":
        skip = True

    if skip and line.strip() == "# Always set gentle recovery state at the END of tick, using latest time":
        skip = False
        new_lines.append("        # Set gentle recovery state at the START of tick\n")

    if not skip:
        new_lines.append(line)

with open("src/houndmind_ai/navigation/obstacle_avoidance.py", "w") as f:
    f.writelines(new_lines)
