# Usage

## What this actually does

Tahqeeq reads a piece of news text and scores **how it is written**. It looks
for the habits of careful reporting — named sources, hedged claims, concrete
figures, direct quotations — and the habits of persuasion — hype, absolutism,
manufactured urgency, vague sourcing.

It does **not** know whether the claims are true. It has no fact database and
no knowledge base. A careful liar writes like a journalist, and this tool will
score them well. That is a real limit, and the app says so on every screen.

## The three ways in

### 1. Paste text

The main path. Paste the article body, and optionally the headline.

The headline is worth adding: it unlocks the **headline vs body** check, which
is the one that catches the most common form of misleading-but-technically-true
writing — a headline that promises something the article never says.

### 2. Paste a URL

The page is fetched, stripped to readable text, and analysed. The publisher's
domain is also scored against a static tier table.

Two things to know:

- Pages that need JavaScript to render will fail with a clear message. The
  fetcher does not run a browser.
- Private, loopback and link-local addresses are rejected. That is the SSRF
  guard, and it is deliberate.

### 3. Live preview

The preview endpoint scores text without saving it, and needs no account. It is
what the "Analyse" button calls when you are not logged in.

## Reading the result

### The score

0–100, where **higher means the writing looks more like reporting**. It is a
weighted mean over the eleven signals that apply, renormalised so a missing
input does not drag the number toward the middle.

### The band

| Band | Range | What it means |
|---|---|---|
| Strong signals | 75–100 | Named sources, hedged claims, concrete figures |
| Reasonable | 60–74 | Mostly conventional, a few weak spots |
| Mixed | 45–59 | Some of each; the text alone does not settle it |
| Weak signals | 30–44 | Leans on hype, vague sourcing or urgency |
| Poor signals | 0–29 | Emotional language, little attribution |

### The confidence

This is about **how much text there was**, not how sure the model is.

| Level | Words |
|---|---|
| Very low | under 80 |
| Low | 80–199 |
| Moderate | 200–499 |
| High | 500–1199 |
| Very high | 1200+ |

A 60-word post cannot be judged the way a 1,200-word article can. Reporting
high confidence on a short text would be the most dishonest thing this app
could do, so it does not.

### The signals

Eleven detectors, each with a weight, a score, a one-line summary, and the
evidence that produced it. Click any row to see the exact spans it matched.

| Signal | Weight | What it measures |
|---|---|---|
| Attribution | 15% | Named sources vs anonymous "sources say" |
| Certainty | 12% | Absolute claims vs hedged language |
| Sensationalism | 11% | Exclamation density, ALL-CAPS, high-arousal words |
| Headline vs body | 10% | Does the body contain the headline's claim |
| Clickbait | 10% | Curiosity-gap and listicle constructions |
| Conspiracy framing | 9% | "They don't want you to know" |
| Direct quotes | 8% | Quotations per 100 words |
| Source domain | 7% | Publisher tier (only with a URL) |
| Sharing bait | 7% | "Share before it's deleted" |
| Quantity precision | 6% | "Thousands of" vs an actual number |
| Time precision | 5% | "Recently" vs a real date |

## Worked example

Take this wire-style paragraph:

> ISLAMABAD — The Ministry of Finance said on Monday that inflation eased to 4.2
> percent in October, down from 5.1 percent the previous month, according to
> data released by the Pakistan Bureau of Statistics.

It scores well, and the reasons are visible:

- **Attribution** — "said", "according to data released by" are named-source
  references.
- **Certainty** — no absolutism; the figures are attributed rather than asserted.
- **Quantity precision** — 4.2, 5.1, October: concrete.
- **Sensationalism** — calm register. Note that "ISLAMABAD" is *not* counted as
  shouting: it is a dateline, and the detector knows the difference.

Now this:

> SHOCKING!!! You won't BELIEVE what they are hiding about the economy!!!
> Sources say the government is about to DESTROY the rupee. Share this before
> it gets deleted!

Every signal that matters goes the other way, and each one names its evidence:
three high-arousal words, thirteen exclamation marks, three shouted words, two
anonymous-source references and nothing named, four calls to share.

## Saving and history

Logged in, analyses are saved and listed under **History**. Each one stores the
full signal payload, so reopening it does not re-run the engine — you see
exactly what you saw the first time.

## What it will get wrong

- **Satire and parody.** Well-written satire scores badly, because it uses the
  techniques of bad writing on purpose.
- **Non-English text.** The lexicons are English. Urdu and Roman-Urdu will score
  poorly for reasons that have nothing to do with reliability.
- **Careful liars.** Style is not intent. A skilled propagandist who names
  sources and hedges claims will score well.
- **Short texts.** Under 200 words, treat the score as a hint, not a reading.
- **Legitimate urgency.** A genuine emergency alert will look like sharing bait,
  because it is written like one.

Use it as one input. Never as a verdict.
