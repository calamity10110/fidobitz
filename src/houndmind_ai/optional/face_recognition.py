from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from typing import Any

from houndmind_ai.core.module import Module
from houndmind_ai.core.auth import get_shared_auth_token

logger = logging.getLogger(__name__)


class FaceRecognitionModule(Module):
    """Pi4-focused face recognition module (backend-pluggable).

    Lite backend: OpenCV Haar detector with optional LBPH recognition.
    Heavy backend: face_recognition (dlib-based) with embeddings.
    """

    def __init__(self, name: str, enabled: bool = True, required: bool = False) -> None:
        super().__init__(name, enabled=enabled, required=required)
        self.backend: str = "stub"
        self.available = False
        self.repo_root = Path(__file__).resolve().parents[3]

        self._cv2: Any | None = None
        self._cascade: Any | None = None
        self._recognizer: Any | None = None
        self._label_map: dict[int, str] = {}

        self._embeddings_path: Path | None = None
        self._known_embeddings: list[list[float]] = []
        self._known_names: list[str] = []

        self._http_server: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._pending_commands: list[dict[str, Any]] = []
        self._latest_faces: list[dict[str, Any]] = []

    def start(self, context) -> None:
        if not self.status.enabled:
            return

        settings = (context.get("settings") or {}).get("face_recognition", {})
        backend = settings.get("backend", "stub")
        self.backend = backend

        if backend == "stub":
            self._start_stub(context)
        elif backend == "opencv":
            self._start_opencv(context, settings)
        elif backend == "face_recognition":
            self._start_face_recognition(context, settings)
        else:
            logger.error("Unknown face recognition backend: %s", backend)
            self.disable("Internal error")

    def _start_stub(self, context) -> None:
        self.available = True
        context.set(
            "face_recognition_status", {"status": "ready", "backend": self.backend}
        )

    def _start_opencv(self, context, settings: dict) -> None:
        try:
            import cv2  # type: ignore
        except Exception:  # noqa: BLE001
            logger.exception("OpenCV backend unavailable")
            self.disable("Internal error")
            return

        self._cv2 = cv2
        haar_path = settings.get("opencv_haar_path")
        if not haar_path:
            data_obj = getattr(self._cv2, "data", None)
            if data_obj is not None:
                if getattr(data_obj, "haarcascades", None) is not None:
                    haar_path = str(
                        Path(getattr(data_obj, "haarcascades"))
                        / "haarcascade_frontalface_default.xml"
                    )
                # Removed the empty if check for 'haaracascades'
            if not haar_path:
                haar_path = ""

        haar_path = self._resolve_path(haar_path)
        if not haar_path.exists():
            logger.error("Haar cascade not found: %s", haar_path)
            self.disable("Internal error")
            return

        self._cascade = cv2.CascadeClassifier(str(haar_path))
        self._init_lbph(settings)

        self.available = True
        context.set(
            "face_recognition_status", {"status": "ready", "backend": self.backend}
        )
        self._maybe_start_http(context, settings)

    def _init_lbph(self, settings: dict) -> None:
        lbph_settings = settings.get("lbph", {})
        if (
            not lbph_settings.get("enabled", True)
            or self._cv2 is None
            or not hasattr(self._cv2, "face")
        ):
            return

        try:
            self._recognizer = self._cv2.face.LBPHFaceRecognizer_create()  # type: ignore[attr-defined, union-attr]
        except Exception as exc:  # noqa: BLE001
            logger.warning("LBPH unavailable: %s", exc)
            self._recognizer = None
            return

        model_path = self._resolve_path(
            lbph_settings.get("model_path", "data/face_model.yml")
        )
        dataset_dir = self._resolve_path(
            lbph_settings.get("dataset_dir", "data/face_dataset")
        )
        label_map_path = self._resolve_path(
            lbph_settings.get("label_map_path", "data/face_labels.json")
        )

        self._label_map = self._load_label_map(label_map_path)
        if model_path.exists():
            try:
                self._recognizer.read(str(model_path))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to read LBPH model: %s", exc)
        elif dataset_dir.exists():
            self._train_lbph(dataset_dir, model_path, label_map_path)

    def _start_face_recognition(self, context, settings: dict) -> None:
        try:
            import face_recognition  # type: ignore  # noqa: F401
        except Exception:  # noqa: BLE001
            logger.exception("face_recognition backend unavailable")
            self.disable("Internal error")
            return

        self._embeddings_path = self._resolve_path(
            settings.get("embeddings_path", "data/face_embeddings.json")
        )
        self._load_embeddings()

        self.available = True
        context.set(
            "face_recognition_status", {"status": "ready", "backend": self.backend}
        )
        self._maybe_start_http(context, settings)

    def tick(self, context) -> None:
        if not self.available or not self.status.enabled:
            return

        settings = (context.get("settings") or {}).get("face_recognition", {})
        if not settings.get("enabled", True):
            return

        command = context.get("face_recognition_command")
        if isinstance(command, dict):
            self._handle_command(command, context, settings)
            context.set("face_recognition_command", None)

        if self._pending_commands:
            for pending in list(self._pending_commands):
                self._handle_command(pending, context, settings)
                self._pending_commands.remove(pending)

        detections: list[dict[str, Any]] = []
        raw = context.get("vision_faces_raw")
        if isinstance(raw, list):
            detections = raw

        frame = context.get("vision_frame")
        if detections:
            context.set("faces", self._wrap_faces(context, detections))
            return

        if frame is None:
            return

        if self.backend == "opencv":
            detections = self._detect_opencv(frame, settings)
        elif self.backend == "face_recognition":
            detections = self._detect_face_recognition(frame, settings)
        else:
            detections = []

        context.set("faces", self._wrap_faces(context, detections))
        self._latest_faces = detections

    def _wrap_faces(self, context, detections: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "timestamp": context.get("tick_ts"),
            "backend": self.backend,
            "detected": detections,
        }

    def _maybe_start_http(self, context, settings: dict) -> None:
        http_settings = settings.get("http", {})
        if not http_settings.get("enabled", False):
            return
        # Default to loopback for LAN-safe behavior.
        host = http_settings.get("host", "127.0.0.1")
        port = int(http_settings.get("port", 8088))

        # Optional simple token-based auth for endpoints that can expose
        # sensitive data or trigger operations (enrolling faces).
        self._auth_token = get_shared_auth_token(context, http_settings)
        if self._auth_token == context.get("shared_auth_token"):
            logger.debug(
                "No auth_token configured for face recognition; using generated shared session token."
            )
            if context.get("shared_auth_token_printed") is not True:
                print(f"Generated shared session token: {self._auth_token}")
                context.set("shared_auth_token_printed", True)

        if host == "0.0.0.0":
            if not http_settings.get("danger_allow_public", False):
                logger.error(
                    "Face recognition HTTP server configured to bind to 0.0.0.0, but 'danger_allow_public' is not true. "
                    "Falling back to 127.0.0.1 for security."
                )
                host = "127.0.0.1"
            else:
                logger.warning(
                    "Face recognition HTTP server configured to bind to 0.0.0.0 â ensure network access is restricted or use the generated/configured auth_token"
                )

        module = self

        class Handler(BaseHTTPRequestHandler):
            def _send_json(self, payload, status=200):
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("X-Frame-Options", "DENY")
                self.send_header("Content-Security-Policy", "default-src 'none'")
                self.end_headers()
                self.wfile.write(data)

            def _auth_ok(self, params: dict) -> bool:
                token = getattr(module, "_auth_token", None)
                if not token:
                    return False
                hdr = self.headers.get("X-Auth-Token")
                if hdr and secrets.compare_digest(hdr, token):
                    return True
                q = params.get("auth_token", [None])[0]
                if q and secrets.compare_digest(q, token):
                    return True
                return False

            def do_GET(self):
                parsed = urlparse(self.path)
                params = parse_qs(parsed.query)

                if parsed.path == "/status":
                    self._send_json({"status": "ok", "backend": module.backend})
                    return

                # All other endpoints require authentication
                if not self._auth_ok(params):
                    self._send_json({"error": "unauthorized"}, status=401)
                    return

                if parsed.path == "/faces":
                    self._send_json({"faces": module._latest_faces})
                    return
                if parsed.path == "/enroll":
                    name = (params.get("name") or [None])[0]
                    if not name:
                        self._send_json({"error": "Missing name"}, status=400)
                        return
                    if not re.fullmatch(r"^[a-zA-Z0-9_ -]+$", name):
                        self._send_json({"erræÖRf÷&ÖB'ÒÂ7FGW3ÓC¢&WGW&à¢ÖöGVÆRå÷VæFæuö6öÖÖæG2æVæB²&7me": name})
                    self._send_json({"stb&WGW&à¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢$æ÷Bf÷VæB'ÒÂ7FGW3ÓCB ¢FVbFõõõ5B6VÆb ¢'6VBÒW&Ç'6R6VÆbçF¢&×2Ò'6U÷2'6VBçVW' ¢2ÆÂõ5BVæGöçG2&WV&RWFVçF6Föà¢bæ÷B6VÆbåöWFöö²&×2 ¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢'VæWF÷&¦VB'ÒÂ7FGW3ÓC¢&WGW&à ¢ÆVæwFÒçB6VÆbæVFW'2ævWB$6öçFVçBÔÆVæwF"Â#"¢bÆVæwFâCSsc¢2Ô"ÆÖBFò&WfVçBFõ2vFÆ&vRÖvW0¢6VÆbå÷6VæEö§6öâ²&W'oad too large"}, status=413)
                    return
                body = self.rfile.read(length).decode("utf-8") if length > 0 else ""
                if parsed.path == "/enroll":
                    try:
                        payload = json.loads(body) if body else {}
                    except Exception:
                        payload = {}
                    name = payload.get("name")
                    if not name:
                        self._send_json({"error": "Missing name"}, status=400)
                        return
                    if not re.fullmatch(r"^[a-zA-Z0-9_ -]+$", name):
                        self._send_json({"error": "Invalid name format"}, status=400)
                        return
                    module._pending_commands.append({"action": "enroll", "name": name})
                    self._send_json({"status": "queued", "name": name})
                    return
                self._send_json({"errFVbÆöuöÖW76vR6VÆbÂf÷&ÖBÂ¦&w2 ¢&WGW&à ¢G' ¢6W'fW"ÒF&VFætEE6W'fW"÷7BÂ÷'BÂæFÆW"¢W6WBW6WFöâ2W3¢2æ÷¢$ÄS¢ÆövvW"çv&æær$fÆVBFò7F'Bf6R&V6övæFöâEE6W'fW#¢W2"ÂW2¢&WGW&à¢6VÆbåöGG÷6W'fW"Ò6W'fW ¢6VÆbåöGG÷F&VBÒF&VFæråF&VBF&vWC×6W'fW"ç6W'fUöf÷&WfW"ÂFVÖöãÕG'VR¢6VÆbåöGG÷F&VBç7F'B¢ÆövvW"ææfò$f6R&V6övæFöâEE6W'fW"Æ7FVææröâW3¢W2"Â÷7BÂ÷'B ¢FVböÇöÆ'÷&V6övæFöâ¢6VÆbÂVçG'¢F7E·7G"ÂçÒÂf6U÷&ö¢çÂF&W6öÆC¢fÆö@¢ÓâæöæS ¢""$ÆW2Ä%f6R&V6övæFöâFòFWFV7FVBf6R$ôâ"" ¢b6VÆbå÷&V6övæ¦W"2æöæS ¢&WGW&à ¢G' ¢Æ&VÅöBÂ6öæfFVæ6RÒ6VÆbå÷&V6övæ¦W"ç&VF7Bf6U÷&ö¢æÖRÒ6VÆbåöÆ&VÅöÖævWBçBÆ&VÅöBÂ'Væ¶æ÷vâ"¢VçG'çWFFR²&Æ&VÂ#¢æÖRÂ&6öæfFVæ6R#¢fÆöB6öæfFVæ6RÒ¢b6öæfFVæ6RâF&W6öÆC ¢VçG'²&Æ&VÂ%ÒÒ'Væ¶æ÷vâ ¢W6WBW6WFöâ2W3¢2æ÷¢$ÄS¢ÆövvW"çv&æær¢$Ä%&VF7FöâfÆVBf÷"$ôvF6RW3¢W2"À¢vWFGG"f6U÷&öÂ'6R"Â'Væ¶æ÷vâ"À¢W2À¢W5öæfóÕG'VRÀ¢ ¢FVböFWFV7Eö÷Væ7b6VÆbÂg&ÖRÂ6WGFæw3¢F7BÓâÆ7E¶F7E·7G"ÂçÕÓ ¢b6VÆbåö7c"2æöæR÷"6VÆbåö666FR2æöæS ¢&WGW&âµÐ¢7c"Ò6VÆbåö7c ¢w&Ò7c"æ7gD6öÆ÷"g&ÖRÂ7c"ä4ôÄõ%ô$u#$u$ ¢66ÆUöf7F÷"ÒfÆöB6WGFæw2ævWB'66ÆUöf7F÷""Âã¢ÖåöæVv&÷'2ÒçB6WGFæw2ævWB&ÖåöæVv&÷'2"ÂR¢Öåöf6U÷ÒçB6WGFæw2ævWB&Öåöf6U÷"Âc ¢f6W2Ò6VÆbåö666FRæFWFV7D×VÇF66ÆR¢w&À¢66ÆTf7F÷#×66ÆUöf7F÷"À¢ÖäæVv&÷'3ÖÖåöæVv&÷'2À¢Öå6¦SÒÖåöf6U÷ÂÖåöf6U÷À¢ ¢&W7VÇG3¢Æ7E¶F7E·7G"ÂçÕÒÒµÐ¢Æ'÷6WGFæw2Ò6WGFæw2ævWB&Æ'"Â·Ò¢F&W6öÆBÒfÆöBÆ'÷6WGFæw2ævWB&6öæfFVæ6U÷F&W6öÆB"Âsã¢f÷"ÂÂrÂâf6W3 ¢VçG'¢F7E·7G"ÂçÒÒ²&&&)]}
            face_roi = gray[y : y + h, x : x + w]
            self._apply_lbph_recognition(entry, face_roi, threshold)
            results.append(entry)
        return results

    def _detect_face_recognition(self, frame, settings: dict) -> list[dict[str, Any]]:
        try:
            import face_recognition  # type: ignore
        except Exception:
            return []

        rgb = frame[:, :, ::-1]
        locations = face_recognition.face_locations(rgb)
        encodings = face_recognition.face_encodings(rgb, locations)
        threshold = float(settings.get("match_threshold", 0.6))
        results: list[dict[str, Any]] = []

        for (top, right, bottom, left), encoding in zip(locations, encodings):
            label = "unknown"
            confidence = None
            if self._known_embeddings:
                distances = face_recognition.face_distance(
                    self._known_embeddings, encoding
                )
                if len(distances) > 0:
                    best_idx = int(distances.argmin())  # type: ignore[attr-defined]
                    best_dist = float(distances[best_idx])
                    if best_dist <= threshold:
                        label = self._known_names[best_idx]
                        confidence = 1.0 - best_dist
            results.append(
                {
                    "bbox": [int(left), int(top), int(right - left), int(bottom - top)],
                    "label": label,
                    "confidence": confidence,
                }
            )
        return results

    def _handle_command(self, command: dict, context, settings: dict) -> None:
        action = command.get("action")
        name = command.get("name")
        frame = context.get("vision_frame")
        if action != "enroll" or not name or frame is None:
            return

        if self.backend == "opencv":
            self._enroll_opencv(name, frame, settings)
        elif self.backend == "face_recognition":
            self._enroll_face_recognition(name, frame, settings)

    def _enroll_opencv(self, name: str, frame, settings: dict) -> None:
        if self._cv2 is None or self._cascade is None:
            return
        cv2 = self._cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(60, 60)
        )
        if len(faces) != 1:
            logger.warning("Enroll requires exactly one face; got %d", len(faces))
            return

        x, y, w, h = faces[0]
        face_roi = gray[y : y + h, x : x + w]

        lbph_settings = settings.get("lbph", {})
        dataset_dir = self._resolve_path(
            lbph_settings.get("dataset_dir", "data/face_dataset")
        )
        dataset_dir.mkdir(parents=True, exist_ok=True)
        person_dir = dataset_dir / name
        person_dir.mkdir(parents=True, exist_ok=True)
        filename = person_dir / f"{int(time.time())}.png"
        cv2.imwrite(str(filename), face_roi)

        model_path = self._resolve_path(
            lbph_settings.get("model_path", "data/face_model.yml")
        )
        label_map_path = self._resolve_path(
            lbph_settings.get("label_map_path", "data/face_labels.json")
        )
        self._train_lbph(dataset_dir, model_path, label_map_path)

    def _train_lbph(
        self, dataset_dir: Path, model_path: Path, label_map_path: Path
    ) -> None:
        if self._cv2 is None or self._recognizer is None:
            return
        cv2 = self._cv2
        faces: list[Any] = []
        labels: list[int] = []
        label_map: dict[int, str] = {}
        label_id = 0

        for person_dir in sorted(dataset_dir.iterdir()):
            if not person_dir.is_dir():
                continue
            label_map[label_id] = person_dir.name
            for img_path in person_dir.glob("*.png"):
                img = cv2.imread(str(img_path), cv2.IMREAD_GRAYSCALE)
                if img is None:
                    continue
                faces.append(img)
                labels.append(label_id)
            label_id += 1

        if not faces:
            return

        try:
            import numpy as np  # type: ignore
        except Exception as exc:  # noqa: BLE001
            logger.warning("NumPy required for LBPH training: %s", exc)
            return
        self._recognizer.train(faces, np.array(labels))
        model_path.parent.mkdir(parents=True, exist_ok=True)
        self._recognizer.save(str(model_path))
        label_map_path.parent.mkdir(parents=True, exist_ok=True)
        label_map_path.write_text(json.dumps(label_map, indent=2), encoding="utf-8")
        self._label_map = label_map

    def _enroll_face_recognition(self, name: str, frame, settings: dict) -> None:
        try:
            import face_recognition  # type: ignore
        except Exception:
            return

        rgb = frame[:, :, ::-1]
        locations = face_recognition.face_locations(rgb)
        encodings = face_recognition.face_encodings(rgb, locations)
        if len(encodings) != 1:
            logger.warning("Enroll requires exactly one face; got %d", len(encodings))
            return

        self._known_embeddings.append(encodings[0].tolist())
        self._known_names.append(name)
        self._save_embeddings()

    def _load_embeddings(self) -> None:
        if self._embeddings_path is None or not self._embeddings_path.exists():
            return
        try:
            payload = json.loads(self._embeddings_path.read_text(encoding="utf-8"))
            self._known_embeddings = payload.get("embeddings", [])
            self._known_names = payload.get("names", [])
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load embeddings: %s", exc)

    def _save_embeddings(self) -> None:
        if self._embeddings_path is None:
            return
        self._embeddings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"nafÆbåö¶æ÷våöæÖW2Â&VÖ&VFFæw2#¢6VÆbåö¶æ÷våöVÖ&VFFæw7Ð¢6VÆbåöVÖ&VFFæw5÷Fçw&FU÷FWB¢§6öâæGV×2ÆöBÂæFVçCÓ"ÂVæ6öFæsÒ'WFbÓ ¢ ¢FVböÆöEöÆ&VÅöÖ6VÆbÂÆ&VÅöÖ÷F¢FÓâF7E¶çBÂ7G%Ó ¢bæ÷BÆ&VÅöÖ÷FæW7G2 ¢&WGW&â·Ð¢G' ¢ÆöBÒ§6öâæÆöG2Æ&VÅöÖ÷Fç&VE÷FWBVæ6öFæsÒ'WFbÓ"¢&WGW&â¶çB²¢bf÷"²ÂbâÆöBæFV×2Ð¢W6WBW6WFöâ2W3¢2æ÷¢$ÄS¢ÆövvW"çv&æær$fÆVBFòÆöBÆ&VÂÖ¢W2"ÂW2¢&WGW&â·Ð ¢FVb÷&W6öÇfU÷F6VÆbÂfÇVS¢7G"ÓâF ¢FÒFfÇVR¢bæ÷BFæ5ö'6öÇWFR ¢FÒ6VÆbç&Wõ÷&ö÷BòF¢&WGW&âF ¢FVb7F÷6VÆbÂ6öçFWBÓâæöæS ¢b6VÆbåöGG÷6W'fW"2æ÷BæöæS ¢G' ¢6VÆbåöGG÷6W'fW"ç6WFF÷vâ¢6VÆbåöGG÷6W'fW"ç6W'fW%ö6Æ÷6R¢W6WBW6WFöâ2W3¢2æ÷¢$ÄS¢ÆövvW"çv&æær$fÆVBFò7F÷f6R&V6övæFöâEE6W'fW#¢W2"ÂW2