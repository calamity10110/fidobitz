## 2024-05-30 - Missing Security Headers in Web Dashboard
**Vulnerability:** The internal telemetry web dashboard in `src/houndmind_ai/optional/telemetry_dashboard.py` lacked standard HTTP security headers (X-Content-Type-Options, X-Frame-Options, Content-Security-Policy).
**Learning:** Even internal, locally-bound development servers that expose dashboards or return JSON/ZIP data should include baseline defense-in-depth headers to prevent cross-site scripting (XSS), MIME sniffing, and clickjacking attacks.
**Prevention:** Always ensure that any custom `BaseHTTPRequestHandler` implementation manually sets security headers using `self.send_header(...)` for all HTML, JSON, and file download responses.
