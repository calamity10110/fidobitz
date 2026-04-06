from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path

from houndmind_ai.core.module import Module

logger = logging.getLogger(__name__)


def _build_trig_cache() -> dict[str, tuple[float, float]]:
    cache = {}
    for d in range(-360, 361):
        cos_val = math.cos(math.radians(d))
        sin_val = math.sin(math.radians(d))
        cache[str(d)] = (cos_val, sin_val)
        cache[f"{d}.0"] = (cos_val, sin_val)
    return cache


class MappingModule(Module):
    """Lightweight mapping module with optional home map persistence.

    This does not implement full SLAM. It stores sensor snapshots and can save
    a "Home Map" file for later analysis or future navigation upgrades.
    """

    _TRIG_CACHE_STR: dict[str, tuple[float, float]] = _build_trig_cache()

    def __init__(self, name: str, enabled: bool = True, required: bool = False) -> None:
        super().__init__(name, enabled=enabled, required=required)
        self.last_save_ts = 0.0

    def tick(self, context) -> None:
        settings = (context.get("settings") or {}).get("mapping", {})
        if not settings.get("enabled", True):
            return

        # Read sensor data and store a basic history for later mapping work.
        sensors = context.get("sensors") or {}
        mapping_state = context.get("mapping_state") or {"samples": []}

        scan_latest = context.get("scan_latest") or {}
        scan_angles = (
            scan_latest.get("angles", {}) if isinstance(scan_latest, dict) else {}
        )
        openings, safe_paths, best_path = self._analyze_scan_openings(
            scan_angles, settings
        )

        sample = {
            "timestamp": time.time(),
            "distance_cm": sensors.get("distance"),
            "touch": sensors.get("touch"),
            "sound": sensors.get("sound_detected"),
            "acc": sensors.get("acc"),
            "gyro": sensors.get("gyro"),
            "openings": openings,
            "safe_paths": safe_paths,
            "best_path": best_path,
        }
        mapping_state["samples"].append(sample)
        max_samples = int(settings.get("sample_history_max", 500))
        if max_samples > 0 and len(mapping_state["samples"]) > max_samples:
            mapping_state["samples"] = mapping_state["samples"][-max_samples:]
        max_age_s = float(settings.get("sample_max_age_s", 0))
        if max_age_s > 0:
            cutoff = time.time() - max_age_s
            samples = mapping_state["samples"]
            # ⚡ Bolt: Use forward iteration to find the first sample newer than cutoff.
            # This slices chronologically ordered lists in O(K) where K is the number
            # of pruned items, instead of O(N) reverse iteration.
            for i in range(len(samples)):
                if samples[i].get("timestamp", 0) >= cutoff:
                    mapping_state["samples"] = samples[i:]
                    break
            else:
                mapping_state["samples"] = []
        context.set("mapping_state", mapping_state)

        context.set(
            "mapping_openings",
            {
                "timestamp": sample["timestamp"],
                "openings": openings,
                "safe_paths": safe_paths,
                "best_path": best_path,
            },
        )

        # Optionally ingest sweep angles into a simple occupancy grid for
        # lightweight map-aware avoidance. This keeps a histogram of observed
        # hits by grid cell (coordinates in centimeters relative to robot).
        if bool(settings.get("grid_enabled", True)):
            try:
                self._ingest_into_grid(scan_angles, settings, mapping_state)
            except Exception:  # noqa: BLE001
                logger.debug("Grid ingestion failed", exc_info=True)

        # Optional path-planning hook (future expansion).
        if settings.get("path_planning_enabled", False):
            hook = context.get("path_planning_hook")
            if callable(hook):
                try:
                    plan = hook(mapping_state, sample, settings)
                    context.set("path_planning", plan)
                except Exception:  # noqa: BLE001
                    logger.debug("Path planning hook failed", exc_info=True)

        # Persist a home map snapshot on a configured interval.
        save_interval = settings.get("home_map_save_interval_s", 30)
        now = time.time()
        if (
            settings.get("home_map_enabled", False)
            and now - self.last_save_ts >= save_interval
        ):
            self.save_home_map(mapping_state, settings)
            self.last_save_ts = now

    def save_home_map(self, mapping_state: dict, settings: dict) -> None:
        """Persist mapping samples to a JSON file for later analysis."""
        output_path = Path(settings.get("home_map_path", "data/home_map.json"))
        if not output_path.is_absolute():
            output_path = Path(__file__).resolve().parents[3] / output_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        samples = list(mapping_state.get("samples", []))
        max_samples = int(settings.get("home_map_max_samples", 0))
        max_age_s = float(settings.get("home_map_max_age_s", 0))
        if max_age_s > 0:
            cutoff = time.time() - max_age_s
            for i in range(len(samples)):
                if samples[i].get("timestamp", 0) >= cutoff:
                    samples = samples[i:]
                    break
            else:
                samples = []
        if max_samples > 0 and len(samples) > max_samples:
            samples = samples[-max_samples:]

        payload = {
            "meta": {
                "saved_at": time.time(),
                "cell_size_cm": settings.get("cell_size_cm", 10),
                "grid_size": settings.get("grid_size", [100, 100]),
                "opening_min_width_cm": settings.get("opening_min_width_cm", 60),
                "safe_path_min_width_cm": settings.get("safe_path_min_width_cm", 40),
                "safe_path_score_weight_width": settings.get(
                    "safe_path_score_weight_width", 0.6
                ),
                "safe_path_score_weight_distance": settings.get(
                    "safe_path_score_weight_distance", 0.4
                ),
                "home_map_max_samples": max_samples,
                "home_map_max_age_s": max_age_s,
            },
            "samples": samples,
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Saved home map to %s", output_path)

    def stop(self, context) -> None:
        settings = (context.get("settings") or {}).get("mapping", {})
        if settings.get("home_map_enabled", False):
            mapping_state = context.get("mapping_state") or {"samples": []}
            self.save_home_map(mapping_state, settings)

    def _ingest_into_grid(
        self, angles: dict, settings: dict, mapping_state: dict
    ) -> None:
        if not isinstance(angles, dict) or not angles:
            return
        cell_size_cm = float(settings.get("cell_size_cm", 10.0))
        inv_cell_size = 1.0 / cell_size_cm if cell_size_cm else 0.0
        grid_size = settings.get("grid_size", [100, 100])
        try:
            gx = int(grid_size[0])
            gy = int(grid_size[1])
        except Exception:
            gx, gy = 100, 100
        half_x = gx // 2
        half_y = gy // 2

        grid = mapping_state.get("grid") or {"cells": {}}
        cells = grid.get("cells") or {}

        # Pre-calculate divisor outside the loop
        inv_cell_size = 1.0 / cell_size_cm if cell_size_cm > 0 else 0.0

        # Localize cache lookup to avoid self. overhead
        trig_cache_str = self._TRIG_CACHE_STR

        # ⚡ Bolt: Optimize cache lookup by doing str(key) check BEFORE parsing
        # float/int values for yaw. This avoids `float()`, `int()`, and `str()`
        # overhead for the vast majority of cached integer degree lookups.
        for key, raw in angles.items():
            cached = trig_cache_str.get(key)
            if cached is not None:
                c, s = cached
                try:
                    dist = float(raw)
                except Exception:
                    continue
                if dist <= 0:
                    continue
            else:
                str_key = str(key)
                if str_key in trig_cache_str:
                    c, s = trig_cache_str[str_key]
                    try:
                        dist = float(raw)
                    except Exception:
                        continue
                    if dist <= 0:
                        continue
                else:
                    try:
                        yaw = int(float(key))
                        dist = float(raw)
                    except Exception:
                        continue
                    if dist <= 0:
                        continue
                    # Convert polar (distance cm, yaw deg) to grid indices. Yaw is
                    # degrees where 0 = forward, positive = left.
                    rad = math.radians(yaw)
                    c, s = math.cos(rad), math.sin(rad)

            # ⚡ Bolt: Avoid multiple multiplications per iteration by combining
            # distance with the inverted cell size scalar early.
            dist_inv = dist * inv_cell_size
            ix = int(round(dist_inv * s))  # left
            iy = int(round(dist_inv * c))  # forward

            # Bound to grid size
            if abs(ix) > half_x or abs(iy) > half_y:
                continue
            k = (ix, iy)
            cells[k] = cells.get(k, 0) + 1

        grid["cells"] = cells
        mapping_state["grid"] = grid

    @staticmethod
    def _analyze_scan_openings(
        angles: dict, settings: dict
    ) -> tuple[list[dict], list[dict], dict | None]:
        if not isinstance(angles, dict) or not angles:
            return [], [], None

        min_open_width_cm = float(settings.get("opening_min_width_cm", 60))
        max_open_width_cm = float(settings.get("opening_max_width_cm", 120))
        min_open_conf = float(settings.get("opening_cell_conf_min", 0.6))
        min_safe_width_cm = float(settings.get("safe_path_min_width_cm", 40))
        max_safe_width_cm = float(settings.get("safe_path_max_width_cm", 200))
        min_safe_conf = float(settings.get("safe_path_cell_conf_min", 0.5))

        items = []
        # ⚡ Bolt: Localize append method for performance in tight loop
        append_item = items.append
        for key, dist in angles.items():
            try:
                # ⚡ Bolt: 'Fast path' try-except block, check distance > 0 directly
                distance = float(dist)
                if distance > 0:
                    append_item((int(float(key)), distance))
            except Exception:
                pass

        if not items:
            return [], [], None

        items.sort(key=lambda it: it[0])
        openings: list[dict] = []
        safe_paths: list[dict] = []
        # ⚡ Bolt: Localize list appends
        append_open = openings.append
        append_safe = safe_paths.append

        step_deg = float(settings.get("scan_step_deg", 0.0))
        if step_deg <= 0.0 and len(items) > 1:
            diffs = [d for a, b in zip(items, items[1:]) if (d := abs(b[0] - a[0])) > 0]
            if diffs:
                diffs.sort()
                mid = len(diffs) // 2
                step_deg = diffs[mid]
        if step_deg <= 0.0:
            step_deg = 15.0

        width_multiplier = step_deg * 0.0174533
        # ⚡ Bolt: Replace division by 200.0 with reciprocal multiplication
        inv_200 = 0.005

        for yaw, dist in items:
            # dist is guaranteed > 0 from the filtering loop above
            width_cm = dist * width_multiplier
            conf = dist * inv_200 if dist < 200.0 else 1.0

            # ⚡ Bolt: Defer dictionary allocation until after condition checks
            is_open = (min_open_width_cm <= width_cm <= max_open_width_cm) and (conf >= min_open_conf)
            is_safe = (min_safe_width_cm <= width_cm <= max_safe_width_cm) and (conf >= min_safe_conf)

            if is_open or is_safe:
                entry = {
                    "yaw": yaw,
                    "distance_cm": dist,
                    "width_cm": width_cm,
                    "confidence": conf,
                }
                if is_open:
                    append_open(entry)
                if is_safe:
                    append_safe(entry)

        best_path = None
        if safe_paths:
            weight_width = float(settings.get("safe_path_score_weight_width", 0.6))
            weight_distance = float(
                settings.get("safe_path_score_weight_distance", 0.4)
            )
            best_score = -1.0
            for entry in safe_paths:
                score = (entry["width_cm"] * weight_width) + (
                    entry["distance_cm"] * weight_distance
                )
                if score > best_score:
                    best_score = score
                    best_path = {**entry, "score": score}

        return openings, safe_paths, best_path
