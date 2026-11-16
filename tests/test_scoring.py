"""Tests for aggregation, bands and confidence.

The two behaviours worth guarding here are the ones that are easy to get
subtly wrong: renormalising when a signal does not apply, and refusing to
claim high confidence on a short text.
"""

from __future__ import annotations

from app.engine.scoring import BANDS, aggregate, analyse, band_for, confidence_for
from app.engine.signals import Signal
from app.engine.text import build_document


def make_signal(score: float, weight: float, applies: bool = True) -> Signal:
    return Signal(
        id="test",
        label="Test",
        weight=weight,
        score=score,
        summary="",
        evidence=(),
        applies=applies,
    )


class TestAggregate:
    def test_single_signal_returns_its_score(self):
        assert aggregate((make_signal(80.0, 1.0),)) == 80.0

    def test_weighted_mean(self):
        signals = (make_signal(100.0, 0.5), make_signal(0.0, 0.5))
        assert aggregate(signals) == 50.0

    def test_weights_are_respected(self):
        signals = (make_signal(100.0, 0.9), make_signal(0.0, 0.1))
        assert aggregate(signals) == 90.0

    def test_non_applying_signals_are_dropped(self):
        # A 0-scoring signal that does not apply must not drag the mean down.
        signals = (make_signal(80.0, 0.5), make_signal(0.0, 0.5, applies=False))
        assert aggregate(signals) == 80.0

    def test_renormalisation_not_penalisation(self):
        """Dropping a signal must not change the score of the rest."""
        with_na = (make_signal(70.0, 0.5), make_signal(90.0, 0.5, applies=False))
        without = (make_signal(70.0, 0.5),)
        assert aggregate(with_na) == aggregate(without)

    def test_empty_returns_neutral(self):
        assert aggregate(()) == 50.0

    def test_all_not_applying_returns_neutral(self):
        signals = (make_signal(10.0, 0.5, applies=False),)
        assert aggregate(signals) == 50.0

    def test_result_is_clamped(self):
        assert 0.0 <= aggregate((make_signal(100.0, 1.0),)) <= 100.0


class TestBands:
    def test_high_score_is_strong(self):
        assert band_for(85.0).id == "strong"

    def test_mid_score_is_mixed(self):
        assert band_for(50.0).id == "mixed"

    def test_low_score_is_poor(self):
        assert band_for(10.0).id == "poor"

    def test_boundaries_are_inclusive(self):
        assert band_for(75.0).id == "strong"
        assert band_for(60.0).id == "reasonable"
        assert band_for(45.0).id == "mixed"
        assert band_for(30.0).id == "weak"

    def test_every_band_has_a_description(self):
        for band in BANDS:
            assert band.description
            assert band.label

    def test_bands_are_ordered_descending(self):
        thresholds = [band.min_score for band in BANDS]
        assert thresholds == sorted(thresholds, reverse=True)


class TestConfidence:
    def test_very_short_text_is_very_low(self):
        d = build_document(" ".join(["word"] * 40))
        assert confidence_for(d).level == "very_low"

    def test_short_text_is_low(self):
        d = build_document(" ".join(["word"] * 150))
        assert confidence_for(d).level == "low"

    def test_medium_text_is_moderate(self):
        d = build_document(" ".join(["word"] * 350))
        assert confidence_for(d).level == "moderate"

    def test_long_text_is_high(self):
        d = build_document(" ".join(["word"] * 800))
        assert confidence_for(d).level == "high"

    def test_very_long_text_is_very_high(self):
        d = build_document(" ".join(["word"] * 1500))
        assert confidence_for(d).level == "very_high"

    def test_reason_mentions_word_count(self):
        d = build_document(" ".join(["word"] * 300))
        assert "300" in confidence_for(d).reason


class TestAnalyse:
    def test_good_article_scores_higher_than_bad(self, good_article, bad_article):
        good = analyse(good_article, headline="Inflation eases to 4.2 percent in October")
        bad = analyse(bad_article, headline="SHOCKING: They are hiding the truth!!!")
        assert good.score > bad.score
        assert good.score - bad.score > 25

    def test_good_article_lands_in_a_high_band(self, good_article):
        result = analyse(good_article, headline="Inflation eases to 4.2 percent in October")
        assert result.band.id in {"strong", "reasonable"}

    def test_bad_article_lands_in_a_low_band(self, bad_article):
        result = analyse(bad_article)
        assert result.band.id in {"weak", "poor"}

    def test_deterministic(self, good_article):
        first = analyse(good_article).score
        second = analyse(good_article).score
        assert first == second

    def test_top_concerns_are_the_lowest(self, bad_article):
        result = analyse(bad_article)
        concerns = result.top_concerns
        assert len(concerns) == 3
        assert all(signal.applies for signal in concerns)
        # The lowest-scoring applied signal must be in the concerns.
        lowest = min((s.applies and s.score) or 101 for s in result.signals)
        assert any(abs(signal.score - lowest) < 1e-9 for signal in concerns)

    def test_top_strengths_are_the_highest(self, good_article):
        result = analyse(good_article)
        strengths = result.top_strengths
        assert len(strengths) == 3
        highest = max(s.score for s in result.signals if s.applies)
        assert any(abs(signal.score - highest) < 1e-9 for signal in strengths)

    def test_as_dict_is_json_serialisable(self, good_article):
        import json

        result = analyse(good_article)
        payload = result.as_dict()
        text = json.dumps(payload)
        assert len(text) > 100
        assert payload["score"] == round(result.score, 2)

    def test_source_url_flows_through(self):
        result = analyse("Some text about a thing.", source_url="https://www.reuters.com/x")
        domain = next(s for s in result.signals if s.id == "domain")
        assert domain.applies is True
        assert domain.score >= 85

    def test_no_url_means_domain_does_not_apply(self):
        result = analyse("Some text about a thing.")
        domain = next(s for s in result.signals if s.id == "domain")
        assert domain.applies is False

    def test_applied_signals_excludes_na(self):
        # With no headline and no URL, two signals do not apply.
        result = analyse("Some text about a thing.")
        not_applying = [s for s in result.signals if not s.applies]
        assert len(not_applying) == 2
        assert len(result.applied_signals) == len(result.signals) - 2
