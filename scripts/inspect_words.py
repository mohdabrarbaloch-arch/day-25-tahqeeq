from app.engine import lexicon
from app.engine.text import build_document

BAD = (
    "SHOCKING!!! You won't BELIEVE what they are hiding about the economy!!! "
    "Sources say the government is about to DESTROY the rupee and wipe out "
    "everyone's savings. The mainstream media is SILENT about this. Share this "
    "before it gets deleted!!!"
)

d = build_document(BAD)
print("words:", d.words)
print()
print("hedges found:", [w for w in d.words if w in lexicon.HEDGE_WORDS])
print("absolutes found:", [w for w in d.words if w in lexicon.ABSOLUTE_WORDS])
