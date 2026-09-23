import time
import threading
from typing import Optional, Dict
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

def get_client_ip(request: Request) -> str:
    """Extract real client IP considering forward headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"

limiter = Limiter(key_func=get_client_ip)



class AuthBackoffTracker:
    """
    Thread-safe tracker for failed authentication attempts.
    Applies per-account and per-IP tracking with exponential backoff
    rather than a permanent or hard account lockout.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._records: Dict[str, dict] = {}

    def _get_key(self, prefix: str, identifier: str) -> str:
        return f"{prefix}:{identifier.lower().strip()}"

    def check_backoff(self, username: Optional[str], ip: str) -> Optional[int]:
        """
        Checks if the account or IP is currently in an exponential backoff cooldown.
        Returns the number of seconds remaining, or None if allowed.
        """
        if not limiter.enabled:
            return None

        now = time.time()
        keys_to_check = [self._get_key("ip", ip)]
        if username:
            keys_to_check.append(self._get_key("account", username))

        max_remaining = 0
        with self._lock:
            for k in keys_to_check:
                entry = self._records.get(k)
                if entry and entry.get("backoff_until", 0) > now:
                    remaining = int(entry["backoff_until"] - now) + 1
                    if remaining > max_remaining:
                        max_remaining = remaining

        return max_remaining if max_remaining > 0 else None

    def record_failure(self, username: Optional[str], ip: str) -> int:
        """
        Records a failed authentication attempt for both IP and Account.
        Calculates exponential backoff if failure threshold is reached.
        Returns the enforced delay in seconds (0 if below threshold).
        """
        if not limiter.enabled:
            return 0

        now = time.time()
        base_sec = settings.AUTH_EXPONENTIAL_BACKOFF_BASE_SECONDS
        threshold = settings.AUTH_MAX_FAILURES_BEFORE_BACKOFF
        max_sec = settings.AUTH_MAX_BACKOFF_SECONDS

        keys = [self._get_key("ip", ip)]
        if username:
            keys.append(self._get_key("account", username))

        max_delay = 0
        with self._lock:
            for k in keys:
                rec = self._records.get(k, {"failures": 0, "last_failure": 0, "backoff_until": 0})
                rec["failures"] += 1
                rec["last_failure"] = now

                # Calculate exponential delay once failures strictly exceed threshold
                if rec["failures"] > threshold:
                    exponent = rec["failures"] - threshold - 1
                    delay = min(base_sec * (2 ** exponent), max_sec)
                    rec["backoff_until"] = now + delay
                    if delay > max_delay:
                        max_delay = delay
                else:
                    rec["backoff_until"] = 0

                self._records[k] = rec

        return max_delay

    def record_success(self, username: Optional[str], ip: str):
        """Resets failed attempt counters upon successful authentication."""
        keys = [self._get_key("ip", ip)]
        if username:
            keys.append(self._get_key("account", username))

        with self._lock:
            for k in keys:
                if k in self._records:
                    del self._records[k]

    def reset(self):
        """Clears all tracking state (used in testing)."""
        with self._lock:
            self._records.clear()


auth_backoff_tracker = AuthBackoffTracker()

