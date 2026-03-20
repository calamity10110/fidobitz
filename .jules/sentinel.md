## 2025-02-18 - [Path Traversal in Support Bundle Creation]
**Vulnerability:** A Path Traversal vulnerability in `TelemetryDashboardModule.create_support_bundle_for_trace` allowed an attacker to specify a malicious `trace_id` containing directory traversal characters (e.g., `../../../../tmp/evil`), which would write a ZIP file to an arbitrary location on the filesystem.
**Learning:** The vulnerability existed because the `trace_id` string from an HTTP request was directly interpolated into a file path without sanitization: `Path(tempfile.mkdtemp()) / f"support_bundle_{trace_id}.zip"`.
**Prevention:** Always sanitize user-provided input before using it to construct file paths. Specifically, extract only the filename component (e.g., using `Path(trace_id).name` or `os.path.basename`) to strip any path directory traversal attempts.

## 2026-03-19 - [Unauthenticated Face Enrollment and Operations]
**Vulnerability:** The `FaceRecognitionModule` HTTP server allowed unauthenticated users to trigger face enrollment and access the list of detected faces.
**Learning:** The vulnerability existed because the HTTP request handler did not implement any authentication mechanism for sensitive endpoints, assuming a trusted network environment.
**Prevention:** Implement a token-based authentication system (e.g., `X-Auth-Token` header) for all non-public endpoints. Ensure secure defaults by binding to `127.0.0.1` and generating a cryptographically secure session token if none is provided in the configuration.
## 2025-02-28 - Unauthenticated Camera Video Stream Exposure
**Vulnerability:** The camera video stream endpoint in `vision_pi4.py` was bound to `0.0.0.0` by default and had no authentication mechanism for accessing the `/stream` endpoint.
**Learning:** Hardcoded, globally bound public endpoints for sensitive data (like camera streams) create severe privacy and security risks.
**Prevention:** Use a shared secure authentication token logic (via `houndmind_ai.core.auth.get_shared_auth_token`) across local modules to restrict access, and enforce safe defaults like binding local servers to `127.0.0.1` unless explicitly configured otherwise by the user.
