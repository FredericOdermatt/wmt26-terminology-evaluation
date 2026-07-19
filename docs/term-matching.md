# Term matching: how the term sets were built and why scoring them is not trivial

Term success ("did the system use the required terminology?") sounds like a substring check:
for each required term, test whether one of its target renditions appears in the system output.
On this data, the naive check is wrong in five distinct ways. This page documents how the term
annotations were actually constructed, the failure modes we measured, and the matching semantics
the evaluation uses. All numbers are from the unified datasets (`data/unified/private/`), measured
by scoring the gold references as if they were a submission (the "oracle" check,
`make evaluate-oracle`).

## How the term annotations were constructed

The two term-annotated providers built their data differently, and the difference drives the
matching design.

**laniqo (en→pl)** annotated terms manually per sentence, tracking the *inflected* surface form
(the CSVs carry a separate `term (PL - inflection)` column). A mechanical predicate — "glossary
source appears in the source sentence AND a base-form target appears in the reference" — recalls
only 33–40% of their annotations: the annotations follow Polish morphology, not base-form
co-occurrence. The converse also matters: 11–25% of mechanical co-occurrences were *not*
annotated, so the per-sentence term lists are human-selective, not exhaustive.

**vicomtech (es→eu)** annotations are reproducible almost perfectly (98–100%) by a
*case-insensitive substring* predicate without word boundaries: a glossary pair is annotated where
the source is a substring of the Spanish sentence and a target a substring of the Basque sentence.
This explains annotations like `src="potencia"` wrapping the word *potencial* — a lemma-level
(arguably wrong-sense) match produced by the mining itself. A word-boundary version of the same
predicate recalls only 21–37% of the annotations, confirming the mining used raw substrings.

## Failure modes of naive matching

### 1. Inflection

Polish inflects terms heavily: the annotated base form appears verbatim in the reference for only
34–41% of laniqo term occurrences (`wiper` → *wycieraczka*, reference says *wycieraczce*). Basque
agglutinates suffixes but keeps the stem as a prefix, so base forms match 98–100% as raw
substrings — but only 44–54% once matching is anchored to word boundaries (*garraio* does not
boundary-match inside *garraioaren*). The attested surface forms, not the base forms, carry
Basque scoring.

The unified data mitigates this with `TermPair.target_inflected`, the gold surface form attested
in the reference (laniqo: from the CSV inflection column, 80–92% coverage; vicomtech: the covered
text of the eu-side `<term>` tags, 98–99% coverage). Matching in lemma space (Stanza pl/eu) closes
most of the remaining gap; on a previous data version, base-form matching scored 31% on gold
references where lemma-space matching scored 91.5%.

### 2. Nested terms

Glossaries contain terms that are substrings of other terms: 83 nested source pairs in
mechanical-engineering, 129 in medical (*tłumik drgań* ⊂ *tłumik drgań skrętnych*,
*angiotensyna I* ⊂ *angiotensyna II*). When both terms are required in the same paragraph, a
greedy matcher that lets the short term consume the long term's span reports the long term as
missing. The bias is systematic: greedy always penalizes the longer, more specific term. Nested
targets are co-required on the same *sentence* 7–13 times per laniqo domain; at paragraph scope
(where submissions align) the collision rate is higher.

### 3. Straddling overlaps

Terms can overlap without nesting: for terms *ab* and *bc*, the text *abc* contains both, sharing
*b*. The target-side glossaries contain 25–39 such straddling pairs per laniqo domain. Under
exclusive matching, *abc* can satisfy only one of the two.

### 4. Short keys and word boundaries

The eseu glossaries include abbreviation entries released to competitors: `MT` → [*tentsio
ertain*, *TE*], `PE`, `ST`, `IT`, `Te`. As raw substrings these match inside ordinary words (*te*
⊂ *kojinete*, *ate* ⊂ *bateria*) — the nominally 500+ "nested pairs" in the eseu glossaries are
mostly this artifact. Matching must therefore anchor to token boundaries — which simultaneously
means the evaluation is *stricter* than the substring mining that produced the vicomtech
annotations, and that policy question (does an abbreviation-only rendition count?) is still open
with the provider.

### 5. Data noise and the compliance ceiling

Even gold references do not reach 100% under surface matching. The oracle check yields
(word-boundary-anchored; *overlap* allows span reuse, *exclusive* is the maximal disjoint
matching):

| set | base | attested | overlap | exclusive |
|---|---|---|---|---|
| enpl mech-eng t1 | 66.6% | 79.8% | 95.5% | 86.4% |
| enpl mech-eng t2 | 62.0% | 79.7% | 92.0% | 83.7% |
| enpl medical t1 | 45.5% | 83.7% | 88.9% | 86.0% |
| enpl medical t2 | 53.0% | 92.5% | 96.0% | 93.8% |
| eseu (all 4) | 44–54% | 97–99% | 98–100% | 97–99% |

The overlap-vs-exclusive gap on gold references (up to 9 points for enpl, under 1 point for eseu)
exposes a sixth effect: **repeated mentions**. A term annotated in several sentences of the same
paragraph demands that many disjoint renditions under exclusive matching, but a fluent reference
often pronominalizes repeat mentions, so the reference itself contains fewer renditions than
annotations. Whether the metric should require one rendition per annotated occurrence or one per
term type per paragraph is a policy choice; the oracle gap quantifies its impact.

The enpl gap splits into three causes (245 cases, listed in `reports/laniqo-term-mismatch-cases.csv`):
181 occurrences lack an attested-inflection annotation and inflect in the reference (recoverable
by lemma matching); ~64 carry typos or invisible characters on either side (*rozrzędu* for
*rozrządu*, zero-width spaces — reported to the provider); and a residue where the reference
genuinely uses a synonym (`vehicle horn` annotated as *sygnał dźwiękowy*, reference consistently
says *klakson*). The last class is the honest ceiling: **references are not 100%
terminology-compliant**, so oracle rates, not 100%, are the meaningful upper bound for every
surface metric.

## Matching semantics

The evaluation uses maximal exclusive matching (the `match_accuracy` construction):

- Matching operates on token-anchored spans, in surface space and in lemma space; a span matched
  in either space blocks the corresponding range in both.
- Each required term occurrence must be covered by its own span; spans are exclusive (no
  double-consumption). With *n* annotated occurrences of a term, the output must contain *n*
  disjoint renditions.
- Any listed target alternative counts (competitors received the alternatives).
- The score for a paragraph is the *maximum* number of simultaneously satisfiable term
  occurrences over all span assignments — computed exactly over per-occurrence binary masks with
  branch-and-bound (the same quantity as match_accuracy's exhaustive search). Greedy assignment
  is a lower bound and is not used.

For diagnostics we additionally report the *overlap-allowed* variant (each term checked
independently, spans may overlap). It is a strict upper bound of the exclusive score; the gap
between the two quantifies how much nesting/straddling actually affects a given system.

## Derived relation tables

The nesting and straddle relations are computable directly from the released glossaries, with no
extra data: for every ordered pair of entries, test token-boundary containment of one key (or
target) in the other, and test proper prefix/suffix overlap for the straddle case. This is an
O(n²) sweep over at most ~800 entries per glossary. Publishing these tables alongside the metric
description tells competitors exactly which required terms can conflict, without re-releasing any
task data. An explicit per-entry exclusivity flag in the released format would be cleaner still —
that is a proposal for the next edition, not something to change mid-competition.
