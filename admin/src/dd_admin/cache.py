"""A value kept for a short while, so that a page reloaded, or several opened at once, do not each
run the doctor or read every run again."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class Cached[T]:
    """`make()`'s value, made again once it is `ttl_s` seconds old. One caller makes it while the
    others wait for it."""

    make: Callable[[], T]
    ttl_s: float
    clock: Callable[[], float] = time.monotonic
    _value: tuple[float, T] | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def get(self, *, fresh: bool = False) -> T:
        """The value, made again if it is older than `ttl_s` or `fresh` is asked for."""
        with self._lock:
            now = self.clock()
            if fresh or self._value is None or now - self._value[0] >= self.ttl_s:
                self._value = (now, self.make())
            return self._value[1]

    def made_at(self) -> float | None:
        """When the value was made, on `clock`, or None if it has not been."""
        return None if self._value is None else self._value[0]
