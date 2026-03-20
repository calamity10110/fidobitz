import time
from houndmind_ai.mapping.mapper import MappingModule

def old_method(items):
    diffs = [abs(items[i + 1][0] - items[i][0]) for i in range(len(items) - 1)]
    return [d for d in diffs if d > 0]

def optimized_method(items):
    return [d for a, b in zip(items, items[1:]) if (d := abs(b[0] - a[0])) > 0]

def run_benchmark():
    # Generate 1,000 synthetic scanner angles
    angles = {str(i): float((i * 13) % 150) for i in range(1000)}

    # Pre-parse the items as done in _analyze_scan_openings
    items = []
    for key, dist in angles.items():
        if float(dist) > 0:
            items.append((int(float(key)), float(dist)))
    items.sort(key=lambda it: it[0])

    print("Running benchmarks for traversal code path (10,000 iterations each)...")

    start = time.time()
    for _ in range(10000):
        old_method(items)
    end = time.time()
    old_time = end - start
    print(f"Original method: {old_time:.4f} seconds")

    start = time.time()
    for _ in range(10000):
        optimized_method(items)
    end = time.time()
    new_time = end - start
    print(f"Optimized method: {new_time:.4f} seconds")

    improvement = ((old_time - new_time) / old_time) * 100
    print(f"Improvement: ~{improvement:.2f}% speedup")

if __name__ == "__main__":
    run_benchmark()
