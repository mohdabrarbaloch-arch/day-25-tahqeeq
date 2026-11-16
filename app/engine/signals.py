"""The eleven detectors.

Each one looks at exactly one property of the writing and returns a `Signal`:
a 0–100 score where **higher means more credible**, a weight, a one-line
summary, and the evidence that produced it.

The contract every detector honours:

* pure — same input, same output, always
* explainable — if it scores you down, it names the span that did it
* bounded — never returns outside 0–100
* honest about absence — a detector with nothing to look at says so rather
  than inventing a neutral 50
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.engine import lexicon
from app.engine.text import Document, clamp, per_hundred


@dataclass(frozen=True, slots=True)
class Evidence:
    """One concrete thing a detector found, with the text that proves it."""

    label: str
    detail: str
    span: str = ""
    count: int = 1

    def as_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "detail": self.detail,
            "span": self.span,
            "count": self.count,
        }


@dataclass(frozen=True, slots=True)
class Signal:
    """One detector's verdict."""

    id: str
    label: str
    weight: float
    score: float
    summary: str
    evidence: tuple[Evidence, ...] = field(default_factory=tuple)
    applies: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "weight": self.weight,
            "score": round(self.score, 2),
            "summary": self.summary,
            "applies": self.applies,
            "evidence": [item.as_dict() for item in self.evidence],
        }


# ── helpers ──────────────────────────────────────────────────────────────────


def _find_phrases(doc: Document, phrases: tuple[str, ...]) -> list[tuple[str, int]]:
    """Return (phrase, occurrences) for every phrase present in the text."""
    hits: list[tuple[str, int]] = []
    for phrase in phrases:
        count = doc.lower.count(phrase)
        if count:
            hits.append((phrase, count))
    return hits


def _find_words(doc: Document, words: frozenset[str]) -> list[tuple[str, int]]:
    """Count whole-word matches, case-insensitively."""
    lowered = [word.lower() for word in doc.words]
    counts: dict[str, int] = {}
    for word in lowered:
        if word in words:
            counts[word] = counts.get(word, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def _snippet(doc: Document, phrase: str, width: int = 90) -> str:
    """A short window of the original text around the first match."""
    index = doc.lower.find(phrase)
    if index < 0:
        return ""
    start = max(0, index - width // 3)
    end = min(len(doc.text), index + len(phrase) + width)
    fragment = doc.text[start:end].strip()
    if start > 0:
        fragment = "…" + fragment
    if end < len(doc.text):
        fragment = fragment + "…"
    return fragment


# ── 1. Attribution ───────────────────────────────────────────────────────────


def signal_attribution(doc: Document) -> Signal:
    """Does the piece name who told it?

    The strongest positive signal in the model. A story that names a source is
    checkable; one that doesn't is not.
    """
    named = _find_phrases(doc, lexicon.ATTRIBUTION_PHRASES)
    anonymous = _find_phrases(doc, lexicon.ANONYMOUS_SOURCE_PHRASES)

    named_count = sum(count for _, count in named)
    anon_count = sum(count for _, count in anonymous)

    evidence: list[Evidence] = []
    for phrase, count in named[:6]:
        evidence.append(
            Evidence(
                label="Named source",
                detail=f'"{phrase}" appears {count}×',
                span=_snippet(doc, phrase),
                count=count,
            )
        )
    for phrase, count in anonymous[:4]:
        evidence.append(
            Evidence(
                label="Anonymous sourcing",
                detail=f'"{phrase}" appears {count}×',
                span=_snippet(doc, phrase),
                count=count,
            )
        )

    if named_count == 0 and anon_count == 0:
        return Signal(
            id="attribution",
            label="Attribution",
            weight=0.15,
            score=38.0,
            summary="No source is named anywhere in the text.",
            evidence=(
                Evidence(
                    label="No attribution",
                    detail=(
                        "No named source and no anonymous sourcing either — the claims float free."
                    ),
                ),
            ),
        )

    # Named sourcing is worth a lot; anonymous sourcing is worth something but
    # much less, and only when it is not the whole story.
    named_rate = per_hundred(named_count, doc.word_count)
    anon_rate = per_hundred(anon_count, doc.word_count)

    score = 40.0
    score += min(45.0, named_rate * 22.0)
    score += min(12.0, anon_rate * 8.0)
    if named_count == 0 and anon_count > 0:
        score -= 12.0

    if named_count and anon_count:
        summary = (
            f"{named_count} named-source reference(s) and {anon_count} anonymous one(s). "
            "Mixing both is normal in real reporting."
        )
    elif named_count:
        summary = f"{named_count} named-source reference(s) — the claims are checkable."
    else:
        summary = (
            f"{anon_count} anonymous-source reference(s) and nothing named. "
            "Unverifiable as written."
        )

    return Signal(
        id="attribution",
        label="Attribution",
        weight=0.15,
        score=clamp(score),
        summary=summary,
        evidence=tuple(evidence),
    )


# ── 2. Certainty ─────────────────────────────────────────────────────────────


def signal_certainty(doc: Document) -> Signal:
    """Absolute claims versus hedged language.

    Honest reporting hedges. Propaganda asserts. The ratio between the two is
    more informative than either count alone.
    """
    absolutes = _find_words(doc, lexicon.ABSOLUTE_WORDS)
    hedges = _find_words(doc, lexicon.HEDGE_WORDS)

    absolute_count = sum(count for _, count in absolutes)
    hedge_count = sum(count for _, count in hedges)

    evidence: list[Evidence] = []
    for word, count in absolutes[:5]:
        evidence.append(
            Evidence(
                label="Absolute claim",
                detail=f'"{word}" ×{count}',
                span=_snippet(doc, word),
                count=count,
            )
        )
    for word, count in hedges[:4]:
        evidence.append(
            Evidence(
                label="Hedged language",
                detail=f'"{word}" ×{count}',
                span=_snippet(doc, word),
                count=count,
            )
        )

    if absolute_count == 0 and hedge_count == 0:
        return Signal(
            id="certainty",
            label="Certainty",
            weight=0.12,
            score=58.0,
            summary="Neither absolute claims nor hedges — flat, declarative prose.",
            evidence=(
                Evidence(
                    label="No markers",
                    detail="No absolutist words and no hedging words found.",
                ),
            ),
        )

    total = absolute_count + hedge_count
    hedge_share = hedge_count / total

    # 0% hedges → 30, 50% hedges → 70, 100% hedges → 88.
    score = 30.0 + (hedge_share * 58.0)
    # Penalise sheer volume of absolutism, not just its share.
    absolute_rate = per_hundred(absolute_count, doc.word_count)
    score -= min(18.0, absolute_rate * 9.0)

    if hedge_share >= 0.5:
        summary = (
            f"{hedge_count} hedge(s) against {absolute_count} absolute claim(s) — "
            "the writer allows for doubt."
        )
    elif absolute_count > hedge_count:
        summary = (
            f"{absolute_count} absolute claim(s) against only {hedge_count} hedge(s) — "
            "asserted rather than reported."
        )
    else:
        summary = f"{absolute_count} absolute claim(s), {hedge_count} hedge(s)."

    return Signal(
        id="certainty",
        label="Certainty",
        weight=0.12,
        score=clamp(score),
        summary=summary,
        evidence=tuple(evidence),
    )


# ── 3. Sensationalism ────────────────────────────────────────────────────────


def signal_sensationalism(doc: Document) -> Signal:
    """Emotional temperature: exclamations, shouting, high-arousal words."""
    sensational = _find_words(doc, lexicon.SENSATIONAL_WORDS)
    sensational_count = sum(count for _, count in sensational)

    exclamations = doc.exclamation_count
    caps = doc.all_caps_words

    evidence: list[Evidence] = []
    for word, count in sensational[:6]:
        evidence.append(
            Evidence(
                label="High-arousal word",
                detail=f'"{word}" ×{count}',
                span=_snippet(doc, word),
                count=count,
            )
        )
    if exclamations:
        evidence.append(
            Evidence(
                label="Exclamation marks",
                detail=f"{exclamations} in {doc.sentence_count} sentence(s)",
                count=exclamations,
            )
        )
    if caps:
        evidence.append(
            Evidence(
                label="Shouted words",
                detail=", ".join(caps[:8]) + ("…" if len(caps) > 8 else ""),
                count=len(caps),
            )
        )

    if sensational_count == 0 and exclamations == 0 and not caps:
        return Signal(
            id="sensationalism",
            label="Sensationalism",
            weight=0.11,
            score=90.0,
            summary="Calm register — no hype words, no exclamations, no shouting.",
            evidence=(
                Evidence(
                    label="Clean",
                    detail="Nothing in the text is written to raise the temperature.",
                ),
            ),
        )

    score = 92.0
    sensational_rate = per_hundred(sensational_count, doc.word_count)
    score -= min(45.0, sensational_rate * 26.0)

    exclamation_rate = per_hundred(exclamations, doc.word_count)
    score -= min(20.0, exclamation_rate * 30.0)

    caps_rate = per_hundred(len(caps), doc.word_count)
    score -= min(22.0, caps_rate * 40.0)

    parts: list[str] = []
    if sensational_count:
        parts.append(f"{sensational_count} high-arousal word(s)")
    if exclamations:
        parts.append(f"{exclamations} exclamation mark(s)")
    if caps:
        parts.append(f"{len(caps)} shouted word(s)")
    summary = ", ".join(parts) + "."

    return Signal(
        id="sensationalism",
        label="Sensationalism",
        weight=0.11,
        score=clamp(score),
        summary=summary,
        evidence=tuple(evidence),
    )


# ── 4. Headline vs body ──────────────────────────────────────────────────────


_STOPWORDS = frozenset(
    {
        "the",
        "a",
        "an",
        "and",
        "or",
        "but",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "at",
        "by",
        "from",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "it",
        "its",
        "this",
        "that",
        "these",
        "those",
        "his",
        "her",
        "their",
        "our",
        "your",
        "my",
        "he",
        "she",
        "they",
        "we",
        "you",
        "i",
        "not",
        "no",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "can",
        "could",
        "should",
        "may",
        "might",
        "must",
        "than",
        "then",
        "so",
        "if",
        "when",
        "what",
        "who",
        "how",
        "why",
        "which",
    }
)


def _content_words(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z'’\-]+", text.lower())
    return {word for word in words if word not in _STOPWORDS and len(word) > 2}


def signal_headline_body(doc: Document) -> Signal:
    """Does the body actually deliver the headline's claim?

    A headline that promises something the article never says is the single
    most common form of misleading-but-technically-true writing.
    """
    if not doc.headline:
        return Signal(
            id="headline_body",
            label="Headline vs body",
            weight=0.10,
            score=55.0,
            summary="No headline supplied, so the claim cannot be checked against the body.",
            evidence=(
                Evidence(
                    label="Not applicable",
                    detail="Paste a headline to enable this check.",
                ),
            ),
            applies=False,
        )

    headline_words = _content_words(doc.headline)
    if not headline_words:
        return Signal(
            id="headline_body",
            label="Headline vs body",
            weight=0.10,
            score=55.0,
            summary="The headline has no content words to check.",
            evidence=(Evidence(label="Not applicable", detail="Headline is all stopwords."),),
            applies=False,
        )

    body_words = _content_words(doc.text)
    overlap = headline_words & body_words
    coverage = len(overlap) / len(headline_words)

    missing = sorted(headline_words - body_words)

    evidence: list[Evidence] = [
        Evidence(
            label="Headline terms in body",
            detail=f"{len(overlap)} of {len(headline_words)} content words appear in the text",
            count=len(overlap),
        )
    ]
    if missing:
        evidence.append(
            Evidence(
                label="Headline terms absent from body",
                detail=", ".join(missing[:10]) + ("…" if len(missing) > 10 else ""),
                count=len(missing),
            )
        )

    # 100% coverage → 95, 50% → 55, 0% → 15.
    score = 15.0 + (coverage * 80.0)

    if coverage >= 0.8:
        summary = "The body covers the headline's claim — the terms line up."
    elif coverage >= 0.5:
        summary = (
            f"Only {len(overlap)} of {len(headline_words)} headline terms appear in the body. "
            "Partly supported."
        )
    else:
        summary = (
            f"The body barely mentions the headline's terms "
            f"({len(overlap)}/{len(headline_words)}). The headline promises more than it delivers."
        )

    return Signal(
        id="headline_body",
        label="Headline vs body",
        weight=0.10,
        score=clamp(score),
        summary=summary,
        evidence=tuple(evidence),
    )


# ── 5. Clickbait ─────────────────────────────────────────────────────────────


def signal_clickbait(doc: Document) -> Signal:
    """Curiosity-gap constructions and listicle bait."""
    hits = _find_phrases(doc, lexicon.CLICKBAIT_PHRASES)
    total = sum(count for _, count in hits)

    # A headline ending in a question or an ellipsis is a classic curiosity gap.
    headline_bait = False
    if doc.headline:
        stripped = doc.headline.strip()
        if stripped.endswith("?") or stripped.endswith("…") or stripped.endswith("..."):
            headline_bait = True

    evidence: list[Evidence] = []
    for phrase, count in hits[:6]:
        evidence.append(
            Evidence(
                label="Clickbait construction",
                detail=f'"{phrase}" ×{count}',
                span=_snippet(doc, phrase),
                count=count,
            )
        )
    if headline_bait:
        evidence.append(
            Evidence(
                label="Curiosity-gap headline",
                detail="The headline ends in a question or an ellipsis instead of a claim.",
                span=doc.headline,
            )
        )

    if total == 0 and not headline_bait:
        return Signal(
            id="clickbait",
            label="Clickbait",
            weight=0.10,
            score=92.0,
            summary="No curiosity-gap or listicle constructions found.",
            evidence=(
                Evidence(label="Clean", detail="The text states things rather than teasing them."),
            ),
        )

    score = 92.0
    score -= min(55.0, total * 20.0)
    if headline_bait:
        score -= 12.0

    parts: list[str] = []
    if total:
        parts.append(f"{total} clickbait construction(s)")
    if headline_bait:
        parts.append("a curiosity-gap headline")
    summary = ", ".join(parts) + "."

    return Signal(
        id="clickbait",
        label="Clickbait",
        weight=0.10,
        score=clamp(score),
        summary=summary,
        evidence=tuple(evidence),
    )


# ── 6. Conspiracy framing ────────────────────────────────────────────────────


def signal_conspiracy(doc: Document) -> Signal:
    """'They don't want you to know' framing."""
    hits = _find_phrases(doc, lexicon.CONSPIRACY_PHRASES)
    total = sum(count for _, count in hits)

    if total == 0:
        return Signal(
            id="conspiracy",
            label="Conspiracy framing",
            weight=0.09,
            score=94.0,
            summary="No conspiracy framing found.",
            evidence=(
                Evidence(
                    label="Clean",
                    detail="Nothing frames the story as suppressed or hidden.",
                ),
            ),
        )

    evidence = tuple(
        Evidence(
            label="Conspiracy framing",
            detail=f'"{phrase}" ×{count}',
            span=_snippet(doc, phrase),
            count=count,
        )
        for phrase, count in hits[:6]
    )

    score = 94.0 - min(80.0, total * 26.0)

    return Signal(
        id="conspiracy",
        label="Conspiracy framing",
        weight=0.09,
        score=clamp(score),
        summary=f"{total} conspiracy-framing phrase(s) — the story is presented as suppressed.",
        evidence=evidence,
    )


# ── 7. Quotes ────────────────────────────────────────────────────────────────


def signal_quotes(doc: Document) -> Signal:
    """Direct quotations per 100 words.

    Quoting someone is a commitment: it can be checked, and it can be wrong in
    a way that gets corrected. Pieces with no quotes at all are usually
    summarising someone else's reporting, or inventing.
    """
    quote_count = 0
    for pattern in lexicon.QUOTE_PATTERNS:
        quote_count += doc.text.count(pattern)
    # Each quotation has an opening and a closing mark.
    quote_count = quote_count // 2

    rate = per_hundred(quote_count, doc.word_count)

    if quote_count == 0:
        return Signal(
            id="quotes",
            label="Direct quotes",
            weight=0.08,
            score=42.0,
            summary="No direct quotations anywhere in the text.",
            evidence=(
                Evidence(
                    label="No quotes",
                    detail=(
                        "Nobody is quoted, so nothing here can be checked "
                        "against what a person said."
                    ),
                ),
            ),
        )

    # 1 quote per 100 words is healthy; more is fine; zero is the problem.
    score = 45.0 + min(48.0, rate * 30.0)

    return Signal(
        id="quotes",
        label="Direct quotes",
        weight=0.08,
        score=clamp(score),
        summary=f"{quote_count} direct quotation(s), {rate:.1f} per 100 words.",
        evidence=(
            Evidence(
                label="Quotations",
                detail=f"{quote_count} quoted passage(s) in {doc.word_count} words",
                count=quote_count,
            ),
        ),
    )


# ── 8. Domain ────────────────────────────────────────────────────────────────


def _host_from_url(url: str) -> str:
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    host = host.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def signal_domain(doc: Document, source_url: str | None) -> Signal:
    """Source domain tier, from a static table.

    Only applies when a URL was supplied. When it does not apply, the
    aggregator renormalises the remaining weights rather than scoring the
    piece down for a missing input.
    """
    if not source_url:
        return Signal(
            id="domain",
            label="Source domain",
            weight=0.07,
            score=55.0,
            summary="No source URL supplied, so the publisher cannot be assessed.",
            evidence=(
                Evidence(
                    label="Not applicable",
                    detail="Analyse a URL to enable this check.",
                ),
            ),
            applies=False,
        )

    host = _host_from_url(source_url)
    if not host:
        return Signal(
            id="domain",
            label="Source domain",
            weight=0.07,
            score=55.0,
            summary="The supplied URL has no readable hostname.",
            evidence=(Evidence(label="Not applicable", detail=f"Could not parse: {source_url}"),),
            applies=False,
        )

    tier = lexicon.DOMAIN_TIERS.get(host)
    if tier is None:
        # Try the parent domain: news.example.com → example.com
        parts = host.split(".")
        if len(parts) > 2:
            parent = ".".join(parts[-2:])
            tier = lexicon.DOMAIN_TIERS.get(parent)

    if tier is None:
        return Signal(
            id="domain",
            label="Source domain",
            weight=0.07,
            score=lexicon.DOMAIN_UNKNOWN_SCORE,
            summary=f"{host} is not in the tier table — scored neutrally.",
            evidence=(
                Evidence(
                    label="Unknown publisher",
                    detail=f"{host} has no entry in the static tier table.",
                    span=host,
                ),
            ),
        )

    score = lexicon.DOMAIN_TIER_SCORES[tier]
    tier_names = {
        1: "established, with a corrections policy",
        2: "mainstream, generally reliable",
        3: "tabloid or high-volume, weaker verification",
        4: "known misinformation or satire",
    }

    return Signal(
        id="domain",
        label="Source domain",
        weight=0.07,
        score=score,
        summary=f"{host} — tier {tier}, {tier_names[tier]}.",
        evidence=(
            Evidence(
                label=f"Tier {tier} publisher",
                detail=f"{host} is listed as {tier_names[tier]}.",
                span=host,
            ),
        ),
    )


# ── 9. Sharing bait ──────────────────────────────────────────────────────────


def signal_sharing_bait(doc: Document) -> Signal:
    """Manufactured urgency to forward the piece."""
    hits = _find_phrases(doc, lexicon.SHARING_BAIT_PHRASES)
    total = sum(count for _, count in hits)

    if total == 0:
        return Signal(
            id="sharing_bait",
            label="Sharing bait",
            weight=0.07,
            score=93.0,
            summary="No calls to forward or share the text.",
            evidence=(
                Evidence(
                    label="Clean",
                    detail="The piece does not ask the reader to spread it.",
                ),
            ),
        )

    evidence = tuple(
        Evidence(
            label="Sharing bait",
            detail=f'"{phrase}" ×{count}',
            span=_snippet(doc, phrase),
            count=count,
        )
        for phrase, count in hits[:6]
    )

    score = 93.0 - min(78.0, total * 24.0)

    return Signal(
        id="sharing_bait",
        label="Sharing bait",
        weight=0.07,
        score=clamp(score),
        summary=f"{total} call(s) to share or forward — urgency is being manufactured.",
        evidence=evidence,
    )


# ── 10. Vague quantity ───────────────────────────────────────────────────────


def signal_quantity_vagueness(doc: Document) -> Signal:
    """'Thousands of' instead of a number.

    Real reporting gives figures. Vague quantity is how a claim gets to sound
    large without being checkable.
    """
    hits = _find_phrases(doc, lexicon.VAGUE_QUANTITY_PHRASES)
    vague_total = sum(count for _, count in hits)
    concrete_numbers = len(doc.numbers)

    evidence: list[Evidence] = []
    for phrase, count in hits[:5]:
        evidence.append(
            Evidence(
                label="Vague quantity",
                detail=f'"{phrase}" ×{count}',
                span=_snippet(doc, phrase),
                count=count,
            )
        )
    evidence.append(
        Evidence(
            label="Concrete figures",
            detail=f"{concrete_numbers} numeric token(s) in the text",
            count=concrete_numbers,
        )
    )

    if vague_total == 0:
        # No vague phrases is only a *strength* if there are figures to show for
        # it. A text that quantifies nothing at all has given us no evidence
        # either way, so it scores neutral rather than high.
        if concrete_numbers == 0:
            return Signal(
                id="quantity_vagueness",
                label="Quantity precision",
                weight=0.06,
                score=58.0,
                summary="No vague quantities, but no figures either — nothing to weigh.",
                evidence=tuple(evidence),
            )
        return Signal(
            id="quantity_vagueness",
            label="Quantity precision",
            weight=0.06,
            score=88.0,
            summary=f"No vague-quantity phrases, and {concrete_numbers} concrete figure(s).",
            evidence=tuple(evidence),
        )

    # Concrete numbers offset vague ones. A piece with "thousands of" AND
    # twelve real figures is doing better than one with only the phrase.
    ratio = concrete_numbers / (vague_total + 1)
    score = 30.0 + min(55.0, ratio * 18.0)

    return Signal(
        id="quantity_vagueness",
        label="Quantity precision",
        weight=0.06,
        score=clamp(score),
        summary=(
            f"{vague_total} vague-quantity phrase(s) against {concrete_numbers} concrete figure(s)."
        ),
        evidence=tuple(evidence),
    )


# ── 11. Temporal vagueness ───────────────────────────────────────────────────


_DATE_LIKE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}"
    r"|\d{4}-\d{2}-\d{2}"
    r"|(?:January|February|March|April|May|June|July|August|September|October"
    r"|November|December)\s+\d{1,2}"
    r"|\d{1,2}\s+(?:January|February|March|April|May|June|July|August"
    r"|September|October|November|December))\b",
    re.IGNORECASE,
)


def signal_temporal_vagueness(doc: Document) -> Signal:
    """'Recently' instead of a date."""
    hits = _find_phrases(doc, lexicon.VAGUE_TIME_PHRASES)
    vague_total = sum(count for _, count in hits)
    dates = _DATE_LIKE.findall(doc.text)

    evidence: list[Evidence] = []
    for phrase, count in hits[:5]:
        evidence.append(
            Evidence(
                label="Vague time",
                detail=f'"{phrase}" ×{count}',
                span=_snippet(doc, phrase),
                count=count,
            )
        )
    evidence.append(
        Evidence(
            label="Explicit dates",
            detail=f"{len(dates)} date reference(s) found",
            count=len(dates),
        )
    )

    if vague_total == 0:
        # Same rule as quantity: absence of vague time is only a strength when
        # there are real dates to show for it.
        if not dates:
            return Signal(
                id="temporal_vagueness",
                label="Time precision",
                weight=0.05,
                score=58.0,
                summary="No vague time references, but no dates either — nothing to weigh.",
                evidence=tuple(evidence),
            )
        return Signal(
            id="temporal_vagueness",
            label="Time precision",
            weight=0.05,
            score=88.0,
            summary=f"No vague-time phrases, and {len(dates)} explicit date(s).",
            evidence=tuple(evidence),
        )

    ratio = len(dates) / (vague_total + 1)
    score = 32.0 + min(52.0, ratio * 20.0)

    return Signal(
        id="temporal_vagueness",
        label="Time precision",
        weight=0.05,
        score=clamp(score),
        summary=f"{vague_total} vague-time phrase(s) against {len(dates)} explicit date(s).",
        evidence=tuple(evidence),
    )


# ── registry ─────────────────────────────────────────────────────────────────


def run_all(doc: Document, source_url: str | None = None) -> tuple[Signal, ...]:
    """Run every detector in a fixed order. Order is part of the contract."""
    return (
        signal_attribution(doc),
        signal_certainty(doc),
        signal_sensationalism(doc),
        signal_headline_body(doc),
        signal_clickbait(doc),
        signal_conspiracy(doc),
        signal_quotes(doc),
        signal_domain(doc, source_url),
        signal_sharing_bait(doc),
        signal_quantity_vagueness(doc),
        signal_temporal_vagueness(doc),
    )
