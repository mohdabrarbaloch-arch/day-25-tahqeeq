"""Aggregation: eleven signals → one score, one band, one confidence level.

The two decisions that matter here:

1. **Renormalise, don't penalise.** A signal that does not apply (no headline,
   no URL) is dropped and the remaining weights are rescaled to sum to 1. The
   alternative — scoring a missing input as neutral 50 — silently drags every
   analysis toward the middle and makes the score mean nothing.

2. **Confidence is about length, not certainty.** A 60-word post cannot be
   judged the way a 1,200-word article can. Reporting high confidence on a
   short text would be the most dishonest thing this app could do.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.engine.signals import Signal, run_all
from app.engine.text import Document, build_document, clamp


@dataclass(frozen=True, slots=True)
class Band:
    id: str
    label: str
    description: str
    min_score: float


BANDS: tuple[Band, ...] = (
    Band(
        id="strong",
        label="Strong signals",
        description=(
            "The writing carries the markers of careful reporting: named sources, "
            "hedged claims, concrete figures. That is evidence about the writing, "
            "not proof the story is true."
        ),
        min_score=75.0,
    ),
    Band(
        id="reasonable",
        label="Reasonable",
        description=(
            "Mostly conventional reporting with a few weak spots. Worth reading, "
            "worth checking the primary source."
        ),
        min_score=60.0,
    ),
    Band(
        id="mixed",
        label="Mixed",
        description=(
            "Some markers of careful writing and some of careless or persuasive "
            "writing. The text alone does not settle it — verify the claims."
        ),
        min_score=45.0,
    ),
    Band(
        id="weak",
        label="Weak signals",
        description=(
            "The writing leans on hype, vague sourcing or manufactured urgency. "
            "Treat the claims as unverified until you find a primary source."
        ),
        min_score=30.0,
    ),
    Band(
        id="poor",
        label="Poor signals",
        description=(
            "Heavy on emotional language, light on attribution. This is the shape "
            "of content that spreads because it is shared, not because it is checked."
        ),
        min_score=0.0,
    ),
)


@dataclass(frozen=True, slots=True)
class Confidence:
    level: str
    label: str
    reason: str


def band_for(score: float) -> Band:
    for band in BANDS:
        if score >= band.min_score:
            return band
    return BANDS[-1]


def confidence_for(doc: Document) -> Confidence:
    """Confidence in the *assessment*, driven by how much text there is."""
    words = doc.word_count
    if words < 80:
        return Confidence(
            level="very_low",
            label="Very low",
            reason=f"Only {words} words. There is not enough text to judge style reliably.",
        )
    if words < 200:
        return Confidence(
            level="low",
            label="Low",
            reason=f"{words} words. Short texts give the detectors little to work with.",
        )
    if words < 500:
        return Confidence(
            level="moderate",
            label="Moderate",
            reason=f"{words} words. Enough to see a pattern, not enough to be sure of it.",
        )
    if words < 1200:
        return Confidence(
            level="high",
            label="High",
            reason=f"{words} words. Long enough for the style markers to be meaningful.",
        )
    return Confidence(
        level="very_high",
        label="Very high",
        reason=f"{words} words. A full-length piece, so the style is well established.",
    )


@dataclass(frozen=True, slots=True)
class Analysis:
    score: float
    band: Band
    confidence: Confidence
    signals: tuple[Signal, ...]
    document: Document
    source_url: str | None

    @property
    def applied_signals(self) -> tuple[Signal, ...]:
        return tuple(signal for signal in self.signals if signal.applies)

    @property
    def top_concerns(self) -> tuple[Signal, ...]:
        """The three applied signals that pulled the score down hardest."""
        applied = self.applied_signals
        ranked = sorted(applied, key=lambda s: (s.score, -s.weight))
        return tuple(ranked[:3])

    @property
    def top_strengths(self) -> tuple[Signal, ...]:
        """The three applied signals that pulled the score up hardest."""
        applied = self.applied_signals
        ranked = sorted(applied, key=lambda s: (-s.score, -s.weight))
        return tuple(ranked[:3])

    def as_dict(self) -> dict[str, object]:
        return {
            "score": round(self.score, 2),
            "band": {
                "id": self.band.id,
                "label": self.band.label,
                "description": self.band.description,
            },
            "confidence": {
                "level": self.confidence.level,
                "label": self.confidence.label,
                "reason": self.confidence.reason,
            },
            "signals": [signal.as_dict() for signal in self.signals],
            "stats": {
                "word_count": self.document.word_count,
                "sentence_count": self.document.sentence_count,
                "paragraph_count": self.document.paragraph_count,
                "avg_sentence_words": self.document.avg_sentence_words,
                "avg_word_length": self.document.avg_word_length,
                "unique_word_ratio": self.document.unique_word_ratio,
                "exclamation_count": self.document.exclamation_count,
                "all_caps_count": len(self.document.all_caps_words),
                "number_count": len(self.document.numbers),
            },
            "source_url": self.source_url,
        }


def aggregate(signals: tuple[Signal, ...]) -> float:
    """Weighted mean over the signals that apply, renormalised.

    If nothing applies — which cannot happen with the current detector set,
    but is guarded anyway — return a neutral 50 rather than dividing by zero.
    """
    applied = [signal for signal in signals if signal.applies]
    if not applied:
        return 50.0

    total_weight = sum(signal.weight for signal in applied)
    if total_weight <= 0:
        return 50.0

    weighted = sum(signal.score * signal.weight for signal in applied)
    return clamp(weighted / total_weight)


def analyse(text: str, headline: str = "", source_url: str | None = None) -> Analysis:
    """The single public entry point. Text in, Analysis out."""
    document = build_document(text, headline)
    signals = run_all(document, source_url)
    score = aggregate(signals)
    return Analysis(
        score=score,
        band=band_for(score),
        confidence=confidence_for(document),
        signals=signals,
        document=document,
        source_url=source_url,
    )
