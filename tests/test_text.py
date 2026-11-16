"""Tests for text normalisation and the shared statistics.

These are the foundation — if the Document is wrong, every detector is wrong.
"""

from __future__ import annotations

from app.engine.text import (
    build_document,
    clamp,
    normalise_whitespace,
    per_hundred,
    split_paragraphs,
    split_sentences,
)


class TestNormaliseWhitespace:
    def test_collapses_runs_of_spaces(self):
        assert normalise_whitespace("a    b\t\tc") == "a b c"

    def test_unifies_line_endings(self):
        assert normalise_whitespace("a\r\nb\rc") == "a\nb\nc"

    def test_caps_blank_lines_at_two(self):
        assert normalise_whitespace("a\n\n\n\n\nb") == "a\n\nb"

    def test_strips_outer_whitespace(self):
        assert normalise_whitespace("   hello   ") == "hello"

    def test_empty_input(self):
        assert normalise_whitespace("") == ""

    def test_nfkc_normalises_ligatures(self):
        # ﬁ (U+FB01) should become "fi" under NFKC.
        assert "fi" in normalise_whitespace("ﬁnance")


class TestSplitSentences:
    def test_splits_on_period(self):
        result = split_sentences("One thing. Another thing.")
        assert len(result) == 2

    def test_does_not_split_abbreviations(self):
        # "Rs. 1,500" must not become two sentences.
        result = split_sentences("It cost Rs. 1,500 in total.")
        assert len(result) == 1

    def test_does_not_split_us(self):
        result = split_sentences("U.S. officials said no.")
        assert len(result) == 1

    def test_handles_question_and_exclamation(self):
        result = split_sentences("Really? Yes! Fine.")
        assert len(result) == 3

    def test_empty_input(self):
        assert split_sentences("") == ()

    def test_single_sentence_no_terminator(self):
        assert split_sentences("no terminator here") == ("no terminator here",)


class TestSplitParagraphs:
    def test_splits_on_blank_line(self):
        assert len(split_paragraphs("one\n\ntwo\n\nthree")) == 3

    def test_ignores_empty_blocks(self):
        assert len(split_paragraphs("one\n\n\n\ntwo")) == 2

    def test_empty_input(self):
        assert split_paragraphs("") == ()


class TestBuildDocument:
    def test_counts_words(self):
        doc = build_document("one two three four five")
        assert doc.word_count == 5

    def test_counts_sentences(self):
        doc = build_document("First one. Second one. Third one.")
        assert doc.sentence_count == 3

    def test_average_sentence_length(self):
        doc = build_document("one two three. four five six.")
        assert doc.avg_sentence_words == 3.0

    def test_exclamation_count(self):
        doc = build_document("Wow! Amazing! Really!")
        assert doc.exclamation_count == 3

    def test_unique_word_ratio_all_distinct(self):
        doc = build_document("alpha beta gamma delta")
        assert doc.unique_word_ratio == 1.0

    def test_unique_word_ratio_all_same(self):
        doc = build_document("same same same same")
        assert doc.unique_word_ratio == 0.25

    def test_numbers_extracted(self):
        doc = build_document("It rose 4.2 percent from 1,500 to 2,000.")
        assert len(doc.numbers) >= 3

    def test_urls_extracted(self):
        doc = build_document("See https://example.com/page for details.")
        assert len(doc.urls) == 1

    def test_emails_extracted(self):
        doc = build_document("Write to press@example.com about it.")
        assert len(doc.emails) == 1

    def test_headline_stored_separately(self):
        doc = build_document("Body text here.", headline="A headline")
        assert doc.headline == "A headline"
        assert "A headline" not in doc.text

    def test_is_short_threshold(self):
        assert build_document("short text").is_short is True

    def test_empty_document_does_not_crash(self):
        doc = build_document("")
        assert doc.word_count == 0
        assert doc.sentence_count == 0
        assert doc.avg_sentence_words == 0.0


class TestAllCapsDetection:
    def test_detects_shouted_word_mid_sentence(self):
        doc = build_document("This is a TOTAL disaster for everyone involved.")
        assert "TOTAL" in doc.all_caps_words

    def test_ignores_sentence_initial_caps(self):
        # "ISLAMABAD — The Ministry said" is a dateline, not shouting.
        doc = build_document("ISLAMABAD — The Ministry said inflation fell.")
        assert "ISLAMABAD" not in doc.all_caps_words

    def test_ignores_dateline_with_dash(self):
        doc = build_document("KARACHI — Police reported the incident.")
        assert "KARACHI" not in doc.all_caps_words

    def test_ignores_known_acronyms(self):
        doc = build_document("The CEO met the CFO about GDP figures.")
        assert doc.all_caps_words == ()

    def test_ignores_two_letter_words(self):
        doc = build_document("The US and UK both agreed.")
        assert doc.all_caps_words == ()


class TestHelpers:
    def test_per_hundred_basic(self):
        assert per_hundred(5, 100) == 5.0

    def test_per_hundred_zero_words(self):
        assert per_hundred(5, 0) == 0.0

    def test_clamp_upper(self):
        assert clamp(150) == 100.0

    def test_clamp_lower(self):
        assert clamp(-20) == 0.0

    def test_clamp_within(self):
        assert clamp(42.5) == 42.5
