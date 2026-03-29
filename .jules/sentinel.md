## 2024-05-30 - Missing Security Headers in Web Dashboard
**Vulnerability:** The internal telemetry web dashboard in `src/houndmind_ai/optional/telemetry_dashboard.py` lacked standard HTTP security headers (X-Content-Type-Options, X-Frame-Options, Content-Security-Policy).
**Learning:** Even internal, locally-bound development servers that expose dashboards or return JSON/ZIP data should include baseline defense-in-depth headers to prevent cross-site scripting (XSS), MIME sniffing, and clickjacking attacks.
**Prevention:** Always ensure that any custom `BaseHTTPRequestHandler` implementation manually sets security headers using `self.send_header(...)` for all HTML, JSON, and file download responses.

## 2024-05-31 - Path Traversal in Face Recognition Enrollment
**Vulnerability:** The `/enroll` HTTP endpoints in `FaceRecognitionModule` allowed arbitrary path traversal when constructing the directory path for saving face image datasets because the `name` parameter was not sanitized.
**Learning:** Any user-supplied input from an HTTP request (query parameters or JSON body) used to construct file system paths must be strictly validated.
**Prevention:** Always sanitize or validate path components against a strict allowlist regex (e.g., `^[a-zA-Z0-9_ -]+$`) to prevent directory traversal attacks (`../` or absolute paths) before using them in `Path` operations.
## 2024-11-06 - Path Traversal via Unvalidated User Input
**Vulnerability:** HTTP endpoints reading `trace_id` and using it directly to format a zip file path and inject it into an environment variable before executing `subprocess` commands. Even with `Path(trace_id).name` extracting just the filename, special characters or spaces can lead to file creation issues or command misinterpretation later.
**Learning:** `Path.name` alone does not sufficiently sanitize malicious input from HTTP sources. Wait, relying on single-component parsing is insufficient if downstream tools lack proper quoting or escaping.
**Prevention:** Any user-supplied HTTP input (query parameters or JSON payload) that is used to construct file system paths or commands must be explicitly validated against a strict allowlist regex (e.g., `^[a-zA-Z0-9_ -]+$`) to prevent Path Traversal vulnerabilities.
