from __future__ import annotations

import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional, Any
from urllib.parse import urlparse, parse_qs

from houndmind_ai.core.module import Module
from houndmind_ai.core.auth import get_shared_auth_token
from houndmind_ai.optional.vision_preprocessing import VisionPreprocessor
from houndmind_ai.optional.vision_inference_scheduler import VisionInferenceScheduler

logger = logging.getLogger(__name__)


class VisionPi4Module(Module):
    """Pi4-focused vision feed.

    Publishes `vision_frame` into context. Supports Picamera2 if available,
    otherwise falls back to OpenCV VideoCapture.
    """

    def __init__(self, name: str, enabled: bool = True, required: bool = False) -> None:
        super().__init__(name, enabled=enabled, required=required)
        self.available = False
        self._camera: Any | None = None
        self._cv2: Any | None = None
        self._capture: Any | None = None
        self._last_frame_ts = 0.0
        self._last_frame = None

        self._http_server: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None

        self._preprocessor: Optional[VisionPreprocessor] = None
        self._inference_scheduler: Optional[VisionInferenceScheduler] = None
        self._last_inference_result = None

    def start(self, context) -> None:
        if not self.status.enabled:
            return
        settings = (context.get("settings") or {}).get("vision_pi4", {})
        backend = settings.get("backend", "picamera2")

        # Setup preprocessor and inference scheduler if enabled
        self._preprocessor = VisionPreprocessor(settings.get("preprocessing", {}))
        if settings.get("inference_scheduler_enabled", True):
            def _on_inference_result(result):
                self._last_inference_result = result
                context.set("vision_inference_result", result)
            # Dummy inference function, replace with actual model
            def _dummy_inference(frame):
                time.sleep(0.05)
                return {"frame_id": id(frame), "result": "ok"}
            self._inference_scheduler = VisionInferenceScheduler(
                _dummy_inference, result_callback=_on_inference_result
            )
            assert self._inference_scheduler is not None
            self._inference_scheduler.start()

        if backend == "picamera2":
            try:
                from picamera2 import Picamera2  # type: ignore
            except Exception as exc:  # noqa: BLE001
                logger.warning("Picamera2 unavailable: %s", exc)
            else:
                try:
                    cam = Picamera2()
                    config = cam.create_preview_configuration()
                    cam.configure(config)
                    cam.start()
                    self._camera = cam
                    self.available = True
                    context.set(
                        "vision_status", {"status": "ready", "backend": backend}
                    )
                    self._maybe_start_http(context, settings)
                    return
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Picamera2 init failed: %s", exc)

        try:
            import cv2  # type: ignore
        except Exception as exc:  # noqa: BLE001
            self.disable(f"Vision backend unavailable: {exc}")
            return

        device_index = int(settings.get("device_index", 0))
        capture = cv2.VideoCapture(device_index)
        if not capture.isOpened():
            self.disable("Failed to open camera device")
            return

        self._cv2 = cv2
        self._capture = capture
        self.available = True
        context.set("vision_status", {"status": "ready", "backend": "opencv"})
        self._maybe_start_http(context, settings)

    def tick(self, context) -> None:
        if not self.available or not self.status.enabled:
            return

        settings = (context.get("settings") or {}).get("vision_pi4", {})
        if not settings.get("enabled", True):
            return

        override_interval = context.get("vision_frame_interval_override_s")
        if isinstance(override_interval, (int, float)):
            frame_interval = float(override_interval)
        else:
            frame_interval = float(settings.get("frame_interval_s", 0.2))
        now = time.time()
        if now - self._last_frame_ts < frame_interval:
            return

        frame = None
        if self._camera is not None:
            try:
                frame = self._camera.capture_array()
            except Exception as exc:  # noqa: BLE001
                logger.debug("Picamera2 capture failed: %s", exc)
        elif self._capture is not None:
            ok, frame = self._capture.read()
            if not ok:
                frame = None

        if frame is not None:
            context.set("vision_frame", frame)
            context.set("vision_frame_ts", now)
            self._last_frame_ts = now
            self._last_frame = frame
            # Preprocess and schedule inference if enabled
            if self._preprocessor and self._inference_scheduler:
                try:
                    processed = self._preprocessor.process(frame)
                    self._inference_scheduler.submit_frame(processed)
                except Exception as exc:
                    logger.warning("Vision preprocessing/inference failed: %s", exc)

    def stop(self, context) -> None:
        if self._camera is not None:
            try:
                self._camera.stop()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Picamera2 stop failed: %s", exc)
        if self._capture is not None:
            try:
                self._capture.release()
            except Exception as exc:  # noqa: BLE001
                logger.warning("VideoCapture release failed: %s", exc)
        if self._http_server is not None:
            try:
                self._http_server.shutdown()
                self._http_server.server_close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Vision HTTP server shutdown failed: %s", exc)
        if self._inference_scheduler:
            self._inference_scheduler.stop()
            self._inference_scheduler = None

    def _maybe_start_http(self, context, settings: dict) -> None:
        http_settings = settings.get("http", {})
        if not http_settings.get("enabled", False):
            return
        host = http_settings.get("host", "127.0.0.1")
        port = int(http_settings.get("port", 8090))

        auth_token = get_shared_auth_token(context, http_settings)
        if auth_token == context.get("shared_auth_token"):
            logger.debug("No auth_token configured for vision_pi4; using generated shared session token.")
            if context.get("shared_auth_token_printed") is not True:
                print(f"Generated shared session token: {auth_token}")
                context.set("shared_auth_token_printed", True)

        if host == "0.0.0.0":
            logger.warning("Vision HTTP server configured to bind to 0.0.0.0 — ensure network access is restricted or use the generated/configured auth_token")

        module = self

        class Handler(BaseHTTPRequestHandler):
            def _auth_ok(self, params: dict) -> bool:
                import secrets
                if not auth_token:
                    return False
                # check header first
                hdr = self.headers.get("X-Auth-Token")
                if hdr and secrets.compare_digest(hdr, auth_token):
                    return True
                # then query param
                q = params.get("auth_token", [None])[0]
                if q and secrets.compare_digest(q, auth_token):
                    return True
                return False

            def do_GET(self):
                parsed = urlparse(self.path)
                path = parsed.path
                params = parse_qs(parsed.query)

                if path != "/stream":
                    self.send_response(404)
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("X-Frame-Options", "DENY")
                    self.end_headers()
                    return

                if not self._auth_ok(params):
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("X-Frame-Options", "DENY")
                    self.end_headers()
                    self.wfile.write(b'{"error": "unauthorized"}')
                    return

                self.send_response(200)
                self.send_header(
                    "Content-Type", "multipart/x-mixed-replace; boundary=frame"
                )
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.end_headers()

                try:
                    while True:
                        frame = module._last_frame
                        if frame is None or module._cv2 is None:
                            time.sleep(0.05)
                            continue

                        ok, buf = module._cv2.imencode(".jpg", frame)
                        if not ok:
                            time.sleep(0.05)
                            continue
                        payload = buf.tobytes()
                        self.wfile.write(b"--frame\r\n")
                        self.wfile.write(b"Content-Type: image/jpeg\r\n")
                        self.wfile.write(
                            f"Content-Length: {len(payload)}\r\n\r\n".encode()
                        )
                        self.wfile.write(payload)
                        self.wfile.write(b"\r\n")
                        time.sleep(0.1)
                except Exception:
                    return

            def log_message(self, format, *args):
                return

        try:
            server = ThreadingHTTPServer((host, port), Handler)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to start vision HTTP server: %s", exc)
            return
        self._http_server = server
        self._http_thread = threading.Thread(target=server.serve_forever, daemon=True)
        self._http_thread.start()
        logger.info("Vision HTTP stream on http://%s:%s/stream", host, port)
