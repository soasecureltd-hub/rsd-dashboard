"""Failed-login rate limiting (in memory).

Three sliding-window limits on FAILED attempts, checked before any password
work is done:

  * account + IP : stops guessing one account's password from one place,
                   without letting a stranger lock the real owner out
                   (their own IP has its own counter);
  * IP           : stops one client trying many accounts (password spraying);
  * account      : a high ceiling that slows a distributed attack on a single
                   account from many IPs.

A successful login clears that account's account+IP counter.

Limits are per process: with several workers/instances each keeps its own
counters (Render's single instance is fine). Swap the storage for Redis if
the backend is scaled out.
"""
import math
import threading
import time
from collections import deque
from typing import Callable, Deque, Dict, Tuple

WINDOW_SECONDS = 15 * 60
LIMITS = {
    "account_ip": 5,
    "ip": 30,
    "account": 50,
}

Key = Tuple[str, str]


class LoginRateLimiter:
    def __init__(self, limits: Dict[str, int] = None, window_seconds: float = WINDOW_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self.limits = dict(limits or LIMITS)
        self.window = window_seconds
        self.clock = clock
        self._failures: Dict[Key, Deque[float]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _keys(email: str, ip: str):
        account = (email or "").strip().lower()
        return {
            "account_ip": ("account_ip", f"{account}|{ip}"),
            "ip": ("ip", ip),
            "account": ("account", account),
        }

    def _prune(self, key: Key, now: float) -> Deque[float]:
        q = self._failures.get(key)
        if q is None:
            return deque()
        while q and now - q[0] >= self.window:
            q.popleft()
        if not q:
            del self._failures[key]
        return q

    def retry_after(self, email: str, ip: str) -> int:
        """Seconds until another attempt is allowed; 0 if allowed now."""
        now = self.clock()
        wait = 0.0
        with self._lock:
            for name, key in self._keys(email, ip).items():
                q = self._prune(key, now)
                if len(q) >= self.limits[name]:
                    # Allowed again once enough old failures leave the window.
                    oldest_blocking = q[len(q) - self.limits[name]]
                    wait = max(wait, self.window - (now - oldest_blocking))
        return math.ceil(wait) if wait > 0 else 0

    def record_failure(self, email: str, ip: str) -> None:
        now = self.clock()
        with self._lock:
            for key in self._keys(email, ip).values():
                self._prune(key, now)
                self._failures.setdefault(key, deque()).append(now)

    def record_success(self, email: str, ip: str) -> None:
        with self._lock:
            self._failures.pop(self._keys(email, ip)["account_ip"], None)

    def reset(self) -> None:
        with self._lock:
            self._failures.clear()


login_limiter = LoginRateLimiter()
