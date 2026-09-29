"""Simple profiling utilities for liverefresh views."""

import time
from contextlib import contextmanager


@contextmanager
def timed(spans, name):
    """Record elapsed time for a named operation into spans dict."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        spans[name] = elapsed
