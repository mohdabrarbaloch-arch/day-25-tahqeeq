"""Text normalisation and the statistics every detector shares.

Everything here is a pure function of its input. No I/O, no clock, no random.
That is what makes the engine reproducible and the tests meaningful.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Sentence splitting is done by `split_sentences` below, which needs to look at
# the token before each terminator — a single regex cannot do that correctly.
_WHITESPACE = re.compile(r"[ \t\u00a0\u2007\u202f]+")
_BLANK_LINES = re.compile(r"\n{3,}")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]*")
_NUMBER = re.compile(r"\b\d[\d,.]*\b")
_URL_IN_TEXT = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")


@dataclass(frozen=True, slots=True)
class Document:
    """A normalised piece of text plus the statistics detectors need.

    Built once per analysis. Detectors read from this rather than re-parsing
    the raw string, so every signal sees exactly the same text.
    """

    raw: str
    text: str
    headline: str
    sentences: tuple[str, ...]
    paragraphs: tuple[str, ...]
    words: tuple[str, ...]
    word_count: int
    char_count: int
    sentence_count: int
    paragraph_count: int
    avg_sentence_words: float
    avg_word_length: float
    exclamation_count: int
    question_count: int
    all_caps_words: tuple[str, ...]
    numbers: tuple[str, ...]
    urls: tuple[str, ...]
    emails: tuple[str, ...]
    unique_word_ratio: float
    _lower: str = field(default="", repr=False)

    @property
    def lower(self) -> str:
        return self._lower

    @property
    def is_short(self) -> bool:
        """Under 120 words there is not much to judge."""
        return self.word_count < 120


def normalise_whitespace(text: str) -> str:
    """NFKC, unify line endings, collapse runs of spaces, cap blank lines."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _WHITESPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _BLANK_LINES.sub("\n\n", text)
    return text.strip()


def split_sentences(text: str) -> tuple[str, ...]:
    """Split on sentence terminators, keeping the terminator attached.

    A naive split on `[.!?]` breaks on three things that are everywhere in
    news copy, and each one was a real failure before this was written:

    * **Abbreviations** — "Rs. 1,500" and "U.S. officials" are one sentence.
    * **Decimals** — "4.2 percent" is not a sentence boundary.
    * **Initials** — "J. Smith said" is one sentence.

    So the splitter finds candidate boundaries and then rejects the ones whose
    preceding token is a known abbreviation, a single capital initial, or part
    of a number.
    """
    if not text:
        return ()

    flat = " ".join(text.split())
    if not flat:
        return ()

    out: list[str] = []
    start = 0

    for match in re.finditer(r"[.!?]+[\"'”’)\]]*(?=\s)", flat):
        terminator = match.group(0)
        before = flat[start : match.start()]
        tokens = before.split()
        last_token = tokens[-1] if tokens else ""
        bare = last_token.rstrip(".!?\"'”’)")

        if terminator.startswith("."):
            # Decimal: a digit on both sides of the period.
            if match.start() > 0 and flat[match.start() - 1].isdigit():
                following = flat[match.end() :].lstrip()
                if following[:1].isdigit():
                    continue
            # Known abbreviation.
            if bare.lower() in _ABBREVIATIONS:
                continue
            # Single capital initial, e.g. "J. Smith".
            if len(bare) == 1 and bare.isupper():
                continue

        out.append(flat[start : match.end()].strip())
        start = match.end()

    tail = flat[start:].strip()
    if tail:
        out.append(tail)

    return tuple(part for part in out if part)


# Abbreviations that end in a period but do not end a sentence. Kept short and
# specific: a long list invites false negatives, and these are the ones that
# actually appear in the kind of text this app is pointed at.
_ABBREVIATIONS = frozenset(
    {
        "rs",
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "mt",
        "vs",
        "etc",
        "eg",
        "ie",
        "cf",
        "al",
        "approx",
        "est",
        "no",
        "u.s",
        "u.k",
        "u.n",
        "u.a.e",
        "e.u",
        "p.k",
        "inc",
        "ltd",
        "co",
        "corp",
        "dept",
        "gov",
        "sen",
        "rep",
        "gen",
        "col",
        "capt",
        "lt",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "mon",
        "tue",
        "wed",
        "thu",
        "fri",
        "sat",
        "sun",
        "a.m",
        "p.m",
        "am",
        "pm",
        "fig",
        "vol",
        "pp",
        "ed",
        "rev",
    }
)


def split_paragraphs(text: str) -> tuple[str, ...]:
    if not text:
        return ()
    blocks = [block.strip() for block in text.split("\n\n")]
    return tuple(block for block in blocks if block)


def _all_caps_words(text: str) -> tuple[str, ...]:
    """Words of 3+ letters written entirely in capitals, that are shouting.

    Three things are excluded because they are ordinary English rather than
    emphasis, and counting them would punish careful writing:

    * single letters and two-letter words — "I", "US", "OK"
    * known acronyms — "CEO", "GDP", "SBP"
    * a word at the start of a sentence or paragraph — "ISLAMABAD — The
      Ministry said…" is a news dateline, not a raised voice. This was a real
      false positive: a well-written wire story was being marked down for
      shouting its own dateline.
    """
    found: list[str] = []
    for match in re.finditer(r"\b[A-Z]{3,}\b", text):
        token = match.group(0)
        if token in _BENIGN_ACRONYMS:
            continue

        start = match.start()
        # Look back for the previous non-space character.
        before = text[:start].rstrip()
        at_sentence_start = not before or before[-1] in ".!?:\n"
        if at_sentence_start:
            continue

        # A dateline is an all-caps word followed by a dash: "KARACHI —".
        after = text[match.end() :].lstrip()
        if after[:1] in {"—", "–", "-"}:
            continue

        found.append(token)
    return tuple(found)


_BENIGN_ACRONYMS = frozenset(
    {
        "USA",
        "USD",
        "UK",
        "UAE",
        "CEO",
        "CFO",
        "CTO",
        "API",
        "GDP",
        "CPI",
        "NATO",
        "UN",
        "WHO",
        "IMF",
        "FBI",
        "CIA",
        "NASA",
        "ISIS",
        "PTI",
        "PPP",
        "PMLN",
        "MQM",
        "SBP",
        "FBR",
        "NADRA",
        "PTCL",
        "OGRA",
        "NEPRA",
        "PSX",
        "KSE",
        "ADB",
        "WB",
        "EU",
        "AI",
        "IT",
        "DNA",
        "HIV",
        "COVID",
        "SARS",
        "MRI",
        "CT",
        "ECG",
        "ICU",
        "OPD",
        "LLM",
        "GPU",
        "CPU",
    }
)


def build_document(text: str, headline: str = "") -> Document:
    """Normalise raw input into a Document. The single entry point."""
    normalised = normalise_whitespace(text)
    clean_headline = normalise_whitespace(headline)

    sentences = split_sentences(normalised)
    paragraphs = split_paragraphs(normalised)
    words = tuple(match.group(0) for match in _WORD.finditer(normalised))
    word_count = len(words)

    total_word_chars = sum(len(word) for word in words)
    avg_word_length = (total_word_chars / word_count) if word_count else 0.0
    avg_sentence_words = (word_count / len(sentences)) if sentences else 0.0

    lowered_words = [word.lower() for word in words]
    unique_ratio = (len(set(lowered_words)) / word_count) if word_count else 0.0

    return Document(
        raw=text,
        text=normalised,
        headline=clean_headline,
        sentences=sentences,
        paragraphs=paragraphs,
        words=words,
        word_count=word_count,
        char_count=len(normalised),
        sentence_count=len(sentences),
        paragraph_count=len(paragraphs),
        avg_sentence_words=round(avg_sentence_words, 2),
        avg_word_length=round(avg_word_length, 2),
        exclamation_count=normalised.count("!"),
        question_count=normalised.count("?"),
        all_caps_words=_all_caps_words(normalised),
        numbers=tuple(match.group(0) for match in _NUMBER.finditer(normalised)),
        urls=tuple(match.group(0) for match in _URL_IN_TEXT.finditer(normalised)),
        emails=tuple(match.group(0) for match in _EMAIL.finditer(normalised)),
        unique_word_ratio=round(unique_ratio, 3),
        _lower=normalised.lower(),
    )


def per_hundred(count: int, word_count: int) -> float:
    """Rate per 100 words, guarded against division by zero."""
    if word_count <= 0:
        return 0.0
    return (count / word_count) * 100.0


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))
