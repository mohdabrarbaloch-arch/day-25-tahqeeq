"""Quick manual smoke test of the engine. Not part of the test suite."""

from app.engine import analyse

GOOD = """ISLAMABAD — The Ministry of Finance said on Monday that inflation eased to 4.2 percent in October, down from 5.1 percent the previous month, according to data released by the Pakistan Bureau of Statistics.

"The decline reflects lower food prices and a stable rupee," said a spokesperson for the ministry in a statement. The bureau reported that food inflation fell 1.8 percentage points, while core inflation, which excludes food and energy, was roughly unchanged at 6.4 percent.

Economists cautioned that the improvement may be temporary. "One month does not make a trend," said Dr. Ayesha Khan, an economist at the Lahore School of Economics, in an interview with Reuters. She noted that the figures could be revised next quarter.

The State Bank of Pakistan is expected to review its policy rate at its next meeting on 2 December. Analysts surveyed by Bloomberg estimated a 50 basis point cut is likely, though the central bank declined to comment."""

BAD = """SHOCKING!!! You won't BELIEVE what they are hiding about the economy!!!

Sources say the government is about to DESTROY the rupee completely. Insiders claim the real truth is being suppressed by the mainstream media, and thousands of people are already panicking. This is a total DISASTER and nobody is talking about it!

They don't want you to know that the deep state has a hidden agenda. Everyone knows the elites are controlling everything. Do your own research! The truth will blow your mind!!!

Share this before it gets deleted! Forward this to everyone you know. Act now before they silence us!"""

CASES = [
    ("GOOD", GOOD, "Inflation eases to 4.2 percent in October"),
    ("BAD", BAD, "SHOCKING: They are hiding the truth about the rupee!!!"),
]

for name, text, headline in CASES:
    result = analyse(text, headline=headline)
    print(f"--- {name} ---")
    print(
        f"score={result.score:.1f}  band={result.band.label}  "
        f"conf={result.confidence.label}  words={result.document.word_count}"
    )
    for signal in result.signals:
        flag = "" if signal.applies else " (n/a)"
        print(
            f"  {signal.id:22s} {signal.score:5.1f} w={signal.weight:.2f}{flag}  {signal.summary[:72]}"
        )
    print()
