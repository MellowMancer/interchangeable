"""The system clock. The only place this package reads the time."""

import time
from datetime import UTC, datetime


class SystemClock:
    """Real time, for production wiring. Tests inject a fixed clock instead."""

    def now(self) -> datetime:
        """Current UTC time."""
        return datetime.now(UTC)

    def monotonic(self) -> float:
        """Seconds from an arbitrary origin, unaffected by clock adjustments."""
        return time.monotonic()
