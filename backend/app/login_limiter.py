"""Bounded per-process throttle. Production runs exactly one API worker."""
from collections import OrderedDict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException


class LoginLimiter:
    def __init__(self):
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = Lock()

    def check(self, address: str, limit: int) -> None:
        now = monotonic()
        with self._lock:
            while self._attempts and next(iter(self._attempts.values()))[-1] <= now - 60:
                self._attempts.popitem(last=False)
            attempts = self._attempts.setdefault(address, deque())
            self._attempts.move_to_end(address)
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if len(attempts) >= max(1, limit):
                raise HTTPException(429, detail={"code": "RATE_LIMITED", "message": "Too many sign-in attempts. Try again in a minute."},
                                    headers={"Retry-After": "60"})
            attempts.append(now)
            if len(self._attempts) > 10_000:
                self._attempts.popitem(last=False)


login_limiter = LoginLimiter()
