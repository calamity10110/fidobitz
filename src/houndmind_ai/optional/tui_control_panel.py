import curses
import time
import threading
import logging
from houndmind_ai.core.module import Module

logger = logging.getLogger(__name__)

class TUIControlPanelModule(Module):
    """Optional Terminal User Interface (TUI) control panel.

    Provides a live console dashboard for humans using the system locally.
    Uses the curses library. Note that this takes over standard output.
    """

    def __init__(self, name: str, enabled: bool = True, required: bool = False) -> None:
        super().__init__(name, enabled=enabled, required=required)
        self.available = False
        self._thread = None
        self._stop_event = threading.Event()
        self._snapshot = {}
        self._last_ts = 0.0
        self._vision_fps = None
        self._last_vision_ts = None
        self._lock = threading.Lock()

    def start(self, context) -> None:
        if not self.status.enabled:
            return

        # Avoid starting if we don't have a true TTY or if it's disabled in settings
        settings = (context.get("settings") or {}).get("tui", {})
        if not settings.get("enabled", False):
            return

        self.available = True
        self._stop_event.clear()

        # Start the curses loop in a background thread so it doesn't block the main tick
        self._thread = threading.Thread(target=self._run_tui, daemon=True)
        self._thread.start()
        context.set("tui_status", {"status": "ready"})
        logger.info("TUI Control Panel started.")

    def tick(self, context) -> None:
        if not self.available or not self.status.enabled:
            return

        settings = (context.get("settings") or {}).get("tui", {})
        interval = float(settings.get("refresh_interval_s", 0.2))
        now = time.time()

        if now - self._last_ts < interval:
            return

        # Calculate FPS similarly to the web dashboard
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
            "tick_hz_actual": runtime_perf.get("tick_hz_actual"),
            "vision_fps": self._vision_fps,
            "cpu_load_1m": health_status.get("load_1m"),
            "cpu_temp_c": health_status.get("temp_c"),
            "mem_used_pct": health_status.get("mem_used_pct"),
        }

        with self._lock:
            self._snapshot = {
                "trace_id": context.get("trace_id", "N/A"),
                "performance": performance,
                "behavior": context.get("behavior_action", {}),
                "navigation": context.get("navigation_action", {}),
                "faces": len(context.get("faces", []) or []),
            }

        self._last_ts = now

    def stop(self, context) -> None:
        if self._thread is not None:
            self._stop_event.set()
            self._thread.join(timeout=2.0)
            self._thread = None
            logger.info("TUI Control Panel stopped.")

    def _run_tui(self):
        try:
            # We use wrapper to ensure terminal state is restored on exit/error
            curses.wrapper(self._tui_loop)
        except Exception as e:
            logger.error("TUI crashed: %s", e)

    def _tui_loop(self, stdscr):
        # Initial setup
        curses.curs_set(0) # Hide cursor
        stdscr.nodelay(1)  # Non-blocking input
        curses.start_color()
        curses.use_default_colors()

        # Color pairs
        curses.init_pair(1, curses.COLOR_CYAN, -1)   # Header
        curses.init_pair(2, curses.COLOR_GREEN, -1)  # Success/Values
        curses.init_pair(3, curses.COLOR_YELLOW, -1) # Warnings
        curses.init_pair(4, curses.COLOR_RED, -1)    # Errors

        while not self._stop_event.is_set():
            # Handle resize
            max_y, max_x = stdscr.getmaxyx()

            stdscr.erase()

            with self._lock:
                snap = self._snapshot.copy()

            # Draw Header
            title = " HoundMind TUI Control Panel "
            stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
            stdscr.addstr(0, max((max_x - len(title)) // 2, 0), title[:max_x])
            stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)

            if max_y > 2:
                stdscr.addstr(2, 2, f"Trace ID: {snap.get('trace_id', 'N/A')}")

            # Draw Performance Stats
            if max_y > 5:
                perf = snap.get("performance", {})
                stdscr.attron(curses.A_BOLD)
                stdscr.addstr(4, 2, "Performance Telemetry")
                stdscr.attroff(curses.A_BOLD)

                tick_hz = perf.get("tick_hz_actual")
                tick_str = f"{tick_hz:.1f} Hz" if tick_hz else "N/A"
                stdscr.addstr(5, 4, "Tick Rate : ")
                stdscr.attron(curses.color_pair(2))
                stdscr.addstr(tick_str)
                stdscr.attroff(curses.color_pair(2))

                v_fps = perf.get("vision_fps")
                fps_str = f"{v_fps:.1f} FPS" if v_fps else "N/A"
                stdscr.addstr(6, 4, "Vision FPS: ")
                stdscr.attron(curses.color_pair(2))
                stdscr.addstr(fps_str)
                stdscr.attroff(curses.color_pair(2))

                mem = perf.get("mem_used_pct")
                mem_str = f"{mem:.1f}%" if mem else "N/A"
                stdscr.addstr(7, 4, "Memory    : ")
                stdscr.attron(curses.color_pair(3) if mem and mem > 80 else curses.color_pair(2))
                stdscr.addstr(mem_str)
                stdscr.attroff(curses.color_pair(3) if mem and mem > 80 else curses.color_pair(2))

                cpu = perf.get("cpu_temp_c")
                cpu_str = f"{cpu:.1f}C" if cpu else "N/A"
                stdscr.addstr(8, 4, "CPU Temp  : ")
                stdscr.attron(curses.color_pair(4) if cpu and cpu > 75 else curses.color_pair(2))
                stdscr.addstr(cpu_str)
                stdscr.attroff(curses.color_pair(4) if cpu and cpu > 75 else curses.color_pair(2))

            # Draw Actions
            if max_y > 11:
                stdscr.attron(curses.A_BOLD)
                stdscr.addstr(10, 2, "Current State")
                stdscr.attroff(curses.A_BOLD)

                nav = snap.get("navigation", {})
                beh = snap.get("behavior", {})

                nav_state = nav.get("action", "Idle") if nav else "Idle"
                beh_state = beh.get("state", "Idle") if beh else "Idle"

                stdscr.addstr(11, 4, f"Navigation: {nav_state}")
                stdscr.addstr(12, 4, f"Behavior  : {beh_state}")
                stdscr.addstr(13, 4, f"Faces seen: {snap.get('faces', 0)}")

            # Footer / Help
            if max_y > 15:
                footer = "Press 'q' to exit TUI (Server continues running)"
                stdscr.addstr(max_y - 1, max((max_x - len(footer)) // 2, 0), footer[:max_x], curses.color_pair(3))

            stdscr.refresh()

            # Check for input
            c = stdscr.getch()
            if c == ord('q'):
                self._stop_event.set()
                break

            time.sleep(0.1)
