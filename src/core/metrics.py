"""Small structured operational snapshot; no network listener required."""

from collections import Counter
from time import perf_counter

counters: Counter[str] = Counter()
latencies: dict[str, float] = {}


def observe(name: str, started: float):
    counters[name] += 1
    latencies[name] = perf_counter() - started


def snapshot():
    return {"counters": dict(counters), "last_duration_seconds": dict(latencies)}
