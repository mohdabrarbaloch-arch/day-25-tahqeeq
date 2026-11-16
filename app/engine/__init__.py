"""The credibility engine.

Pure functions only. Nothing in this package performs I/O except
`fetcher.py`, which is the single deliberate exception and is isolated so the
rest can be tested without a network.
"""

from app.engine.scoring import Analysis, analyse, band_for, confidence_for
from app.engine.signals import Evidence, Signal, run_all
from app.engine.text import Document, build_document

__all__ = [
    "Analysis",
    "Document",
    "Evidence",
    "Signal",
    "analyse",
    "band_for",
    "build_document",
    "confidence_for",
    "run_all",
]
