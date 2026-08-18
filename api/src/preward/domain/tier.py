"""Escalation ladder and text-provenance vocabulary."""

from enum import IntEnum, StrEnum


class Tier(IntEnum):
    """How far a record has escalated, from passing mention to work under way.

    Deliberately domain-neutral: the cue definitions that map a corpus onto these
    levels live in `config/cues.yaml`, so choosing a corpus never edits this enum.
    """

    MENTION = 1
    EXPLORATION = 2
    COMMITMENT = 3
    EXECUTION = 4


class ExtractionMethod(StrEnum):
    """How a page's text was obtained. OCR'd quotes are evidentially weaker."""

    NATIVE = "native"
    OCR = "ocr"
