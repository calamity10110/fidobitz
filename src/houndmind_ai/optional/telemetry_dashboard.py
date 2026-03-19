from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from typing import Any

from houndmind_ai.core.module import Module

logger = logging.getLogger(__name__)


class TelemetryHTTPHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the telemetry dashboard.

    A class attribute `module` is dynamically attached to the class
    before instantiation by ThreadingHTTPServer.
    """
    module: "TelemetryDashboardModule"

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _auth_ok(self, params: dict) -> bool:
        token = getattr(self.module, "_auth_token", None)
        if not token:
            return False
        # check header first
        hdr = self.headers.get("X-Auth-Token")
        if hdr == token:
            return True
        # then query param
        q = params.get("auth_token", [None])[0]
        if q == token:
            return True
        return False

    def _handle_status(self) -> None:
        self._send_json({"status": "ok"})

    def _handle_snapshot(self, params: dict) -> None:
        # Allow filtering by trace id via header or query parameter
        header_trace = self.headers.get("X-Trace-Id")
        query_trace = params.get("trace_id", [None])[0]
        req_trace = header_trace or query_trace
        if req_trace:
            snap = self.module.get_snapshot_for_trace(req_trace)
            if snap is None:
                self._send_json({"error": "not found"}, status=404)
                return
            self._send_json(snap)
            return
        self._send_json(self.module._snapshot)

    def _handle_download_slam_map(self) -> None:
        data = self.module._snapshot.get("slam_map_data")
        if data is None:
            self._send_json({"error": "no map data"}, status=404)
            return
        # Serve as JSON
        self.send_response(200)
        payload = json.dumps({"map": data}, default=str).encode("utf-8")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_download_support_bundle(self, params: dict) -> None:
        # Accept trace_id via header or query
        header_trace = self.headers.get("X-Trace-Id")
        query_trace = params.get("trace_id", [None])[0]
        req_trace = header_trace or query_trace or self.module._snapshot.get("trace_id")
        if not req_trace:
            self._send_json({"error": "trace_id required"}, status=400)
            return
        zip_path = self.module.create_support_bundle_for_trace(req_trace)
        if not zip_path:
            self._send_json({"error": "failed to create bundle"}, status=500)
            return
        try:
            with open(zip_path, "rb") as fh:
                data = fh.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=500)

    def _handle_download_slam_trajectory(self) -> None:
        data = self.module._snapshot.get("slam_trajectory")
        if data is None:
            self._send_json({"error": "no trajectory"}, status=404)
            return
        self.send_response(200)
        payload = json.dumps({"trajectory": data}, default=str).encode("utf-8")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _handle_dashboard_html(self) -> None:
        # Inject configured camera path into the dashboard HTML
        html = _DASHBOARD_HTML.replace(
            "{{CAMERA_PATH}}", str(getattr(self.module, "_camera_path", "/camera"))
        ).replace(
            "{{AUTH_TOKEN}}", str(getattr(self.module, "_auth_token", ""))
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # Public endpoint
        if path == "/status":
            self._handle_status()
            return

        # All other endpoints require authentication
        if not self._auth_ok(params):
            self._send_json({"error": "unauthorized"}, status=401)
            return

        if path == "/snapshot":
            self._handle_snapshot(params)
            return

        if path == "/download_slam_map":
            self._handle_download_slam_map()
            return

        if path == "/download_support_bundle":
            self._handle_download_support_bundle(params)
            return

        if path == "/download_slam_trajectory":
            self._handle_download_slam_trajectory()
            return

        if path == "/":
            self._handle_dashboard_html()
            return

        self._send_json({"error": "Not found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        # Suppress default HTTP server logging
        return


class TelemetryDashboardModule(Module):
    """Optional telemetry dashboard (Pi4-focused).

    Exposes a small HTTP server with JSON snapshots of selected context keys.
    Disabled by default and safe to leave off for Pi3.
    """

    def __init__(self, name: str, enabled: bool = True, required: bool = False) -> None:
        super().__init__(name, enabled=enabled, required=required)
        self.available = False
        self._http_server: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._snapshot: dict = {}
        self._last_ts = 0.0
        self._last_vision_ts: float | None = None
        self._vision_fps: float | None = None

    def start(self, context) -> None:
        if not self.status.enabled:
            return
        self.available = True
        settings = (context.get("settings") or {}).get("telemetry_dashboard", {})
        self._maybe_start_http(settings)
        context.set("telemetry_status", {"status": "ready"})

    def get_snapshot_for_trace(self, trace_id: str) -> dict | None:
        """Return the current snapshot if its trace_id matches, otherwise None."""
        if not self._snapshot:
            return None
        if self._snapshot.get("trace_id") == trace_id:
            return self._snapshot
        return None

    def create_support_bundle_for_trace(self, trace_id: str):
        """Create a support bundle zip file for the given trace_id and return its Path.

        This uses the project's `tools.collect_support_bundle` module to produce
        a zip file. The function returns the path to the created zip file or None
        on failure.
        """
        try:
            import tempfile
            from pathlib import Path
            # Import the collect function from tools
            from tools.collect_support_bundle import collect

            safe_trace_id = Path(trace_id).name
            tmp = Path(tempfile.mkdtemp()) / f"support_bundle_{safe_trace_id}.zip"
            # Set env var so the collector records the trace id
            import os

            old = os.environ.get("HOUNDMIND_TRACE_ID")
            os.environ["HOUNDMIND_TRACE_ID"] = str(trace_id)
            try:
                collect(tmp)
            finally:
                if old is None:
                    os.environ.pop("HOUNDMIND_TRACE_ID", None)
                else:
                    os.environ["HOUNDMIND_TRACE_ID"] = old
            if tmp.exists():
                return tmp
        except Exception:
            logger.exception("Failed to create support bundle for trace %s", trace_id)
        return None

    def tick(self, context) -> None:
        if not self.available or not self.status.enabled:
            return

        settings = (context.get("settings") or {}).get("telemetry_dashboard", {})
        if not settings.get("enabled", True):
            return

        interval = float(settings.get("snapshot_interval_s", 0.5))
        now = time.time()
        if now - self._last_ts < interval:
            return

        keys = settings.get(
            "context_keys",
            [
                "sensor_reading",
                "scan_latest",
                "mapping_openings",
                "navigation_action",
                "behavior_action",
                "safety_action",
                "performance_telemetry",
                "slam_pose",
                "slam_map_data",
                "slam_trajectory",
                "faces",
                "semantic_labels",
            ],
        )

        vision_ts = context.get("vision_frame_ts")
        if isinstance(vision_ts, (int, float)):
            if self._last_vision_ts is not None:
                dt = float(vision_ts) - float(self._last_vision_ts)
                if dt > 0:
                    self._vision_fps = 1.0 / dt
            self._last_vision_ts = float(vision_ts)

        health_status = context.get("health_status") or {}
        runtime_perf = context.get("runtime_performance") or {}
        performance = {
            "timestamp": now,
            "tick_hz_target": runtime_perf.get("tick_hz_target"),
            "tick_hz_actual": runtime_perf.get("tick_hz_actual"),
            "tick_duration_s": runtime_perf.get("tick_duration_s"),
            "tick_duration_avg_s": runtime_perf.get("tick_duration_avg_s"),
            "tick_interval_s": runtime_perf.get("tick_interval_s"),
            "tick_interval_avg_s": runtime_perf.get("tick_interval_avg_s"),
            "tick_overrun_s": runtime_perf.get("tick_overrun_s"),
            "vision_fps": self._vision_fps,
            "cpu_load_1m": health_status.get("load_1m"),
            "cpu_temp_c": health_status.get("temp_c"),
            "gpu_temp_c": health_status.get("gpu_temp_c"),
            "mem_used_pct": health_status.get("mem_used_pct"),
            "cpu_cores": health_status.get("cpu_cores"),
            "health_degraded": health_status.get("degraded"),
        }
        context.set("performance_telemetry", performance)

        snapshot = {"timestamp": now}
        for key in keys:
            snapshot[key] = context.get(key)
        # Surface trace_id at the top-level of the snapshot for correlation.
        snapshot["trace_id"] = context.get("trace_id")
        self._snapshot = snapshot
        self._last_ts = now

    def stop(self, context) -> None:
        if self._http_server is not None:
            try:
                self._http_server.shutdown()
                self._http_server.server_close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to stop telemetry server: %s", exc)

    def _maybe_start_http(self, settings: dict) -> None:
        http_settings = settings.get("http", {})
        if not http_settings.get("enabled", False):
            return
        # Default to loopback for LAN-safe behavior. Allow overriding,
        # but warn if binding to 0.0.0.0 (public) without explicit opt-in.
        host = http_settings.get("host", "127.0.0.1")
        port = int(http_settings.get("port", 8092))
        # Configurable camera path for embedding a stream or single-frame URL
        self._camera_path = http_settings.get("camera_path", "/camera")
        # Optional simple token-based auth for endpoints that can expose
        # sensitive data (support bundle, map downloads). If set, requests
        # must include this token in `X-Auth-Token` header or `auth_token` query.
        self._auth_token = http_settings.get("auth_token")
        if not self._auth_token:
            self._auth_token = secrets.token_urlsafe(32)
            logger.debug("No auth_token configured for telemetry dashboard; generated a secure session token: %s", self._auth_token)
            print(f"Telemetry dashboard generated session token: {self._auth_token}")

        if host == "0.0.0.0":
            logger.warning("Telemetry dashboard configured to bind to 0.0.0.0 — ensure network access is restricted or use the generated/configured auth_token")

        # Create a subclass of our handler that has this module instance bound to it
        class BoundHandler(TelemetryHTTPHandler):
            module = self

        try:
            server = ThreadingHTTPServer((host, port), BoundHandler)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to start telemetry server: %s", exc)
            return
        self._http_server = server
        self._http_thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._http_thread.start()
        logger.info("Telemetry dashboard on http://%s:%s/", host, port)


_DASHBOARD_HTML = """
<!doctype html>
<html lang="en" data-theme="system">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>HoundMind Control Panel</title>
    <style>
        /* Design Token System Foundation */
        :root {
            /* Light Theme Tokens */
            --bg-primary: #f8fafc;
            --bg-secondary: #ffffff;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --border-color: #e2e8f0;
            --accent-primary: #3b82f6;
            --accent-hover: #2563eb;
            --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1);

            /* Typography Scale */
            --text-xs: 0.75rem;
            --text-sm: 0.875rem;
            --text-base: 1rem;
            --text-lg: 1.125rem;
            --text-xl: 1.25rem;

            /* Spacing System */
            --space-1: 0.25rem;
            --space-2: 0.5rem;
            --space-3: 0.75rem;
            --space-4: 1rem;
            --space-6: 1.5rem;
            --space-8: 2rem;

            /* Layout System */
            --container-max: 1280px;
            --border-radius: 12px;
            --transition-speed: 0.3s;
        }

        /* Dark Theme Tokens */
        [data-theme="dark"] {
            --bg-primary: #020617;
            --bg-secondary: #0f172a;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --border-color: #1e293b;
            --accent-primary: #38bdf8;
            --accent-hover: #7dd3fc;
            --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.3);
        }

        /* System Theme Preference */
        @media (prefers-color-scheme: dark) {
            :root:not([data-theme="light"]) {
                --bg-primary: #020617;
                --bg-secondary: #0f172a;
                --text-primary: #f8fafc;
                --text-secondary: #94a3b8;
                --border-color: #1e293b;
                --accent-primary: #38bdf8;
                --accent-hover: #7dd3fc;
                --card-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.3), 0 2px 4px -2px rgb(0 0 0 / 0.3);
            }
        }

        /* Base Reset & Typography */
        * { box-sizing: border-box; margin: 0; padding: 0; }

        body {
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            transition: background-color var(--transition-speed), color var(--transition-speed);
        }

        /* Layout Architecture */
        .container {
            width: 100%;
            max-width: var(--container-max);
            margin: 0 auto;
            padding: var(--space-4);
            display: flex;
            flex-direction: column;
            gap: var(--space-6);
            flex: 1;
        }

        .header {
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            justify-content: space-between;
            gap: var(--space-4);
            padding: var(--space-4) 0;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: var(--space-2);
        }

        .header-title {
            display: flex;
            align-items: center;
            gap: var(--space-3);
        }

        .header h1 {
            font-size: var(--text-xl);
            font-weight: 600;
            letter-spacing: -0.025em;
        }

        .header-controls {
            display: flex;
            align-items: center;
            gap: var(--space-4);
            flex-wrap: wrap;
        }

        /* Component: Cards */
        .card {
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--border-radius);
            padding: var(--space-6);
            box-shadow: var(--card-shadow);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            display: flex;
            flex-direction: column;
            gap: var(--space-4);
            overflow: hidden;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: var(--space-3);
            margin-bottom: var(--space-2);
        }

        .card-title {
            font-size: var(--text-lg);
            font-weight: 600;
        }

        .meta {
            color: var(--text-secondary);
            font-size: var(--text-sm);
        }

        /* Grid Patterns */
        .grid-main {
            display: grid;
            grid-template-columns: 1fr;
            gap: var(--space-6);
        }

        @media (min-width: 1024px) {
            .grid-main {
                grid-template-columns: 3fr 2fr;
                align-items: start;
            }
        }

        .grid-stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: var(--space-4);
        }

        .stat-item {
            background-color: var(--bg-primary);
            padding: var(--space-3);
            border-radius: calc(var(--border-radius) / 1.5);
            border: 1px solid var(--border-color);
            text-align: center;
        }

        .stat-value {
            font-size: var(--text-lg);
            font-weight: 700;
            color: var(--accent-primary);
            margin-top: var(--space-1);
        }

        /* Media / Camera Feed */
        .camera-container {
            background-color: #000;
            border-radius: calc(var(--border-radius) - 4px);
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 300px;
            position: relative;
        }

        #camera {
            width: 100%;
            height: auto;
            max-height: 600px;
            object-fit: contain;
        }

        /* Typography / Code Output */
        pre {
            background-color: var(--bg-primary);
            color: var(--text-primary);
            padding: var(--space-4);
            border-radius: calc(var(--border-radius) / 1.5);
            border: 1px solid var(--border-color);
            font-family: 'JetBrains Mono', monospace, Consolas;
            font-size: var(--text-xs);
            overflow-x: auto;
            max-height: 400px;
            white-space: pre-wrap;
            word-break: break-all;
        }

        /* Buttons & Interactions */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: var(--space-2);
            padding: var(--space-2) var(--space-4);
            font-size: var(--text-sm);
            font-weight: 500;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 1px solid transparent;
            text-decoration: none;
        }

        .btn-primary {
            background-color: var(--accent-primary);
            color: #ffffff;
        }

        .btn-primary:hover {
            background-color: var(--accent-hover);
            transform: translateY(-1px);
        }

        .btn-outline {
            background-color: transparent;
            border-color: var(--border-color);
            color: var(--text-primary);
        }

        .btn-outline:hover {
            background-color: var(--bg-primary);
            border-color: var(--accent-primary);
            color: var(--accent-primary);
        }

        .btn:focus-visible {
            outline: 2px solid var(--accent-primary);
            outline-offset: 2px;
        }

        /* Theme Toggle Component */
        .theme-toggle {
            display: inline-flex;
            align-items: center;
            background-color: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: 24px;
            padding: 4px;
            gap: 2px;
        }

        .theme-toggle-option {
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: var(--text-xs);
            font-weight: 500;
            color: var(--text-secondary);
            background: transparent;
            border: none;
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .theme-toggle-option:hover {
            color: var(--text-primary);
        }

        .theme-toggle-option.active {
            background-color: var(--accent-primary);
            color: #ffffff;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }

        .status-indicator {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #10b981; /* Success Green */
            box-shadow: 0 0 8px #10b981;
        }

        .status-indicator.offline {
            background-color: #ef4444; /* Error Red */
            box-shadow: 0 0 8px #ef4444;
        }

        /* Badges */
        .badge {
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: var(--text-xs);
            font-weight: 500;
            background-color: var(--bg-primary);
            border: 1px solid var(--border-color);
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header & Top Navigation -->
        <header class="header">
            <div class="header-title">
                <div class="status-indicator" id="connection_status" title="Connection Status"></div>
                <h1>HoundMind Control Panel</h1>
                <span class="badge" id="trace_id" title="Current Trace ID">Waiting for data...</span>
                <button id="copy_trace" class="btn btn-outline" style="padding: 2px 6px; font-size: 0.7rem;" aria-label="Copy Trace ID">Copy ID</button>
            </div>

            <div class="header-controls">
                <button id="download_bundle" class="btn btn-outline" aria-label="Download Support Bundle">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    Support Bundle
                </button>

                <!-- Theme Toggle -->
                <div class="theme-toggle" role="radiogroup" aria-label="Theme selection">
                    <button class="theme-toggle-option" data-theme="light" role="radio" aria-checked="false" aria-label="Light mode">☀️</button>
                    <button class="theme-toggle-option" data-theme="dark" role="radio" aria-checked="false" aria-label="Dark mode">🌙</button>
                    <button class="theme-toggle-option active" data-theme="system" role="radio" aria-checked="true" aria-label="System mode">💻</button>
                </div>
            </div>
        </header>

        <!-- Main Content Grid -->
        <main class="grid-main">
            <!-- Left Column: Camera Feed & Quick Stats -->
            <div style="display: flex; flex-direction: column; gap: var(--space-6);">
                <section class="card" aria-labelledby="camera-title">
                    <div class="card-header">
                        <h2 id="camera-title" class="card-title">Live Vision</h2>
                        <span class="badge"><span id="vision_fps">--</span> FPS</span>
                    </div>
                    <div class="camera-container">
                        <img id="camera" src="{{CAMERA_PATH}}" alt="Live camera feed from robot"/>
                    </div>
                </section>

                <section class="card" aria-labelledby="stats-title">
                    <div class="card-header">
                        <h2 id="stats-title" class="card-title">Performance Telemetry</h2>
                    </div>
                    <div class="grid-stats">
                        <div class="stat-item">
                            <div class="meta">Tick Rate</div>
                            <div class="stat-value"><span id="tick_rate">--</span> Hz</div>
                        </div>
                        <div class="stat-item">
                            <div class="meta">Memory Used</div>
                            <div class="stat-value"><span id="mem_used">--</span>%</div>
                        </div>
                        <div class="stat-item">
                            <div class="meta">CPU Load (1m)</div>
                            <div class="stat-value"><span id="cpu_load">--</span></div>
                        </div>
                        <div class="stat-item">
                            <div class="meta">CPU Temp</div>
                            <div class="stat-value"><span id="cpu_temp">--</span>°C</div>
                        </div>
                    </div>
                </section>
            </div>

            <!-- Right Column: Data Streams & Controls -->
            <div style="display: flex; flex-direction: column; gap: var(--space-6);">
                <section class="card" aria-labelledby="snapshot-title">
                    <div class="card-header">
                        <div>
                            <h2 id="snapshot-title" class="card-title">State Snapshot</h2>
                            <div class="meta">Synchronizes every 500ms</div>
                        </div>
                        <button id="refresh" class="btn btn-primary" aria-label="Refresh Data Streams">Refresh</button>
                    </div>
                    <pre id="output" tabindex="0" aria-label="Raw snapshot JSON output">Connecting to telemetry stream...</pre>
                </section>

                <section class="card" aria-labelledby="slam-title">
                    <div class="card-header">
                        <h2 id="slam-title" class="card-title">SLAM Data</h2>
                        <div style="display: flex; gap: var(--space-2);">
                            <button id="download_map" class="btn btn-outline btn-sm" aria-label="Download Map">Map</button>
                            <button id="download_traj" class="btn btn-outline btn-sm" aria-label="Download Trajectory">Trajectory</button>
                        </div>
                    </div>
                    <pre id="slam" tabindex="0" aria-label="SLAM data output">No SLAM data available</pre>
                </section>
            </div>
        </div>
        <script>
            const camera = document.getElementById('camera');
            const out = document.getElementById('output');
            const quick = document.getElementById('quick');
            const fpsLabel = document.getElementById('vision_fps');
            const refresh = document.getElementById('refresh');
            const authToken = "{{AUTH_TOKEN}}";
            let last = 0;

            function getAuthUrl(path) {
                const url = new URL(path, window.location.origin);
                if (authToken) url.searchParams.set('auth_token', authToken);
                return url.toString();
            }

            async function tick(){
                try{
                    const headers = authToken ? { 'X-Auth-Token': authToken } : {};
                    const res = await fetch('/snapshot', { headers });
                    const data = await res.json();
                    out.textContent = JSON.stringify(data, null, 2);
                    // expose trace id in header for quick copying
                    const traceEl = document.getElementById('trace_id');
                    traceEl.textContent = data.trace_id || '-';
                    const perf = data.performance_telemetry || {};
                    fpsLabel.textContent = perf.vision_fps ? perf.vision_fps.toFixed(1) : '-';
                    quick.textContent = `tick ${perf.tick_hz_actual || '-'} • mem ${perf.mem_used_pct || '-'}%`;
                    const slamEl = document.getElementById('slam');
                    if(data.slam_map_data || data.slam_trajectory){
                        slamEl.textContent = JSON.stringify({map: data.slam_map_data, trajectory: data.slam_trajectory}, null, 2);
                    } else {
                        slamEl.textContent = 'No SLAM data';
                    }
                });
            }

            getStoredTheme() {
                return localStorage.getItem('houndmind-theme');
            }

            applyTheme(theme) {
                if (theme === 'system') {
                    document.documentElement.setAttribute('data-theme', 'system');
                } else {
                    document.documentElement.setAttribute('data-theme', theme);
                }
                localStorage.setItem('houndmind-theme', theme);
                this.currentTheme = theme;
                this.updateToggleUI();
            }

            initializeToggle() {
                const options = document.querySelectorAll('.theme-toggle-option');
                options.forEach(opt => {
                    opt.addEventListener('click', (e) => {
                        const newTheme = e.currentTarget.dataset.theme;
                        this.applyTheme(newTheme);
                    });
                });
            }

            updateToggleUI() {
                const options = document.querySelectorAll('.theme-toggle-option');
                options.forEach(option => {
                    const isActive = option.dataset.theme === this.currentTheme;
                    option.classList.toggle('active', isActive);
                    option.setAttribute('aria-checked', isActive.toString());
                });
            }
        }

        // Initialize theme
        document.addEventListener('DOMContentLoaded', () => {
            new ThemeManager();
        });

        // --- Application Logic ---
        const camera = document.getElementById('camera');
        const out = document.getElementById('output');

        // Stats elements
        const fpsLabel = document.getElementById('vision_fps');
        const tickRate = document.getElementById('tick_rate');
        const memUsed = document.getElementById('mem_used');
        const cpuLoad = document.getElementById('cpu_load');
        const cpuTemp = document.getElementById('cpu_temp');
        const statusIndicator = document.getElementById('connection_status');

        let consecutiveErrors = 0;

        async function tick() {
            try {
                const res = await fetch('/snapshot');
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();

                // Update Connection Status
                consecutiveErrors = 0;
                statusIndicator.classList.remove('offline');

                // Output raw JSON
                out.textContent = JSON.stringify(data, null, 2);

                // Update Trace ID
                const traceEl = document.getElementById('trace_id');
                traceEl.textContent = data.trace_id || 'N/A';

                // Update Performance Telemetry
                const perf = data.performance_telemetry || {};
                fpsLabel.textContent = perf.vision_fps ? perf.vision_fps.toFixed(1) : '--';
                tickRate.textContent = perf.tick_hz_actual ? perf.tick_hz_actual.toFixed(1) : '--';
                memUsed.textContent = perf.mem_used_pct ? perf.mem_used_pct.toFixed(1) : '--';
                cpuLoad.textContent = perf.cpu_load_1m ? perf.cpu_load_1m.toFixed(2) : '--';
                cpuTemp.textContent = perf.cpu_temp_c ? perf.cpu_temp_c.toFixed(1) : '--';

                // Update SLAM Data
                const slamEl = document.getElementById('slam');
                if(data.slam_map_data || data.slam_trajectory) {
                    slamEl.textContent = JSON.stringify({
                        map: data.slam_map_data ? "Map data available" : null,
                        trajectory: data.slam_trajectory ? "Trajectory available" : null
                    }, null, 2);
                } else {
                    slamEl.textContent = 'No SLAM data available';
                }
            } catch(e) {
                consecutiveErrors++;
                if(consecutiveErrors > 2) {
                    statusIndicator.classList.add('offline');
                }
                out.textContent = 'Connection Error: ' + e.message;
            }
        }

        // Avoid caching single-frame camera endpoints
        function reloadCamera() {
            const base = camera.getAttribute('src').split('?')[0];
            camera.src = base + '?ts=' + Date.now();
        }

        // Event Listeners
        document.getElementById('refresh').addEventListener('click', () => {
            tick();
            reloadCamera();
        });

        document.getElementById('copy_trace').addEventListener('click', () => {
            const txt = document.getElementById('trace_id').textContent || '';
            if(!txt || txt === 'Waiting for data...' || txt === 'N/A') return;
            try {
                navigator.clipboard.writeText(txt);
                const btn = document.getElementById('copy_trace');
                const origText = btn.textContent;
                btn.textContent = 'Copied!';
                setTimeout(() => btn.textContent = origText, 2000);
            } catch(e) {
                alert('Copy failed: ' + e);
            }
        });

        document.getElementById('download_bundle').addEventListener('click', async () => {
            const txt = document.getElementById('trace_id').textContent || '';
            if(!txt || txt === 'Waiting for data...' || txt === 'N/A') {
                alert('No trace ID available. Cannot generate bundle.');
                return;
            }
            try {
                const btn = document.getElementById('download_bundle');
                const origHtml = btn.innerHTML;
                btn.innerHTML = 'Downloading...';
                btn.disabled = true;

                const res = await fetch('/download_support_bundle?trace_id=' + encodeURIComponent(txt));
                if(!res.ok) {
                    const err = await res.json().catch(()=>null);
                    alert('Failed to create bundle: ' + (err && err.error ? err.error : res.statusText));
                } else {
            // Avoid caching single-frame camera endpoints by adding a timestamp
            function reloadCamera(){
                const base = camera.getAttribute('src').split('?')[0];
                const camUrl = new URL(base, window.location.origin);
                camUrl.searchParams.set('ts', Date.now());
                if (authToken && !base.startsWith('http')) {
                    camUrl.searchParams.set('auth_token', authToken);
                }
                camera.src = camUrl.toString();
            }
            refresh.addEventListener('click', ()=>{ tick(); reloadCamera(); });
            document.getElementById('copy_trace').addEventListener('click', ()=>{
                const txt = document.getElementById('trace_id').textContent || '';
                if(!txt || txt === '-') return; try{ navigator.clipboard.writeText(txt); alert('Trace id copied') }catch(e){ alert('Copy failed') }
            });

            document.getElementById('download_bundle').addEventListener('click', async ()=>{
                const txt = document.getElementById('trace_id').textContent || '';
                if(!txt || txt === '-') { alert('No trace id available'); return }
                try{
                    const bundleUrl = new URL('/download_support_bundle', window.location.origin);
                    bundleUrl.searchParams.set('trace_id', txt);
                    if (authToken) bundleUrl.searchParams.set('auth_token', authToken);
                    const res = await fetch(bundleUrl.toString());
                    if(!res.ok){
                        const err = await res.json().catch(()=>null);
                        alert('Failed to create bundle: ' + (err && err.error ? err.error : res.statusText));
                        return
                    }
                    const blob = await res.blob();
                    const dlUrl = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = dlUrl;
                    a.download = `support_bundle_${txt}.zip`;
                    a.click();
                    URL.revokeObjectURL(url);
                }
                btn.innerHTML = origHtml;
                btn.disabled = false;
            } catch(e) {
                alert('Download failed: ' + e);
                document.getElementById('download_bundle').disabled = false;
            }
        });

        document.getElementById('download_map').addEventListener('click', async () => {
            const res = await fetch('/download_slam_map');
            if(res.ok) {
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = 'slam_map.json'; a.click();
            } else { alert('No map data available on server') }
        });

        document.getElementById('download_traj').addEventListener('click', async () => {
            const res = await fetch('/download_slam_trajectory');
            if(res.ok) {
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = 'slam_trajectory.json'; a.click();
            } else { alert('No trajectory data available on server') }
        });

        // Main Loop
        setInterval(() => { tick(); reloadCamera(); }, 500);
        tick();
    </script>
</body>
                    URL.revokeObjectURL(dlUrl);
                }catch(e){ alert('Download failed: '+e) }
            });
            document.getElementById('download_map').addEventListener('click', async ()=>{
                const res = await fetch(getAuthUrl('/download_slam_map'));
                if(res.ok){
                    const blob = await res.blob();
                    const dlUrl = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = dlUrl; a.download = 'slam_map.json'; a.click();
                    URL.revokeObjectURL(dlUrl);
                } else { alert('No map data') }
            });
            document.getElementById('download_traj').addEventListener('click', async ()=>{
                const res = await fetch(getAuthUrl('/download_slam_trajectory'));
                if(res.ok){
                    const blob = await res.blob();
                    const dlUrl = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = dlUrl; a.download = 'slam_trajectory.json'; a.click();
                    URL.revokeObjectURL(dlUrl);
                } else { alert('No trajectory') }
            });
            setInterval(()=>{ tick(); reloadCamera(); }, 500);
            tick();
        </script>
    </body>
</html>
"""
