from collections import defaultdict, deque
from time import time


_REQUESTS: dict[str, deque[float]] = defaultdict(deque)


def allow_request(key: str, limit: int = 20, window_seconds: int = 60) -> bool:
    now = time()
    bucket = _REQUESTS[key]

    while bucket and now - bucket[0] > window_seconds:
        bucket.popleft()

    if len(bucket) >= limit:
        return False

    bucket.append(now)
    return True
