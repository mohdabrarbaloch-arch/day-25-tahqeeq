"""Tests for the eleven detectors.

Each test asserts a *direction* and a *reason*, not an exact float. Pinning
exact scores would make the suite a mirror of the implementation rather than a
check on it — the point is that a hype piece scores lower than a wire story,
and that the detector names the thing that made it so.
"""

from __future__ import annotations

from app.engine import signals
from app.engine.text import build_document


def doc(text: str, headline: str = ""):
    return build_document(text, headline)


class TestAttribution:
    def test_named_source_scores_high(self):
        d = doc(
            "The ministry said in a statement that inflation fell. "
            "According to data from the bureau, prices eased. "
            "A spokesperson said the trend would continue."
        )
        result = signals.signal_attribution(d)
        assert result.score > 60
        assert result.applies

    def test_no_source_scores_low(self):
        d = doc("Prices fell last month across the whole country and everyone was happy about it.")
        result = signals.signal_attribution(d)
        assert result.score < 50
        assert "No source" in result.summary

    def test_anonymous_only_is_penalised(self):
        d = doc(
            "Sources say the deal is done. Insiders claim it will close soon. People familiar said so."
        )
        result = signals.signal_attribution(d)
        assert result.score < 55
        assert any("Anonymous" in item.label for item in result.evidence)

    def test_evidence_names_the_phrase(self):
        d = doc("According to Reuters, the deal closed on Monday morning.")
        result = signals.signal_attribution(d)
        assert any("according to" in item.detail.lower() for item in result.evidence)


class TestCertainty:
    def test_hedged_text_scores_high(self):
        d = doc(
            "The figure may be revised. Analysts suggest it could rise. "
            "Officials indicated the data is preliminary and possibly incomplete."
        )
        result = signals.signal_certainty(d)
        assert result.score > 60

    def test_absolutist_text_scores_low(self):
        d = doc(
            "This proves everything. It is undeniably true and absolutely certain. "
            "Everyone knows it, nobody disputes it, and it is 100% confirmed."
        )
        result = signals.signal_certainty(d)
        assert result.score < 50

    def test_hedge_share_drives_the_score(self):
        hedged = doc("It may rise. It could fall. It might stay. Perhaps it will change.")
        absolute = doc("It proves it. It is certain. It is undeniable. It is confirmed.")
        assert signals.signal_certainty(hedged).score > signals.signal_certainty(absolute).score


class TestSensationalism:
    def test_calm_text_scores_high(self):
        d = doc("The committee met on Tuesday and approved the budget by a narrow margin.")
        result = signals.signal_sensationalism(d)
        assert result.score >= 85

    def test_exclamations_lower_the_score(self):
        d = doc("This is amazing! Incredible! Shocking! Unbelievable!")
        result = signals.signal_sensationalism(d)
        assert result.score < 40

    def test_shouting_lowers_the_score(self):
        d = doc("This is a TOTAL DISASTER and a complete CATASTROPHE for the country.")
        result = signals.signal_sensationalism(d)
        assert result.score < 70
        assert any("Shouted" in item.label for item in result.evidence)

    def test_evidence_counts_exclamations(self):
        d = doc("Wow! Amazing! Really!")
        result = signals.signal_sensationalism(d)
        assert any("Exclamation" in item.label for item in result.evidence)


class TestHeadlineBody:
    def test_matching_headline_scores_high(self):
        d = doc(
            "Inflation eased to 4.2 percent in October, the bureau reported. "
            "The decline was driven by lower food prices across the country.",
            headline="Inflation eases to 4.2 percent in October",
        )
        result = signals.signal_headline_body(d)
        assert result.score > 70

    def test_unrelated_headline_scores_low(self):
        d = doc(
            "The cricket team won the match on Sunday after a strong batting performance.",
            headline="Government collapses amid corruption scandal",
        )
        result = signals.signal_headline_body(d)
        assert result.score < 40

    def test_no_headline_does_not_apply(self):
        d = doc("Some body text that has no headline attached to it at all.")
        result = signals.signal_headline_body(d)
        assert result.applies is False

    def test_missing_terms_are_listed(self):
        d = doc("The weather was pleasant on Sunday.", headline="Economy collapses dramatically")
        result = signals.signal_headline_body(d)
        assert any("absent" in item.label.lower() for item in result.evidence)


class TestClickbait:
    def test_plain_text_scores_high(self):
        d = doc("The council approved the measure on Tuesday by a vote of seven to two.")
        assert signals.signal_clickbait(d).score >= 85

    def test_clickbait_phrase_lowers_score(self):
        d = doc("You won't believe what happened next. This one trick changed everything.")
        assert signals.signal_clickbait(d).score < 60

    def test_question_headline_is_flagged(self):
        d = doc("Some body text about a topic.", headline="Is this the end of everything?")
        result = signals.signal_clickbait(d)
        assert any("Curiosity" in item.label for item in result.evidence)


class TestConspiracy:
    def test_clean_text_scores_high(self):
        d = doc("The report was published on Monday and is available on the ministry website.")
        assert signals.signal_conspiracy(d).score >= 90

    def test_conspiracy_phrase_lowers_score(self):
        d = doc("They don't want you to know the truth. The deep state is hiding it from you.")
        assert signals.signal_conspiracy(d).score < 50

    def test_multiple_phrases_compound(self):
        one = doc("They don't want you to know about this.")
        many = doc(
            "They don't want you to know. The deep state is involved. "
            "It is a false flag and a psyop. Do your own research."
        )
        assert signals.signal_conspiracy(many).score < signals.signal_conspiracy(one).score


class TestQuotes:
    def test_no_quotes_scores_low(self):
        d = doc("The minister announced the policy on Monday without any comment from others.")
        assert signals.signal_quotes(d).score < 50

    def test_quotes_raise_the_score(self):
        d = doc(
            'The minister said "we will act" and added "the plan is ready". '
            'An analyst said "it is a good start" in an interview.'
        )
        assert signals.signal_quotes(d).score > 50

    def test_quote_count_reported(self):
        d = doc('He said "yes" and she said "no".')
        result = signals.signal_quotes(d)
        assert any("Quotation" in item.label for item in result.evidence)


class TestDomain:
    def test_no_url_does_not_apply(self):
        d = doc("Some text about something that happened recently in the city.")
        result = signals.signal_domain(d, None)
        assert result.applies is False

    def test_tier_one_scores_high(self):
        d = doc("Some text.")
        result = signals.signal_domain(d, "https://www.reuters.com/world/story")
        assert result.score >= 85
        assert result.applies

    def test_tier_four_scores_low(self):
        d = doc("Some text.")
        result = signals.signal_domain(d, "https://www.infowars.com/story")
        assert result.score <= 20

    def test_unknown_domain_is_neutral(self):
        d = doc("Some text.")
        result = signals.signal_domain(d, "https://some-unknown-blog.example/story")
        assert 45 <= result.score <= 65

    def test_www_prefix_is_stripped(self):
        d = doc("Some text.")
        with_www = signals.signal_domain(d, "https://www.bbc.com/news/story")
        without = signals.signal_domain(d, "https://bbc.com/news/story")
        assert with_www.score == without.score

    def test_subdomain_falls_back_to_parent(self):
        d = doc("Some text.")
        result = signals.signal_domain(d, "https://news.reuters.com/story")
        assert result.score >= 85


class TestSharingBait:
    def test_clean_text_scores_high(self):
        d = doc("The report was released on Tuesday and is available online.")
        assert signals.signal_sharing_bait(d).score >= 90

    def test_share_demand_lowers_score(self):
        d = doc("Share this before it gets deleted! Forward this to everyone you know!")
        assert signals.signal_sharing_bait(d).score < 40


class TestQuantityVagueness:
    def test_no_vague_quantity_scores_high(self):
        d = doc("The figure rose to 4.2 percent from 5.1 percent, a change of 0.9 points.")
        assert signals.signal_quantity_vagueness(d).score >= 80

    def test_vague_quantity_without_numbers_scores_low(self):
        d = doc("Thousands of people were affected and countless others were displaced.")
        assert signals.signal_quantity_vagueness(d).score < 60

    def test_concrete_numbers_offset_vagueness(self):
        vague_only = doc("Thousands of people were affected by the change.")
        with_numbers = doc(
            "Thousands of people were affected: 4,200 in Lahore, 1,800 in Karachi, "
            "and 900 in Multan, according to the bureau."
        )
        assert (
            signals.signal_quantity_vagueness(with_numbers).score
            > signals.signal_quantity_vagueness(vague_only).score
        )


class TestTemporalVagueness:
    def test_no_vague_time_scores_high(self):
        d = doc("The meeting was held on 2 December 2026 at the ministry.")
        assert signals.signal_temporal_vagueness(d).score >= 80

    def test_vague_time_scores_lower(self):
        d = doc("Recently, something happened. These days nobody talks about it.")
        assert signals.signal_temporal_vagueness(d).score < 70

    def test_explicit_dates_offset_vagueness(self):
        vague = doc("Recently the policy changed.")
        dated = doc("Recently the policy changed, on 15 November 2026, after the 3 October review.")
        assert (
            signals.signal_temporal_vagueness(dated).score
            > signals.signal_temporal_vagueness(vague).score
        )


class TestRunAll:
    def test_returns_eleven_signals(self):
        d = doc("Some text about a thing that happened.")
        result = signals.run_all(d)
        assert len(result) == 11

    def test_all_scores_in_range(self):
        d = doc("Some text about a thing that happened recently in the city.")
        for signal in signals.run_all(d):
            assert 0.0 <= signal.score <= 100.0, f"{signal.id} out of range"

    def test_weights_sum_to_one(self):
        d = doc("Some text.")
        total = sum(signal.weight for signal in signals.run_all(d))
        assert abs(total - 1.0) < 1e-9

    def test_order_is_stable(self):
        d = doc("Some text.")
        first = [s.id for s in signals.run_all(d)]
        second = [s.id for s in signals.run_all(d)]
        assert first == second

    def test_deterministic(self):
        d = doc("The ministry said on Monday that prices fell 4.2 percent.")
        a = [s.score for s in signals.run_all(d)]
        b = [s.score for s in signals.run_all(d)]
        assert a == b
