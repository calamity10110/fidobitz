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
## 2025-02-14 - Insecure Default HTTP Binding in Optional Modules
**Vulnerability:** HTTP servers in `FaceRecognitionModule`, `VisionPi4Module`, `VoiceModule`, and `TelemetryDashboardModule` permitted binding to the public `0.0.0.0` interface without strictly enforcing an opt-in security flag, potentially exposing sensitive endpoints to untrusted networks. Also, the `VisionPi4Module`, `FaceRecognitionModule`, and `VoiceModule` lacked fundamental security headers like `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` on multiple response variants.
**Learning:** Security-sensitive HTTP servers embedded in modules must default securely (`127.0.0.1`) and explicitly reject insecure configuration (`0.0.0.0`) unless a dedicated boolean override (e.g., `danger_allow_public`) is provided to indicate intentional, informed risk. Additionally, all possible HTTP responses (including JSON APIs, streams, and 401/404 errors) require comprehensive header hardening.
**Prevention:** Implement strict network binding checks that fall back to `127.0.0.1` upon encountering `0.0.0.0` without the `danger_allow_public` flag. Always verify that all paths and response types within a `BaseHTTPRequestHandler` emit `X-Content-Type-Options: nosniff` and `X-Frame-Options: DENY` headers.

## 2024-05-27 - [Inconsistent Auth Token Generation Across Modules]
**Vulnerability:** FaceRecognitionModule and VoiceModule generated their own tokens (`secrets.token_urlsafe(32)`) locally rather than utilizing the globally consistent `get_shared_auth_token`.
**Learning:** This fragmented the security model, making it impossible to predict or share the authorization token dynamically injected or generated for other modules like Telemetry and Vision. As a result, users might be inadvertently locked out or required to discover logs for multiple distinct tokens.
**Prevention:** Always enforce usage of `houndmind_ai.core.auth.get_shared_auth_token` when configuring module endpoints to guarantee session consistency.

## 2024-05-27 - [Missing Content-Disposition Headers on File Endpoints]
**Vulnerability:** The TelemetryDashboardModule returned sensitive file payloads (`application/json` and `application/zip`) via endpoints without the `Content-Disposition: attachment` header.
**Learning:** Relying solely on the frontend client (e.g. `a.download`) to enforce download behavior allows browsers to potentially render payloads directly if a user navigates manually. For JSON payloads, this exposes the application to potential MIME-sniffing or XSS if the data were mishandled.
**Prevention:** Always pair `Content-Type` headers with `Content-Disposition: attachment; filename="..."` when serving data intended exclusively for download.
## 2024-04-06 - Memory Exhaustion / DoS Vulnerability in Optional HTTP Handlers
**Vulnerability:** The HTTP handlers for the optional `face_recognition` and `voice` modules lacked a maximum limit on the `Content-Length` header. This allowed malicious clients to send requests with extremely large payloads, which could lead to Memory Exhaustion (OOM) and a Denial of Service when the server synchronously called `self.rfile.read(length)`.
**Learning:** In `http.server.BaseHTTPRequestHandler` subclasses,  executes synchronously and blocks, attempting to load the entire payload into memory at once if no limit is enforced.
**Prevention:** Always validate and enforce a strict upper limit on the `Content-Length` header before reading the payload (e.g., 1MB for text endpoints) to prevent Memory Exhaustion DoS vulnerabilities.
## 2024-04-06 - Memory Exhaustion / DoS Vulnerability in Optional HTTP Handlers
**Vulnerability:** The HTTP handlers for the optional `face_recognition` and `voice` modules lacked a maximum limit on the `Content-Length` header. This allowed malicious clients to send requests with extremely large payloads, which could lead to Memory Exhaustion (OOM) and a Denial of Service when the server synchronously called `self.rfile.read(length)`.
**Learning:** In `http.server.BaseHTTPRequestHandler` subclasses, `rfile.read(length)` executes synchronously and blocks, attempting to load the entire payload into memory at once if no limit is enforced.
**Prevention:** Always validate and enforce a strict upper limit on the `Content-Length` header before reading the payload (e.g., 1MB for text endpoints) to prevent Memory Exhaustion DoS vulnerabilities.
