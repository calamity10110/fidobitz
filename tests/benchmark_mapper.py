import random
import timeit

from houndmind_ai.mapping.mapper import MappingModule

def test_mapper_scan_openings_smoke():
    """
    Smoke test to verify that the newly optimized _analyze_scan_openings method
    continues to run correctly without regressions.
    """
    random.seed(42)
    # Generate 1000 items similar to scan data: dictionary mapping str(yaw) to distance
    angles = {str(random.randint(0, 360)): random.uniform(10.0, 200.0) for _ in range(1000)}
    settings = {
        "scan_step_deg": 0.0, # Forces calculation of step_deg
        "opening_min_width_cm": 60,
        "opening_max_width_cm": 120,
        "opening_cell_conf_min": 0.6,
        "safe_path_min_width_cm": 40,
        "safe_path_max_width_cm": 200,
        "safe_path_cell_conf_min": 0.5,
    }

    openings, safe_paths, best_path = MappingModule._analyze_scan_openings(angles, settings)

    # Simple assertion to make sure it did work
    assert isinstance(openings, list)
    assert isinstance(safe_paths, list)

def run_standalone_benchmark():
    """
    A standalone benchmark script comparing the original and optimized implementations.
    This demonstrates the performance improvement achieved by using zip() instead of
    range() based traversal.
    """
    random.seed(42)
    items = [(random.randint(0, 360), random.uniform(10.0, 200.0)) for _ in range(1000)]
    items.sort(key=lambda x: x[0])

    def original_method(items):
        step_deg = 0.0
        if step_deg <= 0.0 and len(items) > 1:
            diffs = [abs(items[i + 1][0] - items[i][0]) for i in range(len(items) - 1)]
            diffs = [d for d in diffs if d > 0]
            if diffs:
                diffs.sort()
                mid = len(diffs) // 2
                step_deg = diffs[mid]
        return step_deg

    def optimized_method(items):
        step_deg = 0.0
        if step_deg <= 0.0 and len(items) > 1:
            diffs = [d for a, b in zip(items, items[1:]) if (d := abs(b[0] - a[0])) > 0]
            if diffs:
                diffs.sort()
                mid = len(diffs) // 2
                step_deg = diffs[mid]
        return step_deg

    n = 10000
    time_orig = timeit.timeit(lambda: original_method(items), number=n)
    time_opt = timeit.timeit(lambda: optimized_method(items), number=n)

    print("\n--- Benchmark Results: Scan Openings Diffs ---")
    print(f"Original method (range len traversal): {time_orig:.4f} seconds (for {n} iterations)")
    print(f"Optimized method (zip traversal):      {time_opt:.4f} seconds (for {n} iterations)")
    print(f"Improvement:                           {(time_orig - time_opt) / time_orig * 100:.2f}%\n")

if __name__ == '__main__':
    run_standalone_benchmark()
