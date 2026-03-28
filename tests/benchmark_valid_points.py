import time
import random

def _safe_float(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

# Simulated LIDAR data (360 points)
data = {str(i): random.uniform(-10, 100) for i in range(-180, 180)}

def original_process(data):
    distances = {int(k): _safe_float(v, 0.0) for k, v in data.items()}
    valid_points = len([d for d in distances.values() if d > 0])
    return valid_points

def optimized_process(data):
    distances = {}
    valid_points = 0
    for k, v in data.items():
        val = _safe_float(v, 0.0)
        distances[int(k)] = val
        if val > 0:
            valid_points += 1
    return valid_points

n = 10000
start = time.perf_counter()
for _ in range(n):
    original_process(data)
print(f"Original (Dictionary Comprehension + secondary len pass): {time.perf_counter() - start:.4f} s")

start = time.perf_counter()
for _ in range(n):
    optimized_process(data)
print(f"Optimized (Single Pass): {time.perf_counter() - start:.4f} s")
