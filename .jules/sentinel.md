## 2024-05-30 - Prevent Input Validation Bypass via Trailing Newlines
**Vulnerability:** Input validation in HTTP handlers (`face_recognition.py`, `telemetry_dashboard.py`) used `re.match(r"^[a-zA-Z0-9_ -]+$", value)` which allowed trailing newlines (e.g., `"valid\n"`) to bypass validation.
**Learning:** In Python, the `$` anchor in regular expressions matches the end of the string *or* just before a newline at the end of the string. `re.match` evaluates if the pattern matches at the beginning of the string, which combined with `$` permits a trailing newline.
**Prevention:** Use `re.fullmatch()` instead of `re.match()` with `^` and `$` anchors to strictly evaluate the entire length of the input string without permitting trailing newlines.
