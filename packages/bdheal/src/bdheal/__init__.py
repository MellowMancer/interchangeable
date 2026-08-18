"""Self-healing for Bright Data collectors: detect, diagnose, heal, verify, promote.

Corpus-agnostic by construction. It knows collector ids, Pydantic schemas, anchor URLs
and HTML structure, and nothing about any problem domain.
"""

from bdheal.healer import Healer
from bdheal.models import (
    Baseline,
    BenchCase,
    CollectorSpec,
    DetectVerdict,
    HealEvent,
    RowError,
    RunResult,
    Signal,
    VerifyReport,
)

__version__ = "0.1.0"

__all__ = [
    "Baseline",
    "BenchCase",
    "CollectorSpec",
    "DetectVerdict",
    "HealEvent",
    "Healer",
    "RowError",
    "RunResult",
    "Signal",
    "VerifyReport",
]
