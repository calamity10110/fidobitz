## 2024-05-18 - Prevent Directory Traversal via Newline Bypass
**Vulnerability:** Used `re.match()` with `$` to validate `trace_id` and `name` strings containing safe alphanumeric paths.
**Learning:** In Python, `re.match(pattern, string)` followed by `$` permits the string to end with a single newline character (e.g., `'valid_name\n'`). When these validated strings are concatenated into file paths, the injected newline can lead to subtle directory traversal or path resolution vulnerabilities depending on the underlying OS API.
**Prevention:** Always use `re.fullmatch(pattern, string)` when performing strict security boundary validation to ensure the entire string is evaluated without trailing exceptions.
