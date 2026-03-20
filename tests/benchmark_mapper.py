import time
import math
from houndmind_ai.mapping.mapper import MappingModule

def run_benchmark():
    settings = {"cell_size_cm": 10.0, "grid_size": [100, 100], "opening_min_width_cm": 60, "opening_max_width_cm": 120, "opening_cell_conf_min": 0.6, "safe_path_min_width_cm": 40, "safe_path_max_width_cm": 200, "safe_path_cell_conf_min": 0.5, "scan_step_deg": 0.0, "safe_path_score_weight_width": 0.6, "safe_path_score_weight_distance": 0.4}

    # Generate 100 angles
    angles = {str(i): float((i * 13) % 150) for i in range(100)}

    start = time.time()
    for _ in range(1000):
        MappingModule._analyze_scan_openings(angles, settings)
    end = time.time()
    print(f"Time for old _analyze_scan_openings: {end - start:.4f}s")

    def fast_analyze_scan_openings(angles, settings):
        if not isinstance(angles, dict) or not angles:
            return [], [], None

        min_open_width_cm = float(settings.get("opening_min_width_cm", 60))
        max_open_width_cm = float(settings.get("opening_max_width_cm", 120))
        min_open_conf = float(settings.get("opening_cell_conf_min", 0.6))
        min_safe_width_cm = float(settings.get("safe_path_min_width_cm", 40))
        max_safe_width_cm = float(settings.get("safe_path_max_width_cm", 200))
        min_safe_conf = float(settings.get("safe_path_cell_conf_min", 0.5))

        items = []
        for key, dist in angles.items():
            try:
                yaw = int(float(key))
                distance = float(dist)
            except Exception:
                continue
            if distance <= 0:
                continue
            items.append((yaw, distance))

        if not items:
            return [], [], None

        items.sort(key=lambda it: it[0])
        openings = []
        safe_paths = []

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

        for yaw, dist in items:
            width_cm = dist * width_multiplier if dist > 0 else 0.0
            conf = dist / 200.0 if dist < 200.0 else 1.0

            entry = {
                "yaw": yaw,
                "distance_cm": dist,
                "width_cm": width_cm,
                "confidence": conf,
            }
            if min_open_width_cm <= width_cm <= max_open_width_cm and conf >= min_open_conf:
                openings.append(entry)
            if min_safe_width_cm <= width_cm <= max_safe_width_cm and conf >= min_safe_conf:
                safe_paths.append(entry)

        best_path = None
        if safe_paths:
            weight_width = float(settings.get("safe_path_score_weight_width", 0.6))
            weight_distance = float(settings.get("safe_path_score_weight_distance", 0.4))

            best_score = -1.0
            for entry in safe_paths:
                score = (entry["width_cm"] * weight_width) + (
                    entry["distance_cm"] * weight_distance
                )
                if score > best_score:
                    best_score = score
                    best_path = {**entry, "score": score}

        return openings, safe_paths, best_path

    start2 = time.time()
    for _ in range(1000):
        fast_analyze_scan_openings(angles, settings)
    end2 = time.time()
    print(f"Time for fast_analyze_scan_openings with loop: {end2 - start2:.4f}s")
run_benchmark()
