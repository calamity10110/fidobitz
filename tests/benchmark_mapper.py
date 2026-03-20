import time
import math
import sys
from houndmind_ai.mapping.mapper import MappingModule

def benchmark_ingest_into_grid():
    module = MappingModule("MappingModule")

    # Simulate a realistic set of scan angles: e.g., -60 to 60 by 15 degrees
    angles = {}
    for i in range(-60, 61, 15):
        angles[str(i)] = 100.0 # distance = 100 cm

    settings = {"cell_size_cm": 10.0, "grid_size": [100, 100]}

    # Pre-warm
    for _ in range(100):
        mapping_state = {"grid": {"cells": {}}}
        module._ingest_into_grid(angles, settings, mapping_state)

    iterations = 50000
    start_time = time.perf_counter()

    for _ in range(iterations):
        mapping_state = {"grid": {"cells": {}}}
        module._ingest_into_grid(angles, settings, mapping_state)

    end_time = time.perf_counter()

    total_time = end_time - start_time
    print(f"Total time for {iterations} iterations: {total_time:.4f} seconds")
    print(f"Average time per iteration: {(total_time / iterations) * 1000:.4f} ms")

if __name__ == "__main__":
    benchmark_ingest_into_grid()
