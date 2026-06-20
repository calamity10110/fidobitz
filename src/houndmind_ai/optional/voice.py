from __future__ import annotations

import json
import logging
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Any

from houndmind_ai.core.module import Module
from houndmind_ai.core.auth import get_shared_auth_token

logger = logging.getLogger(__name__)


class VoiceModule(Module):
    """Voice module with STT (VOSK or SpeechRecognition) and TTS (pidog or pyttsx3).

    Behavior:
    - Listens for microphone input (optional) and/or accepts HTTP commands (`/say`, `/command`).
    - Maps phrases to actions via `settings.voice_assistant.command_map` and `aliases`.
    - If a recognized utterance is a question and a `voice_question_handler` is present in
      `RuntimeContext`, forwards the question and will TTS the response.
    Config (settings.voice_assistant):
    - enabled: bool
    - cooldown_s: float
    - http.enabled/host/port
    - stt.enabled: bool
    - stt.backend: auto|vosk|speech_recognition
    - stt.vosk_model_path: path to VOSK model directory (optional)
    - tts.enabled: bool
    - tts.backend: auto|pyttsx3|pidog
    """

    def __init__(self, name: str, enabled: bool = True, required: bool = False) -> None:
        super().__init__(name, enabled=enabled, required=required)
        self.available = False
        self._last_command_ts = 0.0
        self._http_server: ThreadingHTTPServer | None = None
        self._http_thread: threading.Thread | None = None
        self._pending: list[dict] = []

        # STT/TTS runtime
        self._stt_thread: threading.Thread | None = None
        self._stt_stop = threading.Event()
        self._tts_engine: Any | None = None
        self._pidog: Any | None = None

    def start(self, context) -> None:
        if not self.status.enabled:
            return

        # pidog is optional; if present it may provide robot TTS and other helpers
        try:
            import pidog  # type: ignore[import-not-found]

            self._pidog = pidog
        except Exception:
            self._pidog = None

        self.available = True
        context.set("voice", {"status": "ready"})

        settings = (context.get("settings") or {}).get("voice_assistant", {})

        # Start HTTP control surface if enabled
        try:
            self._maybe_start_http(context, settings)
        except Exception:
            logger.exception("Failed to start voice HTTP server")

        # Start STT listener if requested
        stt_cfg = settings.get("stt", {})
        if stt_cfg.get("enabled", False):
            self._stt_thread = threading.Thread(
                target=self._stt_loop, args=(context,), daemon=True
            )
            self._stt_thread.start()

    def tick(self, context) -> None:
        if not self.available or not self.status.enabled:
            return None

        settings = (context.get("settings") or {}).get("voice_assistant", {})
        if not settings.get("enabled", True):
            return None

        now = time.time()
        cooldown = float(settings.get("cooldown_s", 1.0))
        if now - self._last_command_ts < cooldown:
            return None

        # Handle explicit command injected via context
        command = context.get("voice_command")
        if isinstance(command, dict):
            action = command.get("action") or command.get("pidog_action")
            if action:
                self._apply_action(str(action), context)
                context.set("voice_command", None)
                self._last_command_ts = now
                return None

        mapping = settings.get("command_map", {})
        aliases = settings.get("aliases", {})

        # Drain pending HTTP/recognition items
        if self._pending:
            for item in list(self._pending):
                if "action" in item:
                    self._apply_action(str(item["action"]), context)
                    self._last_command_ts = now
                elif "text" in item:
                    text = str(item["text"])
                    normalized = self._normalize(text)
                    action = self._resolve_action(normalized, mapping, aliases)
                    if action:
                        self._apply_action(action, context)
                    else:
                        # Treat as question if ends with ? or if configured
                        self._handle_utterance(text, context)
                    self._last_command_ts = now
                self._pending.remove(item)

        # Also handle direct `voice_text` in context (other components may set it)
        text = context.get("voice_text")
        if isinstance(text, str) and text.strip():
            normalized = self._normalize(text)
            action = self._resolve_action(normalized, mapping, aliases)
            if action:
                self._apply_action(action, context)
            else:
                self._handle_utterance(text, context)
            context.set("voice_text", None)
            self._last_command_ts = now

        return None

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.lower().strip().split())

    def _resolve_action(self, text: str, mapping: dict, aliases: dict) -> str | None:
        if text in mapping:
            return str(mapping[text])
        alias = aliases.get(text)
        if alias is not None:
            if isinstance(alias, str) and alias in mapping:
                return str(mapping[alias])
            if isinstance(alias, str):
                return alias
        for key, value in mapping.items():
            if key in text:
                return str(value)
        return None

    def _apply_action(self, action: str, context) -> None:
        # Use behavior override so safety/navigation still take priority.
        context.set("behavior_override", action)
        logger.info("Voice command -> %s", action)

    def _handle_utterance(self, text: str, context) -> None:
        # If a question handler exists in context, call it and speak the response.
        handler = context.get("voice_question_handler")
        try:
            # If it's a question (ends with ?) or handler is present, forward
            if (isinstance(text, str) and text.strip().endswith("?")) or callable(
                handler
            ):
                if callable(handler):
                    try:
                        resp = handler(text)
                    except Exception:
                        logger.exception("voice_question_handler failed")
                        resp = None
                else:
                    resp = None
                if isinstance(resp, str) and resp.strip():
                    self._speak(resp)
                else:
                    # default fallback: echo
                    self._speak(f"I heard: {text}")
        except Exception:
            logger.exception("Failed handling utterance")

    def _speak(self, text: str) -> None:
        # Try pidog speak first
        try:
            if self._pidog is not None and hasattr(self._pidog, "speak"):
                try:
                    self._pidog.speak(text)
                    return
                except Exception:
                    logger.exception("pidog.speak failed")
        except Exception:
            logger.exception("pidog TTS check failed")

        # Try pyttsx3
        try:
            if self._tts_engine is None:
                import pyttsx3

                self._tts_engine = pyttsx3.init()
            self._tts_engine.say(text)
            self._tts_engine.runAndWait()
            return
        except Exception:
            logger.exception("pyttsx3 TTS failed")

        logger.info("TTS not available to speak: %s", text)

    def _maybe_start_http(self, context, settings: dict) -> None:
        http_settings = settings.get("http", {})
        if not http_settings.get("enabled", False):
            return
        host = http_settings.get("host", "127.0.0.1")
        port = int(http_settings.get("port", 8091))

        self._auth_token = get_shared_auth_token(context, http_settings)
        if self._auth_token == context.get("shared_auth_token"):
            logger.debug(
                "No auth_token configured for voice server; using generated shared session token."
            )
            if context.get("shared_auth_token_printed") is not True:
                print(f"Generated shared session token: {self._auth_token}")
                context.set("shared_auth_token_printed", True)

        if host == "0.0.0.0":
            if not http_settings.get("danger_allow_public", False):
                logger.error(
                    "Voice server configured to bind to 0.0.0.0, but 'danger_allow_public' is not true. "
                    "Falling back to 127.0.0.1 for security."
                )
                host = "127.0.0.1"
            else:
                logger.warning(
                    "Voice server configured to bind to 0.0.0.0 â ensure network access is restricted or use the generated/configured auth_token"
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
                    self._send_json({"status": "ok"})
                    return
                if not self._auth_ok(params):
                    self._send_json({"ervæWF÷&¦VB'ÒÂ7FGW3ÓC¢&WGW&à¢b'6VBçFÓÒ"÷6# ¢FWBÒ&×2ævWB'FWB"÷"´æöæUÒ³Ð¢bæ÷BFWC ¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢$Ö76ærFWB'ÒÂ7FGW3ÓC¢&WGW&à¢ÖöGVÆRå÷VæFæræVæB²'FWB#¢FWGÒ¢6VÆbå÷6VæEö§6öâ²'7FGW2#¢'VWVVB"Â'FWB#¢FWGÒ¢&WGW&à¢b'6VBçFÓÒ"ö6öÖÖæB# ¢7FöâÒ&×2ævWB&7Föâ"÷"´æöæUÒ³Ð¢bæ÷B7Föã ¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢$Ö76ær7Föâ'ÒÂ7FGW3ÓC¢&WGW&à¢ÖöGVÆRå÷VæFæræVæB²&7Föâ#¢7FöçÒ¢6VÆbå÷6VæEö§6öâ²'7FGW2#¢'VWVVB"Â&7Föâ#¢7FöçÒ¢&WGW&à¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢$æ÷Bf÷VæB'ÒÂ7FGW3ÓCB ¢FVbFõõõ5B6VÆb ¢'6VBÒW&Ç'6R6VÆbçF¢&×2Ò'6U÷2'6VBçVW'¢b'6VBçFÓÒ"÷7FGW2# ¢6VÆbå÷6VæEö§6öâ²'7FGW2#¢&ö²'Ò¢&WGW&à¢bæ÷B6VÆbåöWFöö²&×2 ¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢'VæWF÷&¦VB'ÒÂ7FGW3ÓC¢&WGW&à¢ÆVæwFÒçB6VÆbæVFW'2ævWB$6öçFVçBÔÆVæwF"Â#"¢bÆVæwFâCSsc¢2Ô"ÆÖBFò&WfVçBFõ0¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢%ÆöBFöòÆ&vR'ÒÂ7FGW3ÓC2¢&WGW&à¢&öGÒ6VÆbç&fÆRç&VBÆVæwFæFV6öFR'WFbÓ"bÆVæwFâVÇ6R" ¢b'6VBçFâ²"÷6"Â"ö6öÖÖæB'Ó ¢G' ¢ÆöBÒ§6öâæÆöG2&öGb&öGVÇ6R·Ð¢W6WBW6WFöã ¢ÆöBÒ·Ð¢b'6VBçFÓÒ"÷6# ¢FWBÒÆöBævWB'FWB"¢bæ÷BFWC ¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢$Ö76ærFWB'ÒÂ7FGW3ÓC¢&WGW&à¢ÖöGVÆRå÷VæFæræVæB²'FWB#¢FWGÒ¢6VÆbå÷6VæEö§6öâ²'7FGW2#¢'VWVVB"Â'FWB#¢FWGÒ¢&WGW&à¢7FöâÒÆöBævWB&7Föâ"¢bæ÷B7Föã ¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢$Ö76ær7Föâ'ÒÂ7FGW3ÓC¢&WGW&à¢ÖöGVÆRå÷VæFæræVæB²&7Föâ#¢7FöçÒ¢6VÆbå÷6VæEö§6öâ²'7FGW2#¢'VWVVB"Â&7Föâ#¢7FöçÒ¢&WGW&à¢6VÆbå÷6VæEö§6öâ²&W'&÷"#¢$æ÷Bf÷VæB'ÒÂ7FGW3ÓCB ¢FVbÆöuöÖW76vR6VÆbÂf÷&ÖBÂ¦&w2 ¢&WGW&à ¢G' ¢6W'fW"ÒF&VFætEE6W'fW"÷7BÂ÷'BÂæFÆW"¢W6WBW6WFöâ2W3¢2æ÷¢$ÄS¢ÆövvW"çv&æær$fÆVBFò7F'Bfö6REE6W'fW#¢W2"ÂW2¢&WGW&à¢6VÆbåöGG÷6W'fW"Ò6W'fW ¢6VÆbåöGG÷F&VBÒF&VFæråF&VBF&vWC×6W'fW"ç6W'fUöf÷&WfW"ÂFVÖöãÕG'VR¢6VÆbåöGG÷F&VBç7F'B¢ÆövvW"ææfò%fö6REE6W'fW"Æ7FVææröâW3¢W2"Â÷7BÂ÷'B ¢FVb÷7GEöÆö÷6VÆbÂ6öçFWBÓâæöæS ¢""$&6¶w&÷VæB5EBÆö÷â7W÷'G2dõ4²bfÆ&ÆRÂ÷FW'v6R7VV6&V6övæFöâà ¢&V6övæ¦VBFWB2VæFVBFò6VÆbå÷VæFær2²wFWBs¢ââçÒ6òFRÖà¢F6²Æö÷æFÆW2ÖæræB7Föâçfö6Föâà¢"" ¢6WGFæw2Ò6öçFWBævWB'6WGFæw2"÷"·ÒævWB'fö6Uö767FçB"Â·Ò¢7GEö6frÒ6WGFæw2ævWB'7GB"Â·Ò¢&6¶VæBÒ7GEö6frævWB&&6¶VæB"Â'7VV6÷&V6övæFöâ" ¢2&VfW"7VV6&V6övæFöâæWGv÷&²÷"Æö6Âfç7FÆÆVBVævæW2¢b&6¶VæBâ²&W "speech-recognition"}:
            try:
                import speech_recognition as sr  # type: ignore

                r = sr.Recognizer()
                mic = sr.Microphone()
                with mic as source:
                    r.adjust_for_ambient_noise(source, duration=1)
                logger.info("SpeechRecognition STT started (using default recognizer)")
                while not self._stt_stop.is_set():
                    try:
                        with mic as source:
                            audio = r.listen(source, phrase_time_limit=5)
                        try:
                            text = r.recognize_google(audio)
                        except sr.RequestError:
                            logger.exception("SpeechRecognition service error")
                            continue
                        except sr.UnknownValueError:
                            continue
                        if text:
                            self._pending.append({"text": text})
                    except Exception:
                        logger.exception("STT listen error")
                        time.sleep(0.5)
                return
            except Exception:
                logger.debug("SpeechRecognition not available or failed to initialize")

        # Fallback to VOSK if configured or available
        if backend in {"auwG' ¢g&öÒf÷6²×÷'BÖöFVÂÂ¶ÆF&V6övæ¦W"2GS¢væ÷&P¢×÷'BVFò2GS¢væ÷&P ¢ÖöFVÅ÷FÒ7GEö6frævWB'f÷6µöÖöFVÅ÷F"¢bÖöFVÅ÷F ¢G' ¢ÖöFVÂÒÖöFVÂÖöFVÅ÷F¢ÒVFòåVFò¢7G&VÒÒæ÷Vâ¢f÷&ÖC×VFòççCbÀ¢6ææVÇ3ÓÀ¢&FSÓcÀ¢çWCÕG'VRÀ¢g&ÖW5÷W%ö'VffW#ÓÀ¢¢7G&VÒç7F'E÷7G&VÒ¢&V2Ò¶ÆF&V6övæ¦W"ÖöFVÂÂc¢ÆövvW"ææfò%dõ4²5EB7F'FVB"¢vÆRæ÷B6VÆbå÷7GE÷7F÷æ5÷6WB ¢FFÒ7G&VÒç&VBCÂW6WFöåööåö÷fW&fÆ÷sÔfÇ6R¢bÆVâFFÓÒ ¢6öçFçVP¢b&V2ä66WEvfVf÷&ÒFF ¢&W2Ò&V2å&W7VÇB¢G' ¢¢Ò§6öâæÆöG2&W2¢FWBÒ¢ævWB'FWB"Â""ç7G&¢W6WBW6WFöã ¢FWBÒ" ¢bFWC ¢6VÆbå÷VæFæræVæB²'FWB#¢FWGÒ¢VÇ6S ¢70¢G' ¢7G&VÒç7F÷÷7G&VÒ¢7G&VÒæ6Æ÷6R¢çFW&ÖæFR¢W6WBW6WFöã ¢70¢&WGW&à¢W6WBW6WFöã ¢ÆövvW"æW6WFöâ%dõ4²ÖöFVÂæBfÆVB"¢VÇ6S ¢ÆövvW"ææfò%dõ4²&6¶VæB&WVW7FVB'WBæòÖöFVÂF&÷fFVB"¢W6WBW6WFöã ¢ÆövvW"æFV'Vr%dõ4²æ÷BfÆ&ÆR÷"fÆVBFò×÷'B" ¢ÆövvW"ææfò$æò5EB&6¶VæBfÆ&ÆS²5EBÆö÷WFær" ¢FVb7F÷6VÆbÂ6öçFWBÓâæöæS ¢27F÷5EBF&V@¢G' ¢b6VÆbå÷7GE÷F&VB2æ÷BæöæS ¢6VÆbå÷7GE÷7F÷ç6WB¢6VÆbå÷7GE÷F&VBæ¦öâFÖV÷WCÓ¢W6WBW6WFöã ¢ÆövvW"æW6WFöâ$fÆVBFò7F÷5EBF&VB" ¢b6VÆbåöGG÷6W'fW"2æ÷BæöæS ¢G' ¢6VÆbåöGG÷6W'fW"ç6WFF÷vâ¢6VÆbåöGG÷6W'fW"ç6W'fW%ö6Æ÷6R¢W6WBW6WFöâ2W3¢2æ÷¢$ÄS¢ÆövvW"çv&æær$fÆVBFò7F÷fö6REE6W'fW#¢W2"ÂW2 ¢27F÷GG72VævæRb&W6Vç@¢G' ¢b6VÆbå÷GG5öVævæR2æ÷BæöæS ¢G' ¢6VÆbå÷GG5öVævæRç7F÷¢W6WBW6WFöã ¢70¢W6WBW6WFöã ¢70 