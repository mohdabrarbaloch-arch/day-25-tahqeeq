"""Inspect per-signal scores for the hype sample."""

from app.engine import analyse

BAD = (
    "SHOCKING!!! You won't BELIEVE what they are hiding about the economy!!! "
    "Sources say the government is about to DESTROY the rupee and wipe out "
    "everyone's savings. The mainstream media is SILENT about this. Share this "
    "before it gets deleted!!!"
)

r = analyse(BAD)
print(f"score={r.score}  band={r.band.id}  confidence={r.confidence.level}")
print(f"words={r.document.word_count}\n")
for s in r.signals:
    flag = "  " if s.applies else "NA"
    print(f"{flag} {s.id:<20} w={s.weight:.2f} score={s.score:6.1f}  {s.summary[:70]}")
