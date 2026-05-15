import time
from collections import defaultdict

_store: dict[int, list[float]] = defaultdict(list)

VOICE_LIMIT = 20
VOICE_WINDOW = 3600  # 1 hour


def check_voice_rate_limit(user_id: int) -> bool:
    """Returns True if the request is allowed, False if rate-limited. Mutates state."""
    now = time.monotonic()
    window_start = now - VOICE_WINDOW
    timestamps = _store[user_id]
    # Drop expired timestamps
    _store[user_id] = [t for t in timestamps if t > window_start]
    if len(_store[user_id]) >= VOICE_LIMIT:
        return False
    _store[user_id].append(now)
    return True
