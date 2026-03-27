import time
import string
import random

# Benchmark 1: generator vs list comp and explicit loop for mapping and reducing


def test_generator(distances):
    return sum(1 for dist in distances.values() if dist > 0)


def test_list_comp(distances):
    return len([d for d in distances.values() if d > 0])


def test_for_loop(distances):
    c = 0
    for d in distances.values():
        if d > 0:
            c += 1
    return c


# Benchmark 2: any() vs simple iteration / inline matching


def test_any(s):
    return any(c in s for c in ["a", "b", "c"])


def test_or(s):
    return "a" in s or "b" in s or "c" in s


def test_any_list(arr):
    return any(x == 5 for x in arr)


def test_for_list(arr):
    for x in arr:
        if x == 5:
            return True
    return False


if __name__ == "__main__":
    print("--- Benchmark: sum(1 for ...) vs list comp vs for loop ---")
    distances = {i: random.uniform(-10, 100) for i in range(-60, 61, 5)}
    n = 100000

    start = time.perf_counter()
    for _ in range(n):
        test_generator(distances)
    print(f"Generator (sum(1 for ...)): {time.perf_counter() - start:.4f} s")

    start = time.perf_counter()
    for _ in range(n):
        test_list_comp(distances)
    print(f"List comp (len([x for ...])): {time.perf_counter() - start:.4f} s")

    start = time.perf_counter()
    for _ in range(n):
        test_for_loop(distances)
    print(f"Explicit For loop: {time.perf_counter() - start:.4f} s")

    print("\n--- Benchmark: any() generator vs explicit ---")
    s = string.ascii_lowercase[10:]
    n = 1000000

    start = time.perf_counter()
    for _ in range(n):
        test_any(s)
    print(f"Any() generator: {time.perf_counter() - start:.4f} s")

    start = time.perf_counter()
    for _ in range(n):
        test_or(s)
    print(f"Explicit 'or': {time.perf_counter() - start:.4f} s")

    arr = list(range(10))
    start = time.perf_counter()
    for _ in range(n):
        test_any_list(arr)
    print(f"Any() on list: {time.perf_counter() - start:.4f} s")

    start = time.perf_counter()
    for _ in range(n):
        test_for_list(arr)
    print(f"Explicit for loop on list: {time.perf_counter() - start:.4f} s")
