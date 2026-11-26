---
name: argument-decomposition
description: Use when evaluating whether a general claim holds, or assessing the case for or against a position. Triggers — "does this argument hold?", "stress-test this claim", "prove or disprove X", "what's the case for/against Y?".
---

# Argument Decomposition

## Overview

Output is two parallel artifacts: a **verdict** (what the evidence supports or refutes) and a **residual-risks register** (what the evidence doesn't reach). The register is never absorbed into the verdict. The procedure: decompose the claim into a tree of sub-claims and attach evidence per leaf.

## Procedure

Default mode is **burden-of-proof**: no evidence, no support. Absence resolves to unresolved.

1. **Pin down the claim, its load-bearing terms, and its scope boundary.** Words like "safe", "consistent", "scales" carry the verdict's weight — define them alongside the claim; undefined, they drift and the verdict drifts with them. If the user disputes a definition, record both readings and add the dispute as a `C*/R*` residual; do not relitigate the definition mid-session. Split compound claims into separate sessions.

   **Fix the scope boundary explicitly:** state what is *in-scope* (what the claim actually asserts) versus what is merely *adjacent* (real risks in the same neighborhood that the claim does not assert anything about). The verdict answers the in-scope claim only. Adjacent risks are recorded in the residual register (step 6); they never become conditions the verdict depends on. When the claim names a specific subject — "closes *the reported* vuln", "fixes *this* race", "backfills *existing* rows" — that wording is the boundary; a different-but-related failure is adjacent, not in-scope.

2. **Decompose into sub-claims — and gate each one.** Default: break into necessary conditions ("claim holds iff A and B and C") — an AND-decomposition. If the natural decomposition is OR-gated ("claim holds if any of A, B, C"), tag the children `[or-branch]` and run each independently; the parent resolves by the dual rule (see step 5). Walk one branch at a time.

   **Admission test — apply to every candidate necessary condition before it enters the tree.** Ask: *if this sub-claim failed, would the original claim — as scoped in step 1 — be false? Or would a different, adjacent claim be false?* Only conditions whose failure makes the *scoped* claim false belong in the AND-tree. A risk whose failure leaves the scoped claim intact (it just means some other claim is false) is **not** a necessary condition — record it as a residual (step 6) and never let it gate the verdict. This is the guard against the most common and most damaging error: promoting an adjacent, out-of-scope risk into a load-bearing condition, which mechanically smuggles the residual register into the verdict. Worked contrast: for "this patch closes *the reported filename path-traversal*", a leftover symlink-following risk fails the test (the filename-traversal is still closed; a *different* vuln exists) → residual, not a condition. But for "this migration introduces *no behavior change*", a lost audit event passes the test (a behavior *did* change) → genuine necessary condition, stays in the tree.

3. **Recurse.** A sub-claim is just a claim — pin it down, decompose further if too coarse, gather evidence, resolve, log residuals. Most non-trivial claims need two or three levels before leaves are tractable. Stop descending once you can name the evidence type you'd attach.

4. **Gather evidence at each leaf.** Evidence is whatever fits: a test result, a doc citation, a proof sketch, an observation, a code reading, a measurement, an expert judgment. Investigate as far as accessible tools and sources reach. Stop when the next step costs more than the certainty it would buy.

5. **Record two things per leaf, independently.**
   - **Resolution** — supported / refuted / unresolved. Keep *refuted* and *unresolved* strictly distinct; they propagate differently. For AND-decomposition: a **refuted** child refutes the parent ("falls at C1.2"); surviving siblings are recorded but don't rescue it. An **unresolved** child does **not** refute the parent — it makes the parent *inconclusive on that condition*, never "does not hold". For `[or-branch]` children: any supported child supports the parent; refutation requires all children refuted.
   - **Residual risks** — gaps the evidence doesn't cover. They apply to any resolution; even supported leaves carry them. Each residual carries a **likelihood rating** on the fixed scale `very-low / low / low-to-medium / medium / high` and a one-line rationale for the rating. Write the residual as the unstated assumption it exposes ("an actor with X rights repoints the app", "the client reconnects within the window", "the provider rotates refresh tokens"), not as a vague gap. Rate the assumption's likelihood of holding in the real deployment, not the severity of what happens if it does — those are separate judgments and must stay separate. A verified fact that the chain depends on ("the server never checks X — confirmed") is still recorded, rated `high`, and marked as checked, so a reader knows it was not assumed.

6. **Output two parallel sections.**
   - **Verdict** — synthesis of resolutions, with three terminal states kept distinct all the way to the headline:
     - **Holds** — every in-scope necessary condition is supported.
     - **Falls at Cx** — an in-scope necessary condition is *refuted*. Only refutation earns "does not hold".
     - **Inconclusive on Cx** — an in-scope necessary condition is *unresolved* (not refuted). Phrase it "holds except for unverified Cx" / "inconclusive pending Cx" — **never** "does not hold". An *adjacent* unresolved risk (one that failed the step-2 admission test) is a residual and does not enter the verdict at all.
   - **Residual-risks register** — flat list aggregated across depths, each entry tagged with source ID. Use `C1/R*` for caveats that don't attach to any one sub-claim. Emit each entry as a triple — `(assumption, likelihood, rationale)` — and, for each refuted or unresolved claim, a **combined likelihood** equal to the least likely necessary residual under it, with a sentence saying which link that is. This is the shape downstream consumers (e.g. a PR review report's threat-model table) ingest directly.

7. **Firewall audit — before publishing.** For every item doing work in the verdict (each condition cited as making the claim hold, fall, or be inconclusive), confirm it is an in-scope necessary condition that passed the step-2 admission test. If any item influencing the verdict is actually a residual — it failed the admission test, or it lives in the residual register — that is a firewall breach: move it back to the register and re-derive the verdict without it. The rule "the register is never absorbed into the verdict" is enforced here, not merely hoped for. Concretely: if your headline is "does not hold" / "inconclusive", name the *in-scope* condition that is refuted/unresolved; if the only thing you can name is an adjacent risk, the correct headline is "holds (with residuals)".

### Alternative modes

Switchable per sub-claim at any depth:

- **Adversarial** — try to refute the sub-claim rather than confirm it. Useful when confirmation bias is a risk.
- **Falsificationist** — state what would falsify the sub-claim, then attempt that observation. Useful for empirical claims where supporting evidence is cheap and only falsification settles the question.

Modes are per sub-claim, not per session: "let's run C3.2 adversarially."

## Identifiers

```
C1 — claim                          ← root takes C1/E* and C1/R* too
├── C1.1 — sub-claim, supported
│   ├── C1.1/E1 — evidence
│   └── C1.1/R1 — residual
└── C1.2 — sub-claim, unresolved
    └── C1.2/R1 — residual
```

- **Claim** — `C1`, `C1.2`, `C1.2.3`. Same entity at every depth, including the root (which can carry its own evidence and residuals).
- **Evidence item** under a claim — `C1.2/E1`. Kind (test/doc/proof/observation/measurement/judgment) lives in the entry text. Reusable across claims.
- **Residual risk** under a claim — `C1.2/R1`. Flat (no nesting; if it decomposes, it was a sub-claim). Carries `[likelihood: <very-low|low|low-to-medium|medium|high>]` after the ID, e.g. `C1.2/R1 [likelihood: low] — an admin repoints the app; privileged and audited, migrations make it plausible`.
- **Resolution** — supported / refuted / unresolved, inlined on the claim; no ID.
- **Session** — `S2026-05-26-<slug>` if the output is persisted.

Tags: `[adversarial]` / `[falsificationist]` after an ID. Cross-references are free-form (`see C3.4/R1`).

## Output format

Persisted Markdown is the default — write out the tree, evidence, residuals, and verdict as a document. Inline conversation is fine only when the entire tree has one or two terminal leaves (i.e., `C1.1` and at most `C1.2`, with no further descent).

## Residual Risks

Limits of the procedure itself — not absorbed into any verdict:

- **Bad decomposition is invisible.** The procedure validates the form of the tree, not the correctness of its structure. A missed necessary condition or wrong granularity will resolve formally and still be wrong.
- **Evidence reachability ≠ evidence existence.** "Stop when the next step costs more than the certainty it would buy" is prior-dependent. Two operators on the same claim can stop at different depths and reach different verdicts.
- **No canonical decomposition.** Two operators may produce different trees, both formally sound. Reconciling them is manual; the skill offers no collision rule.
- **Mode and rule novelty.** The `[or-branch]` dual rule and the adversarial / falsificationist modes are unstressed at depth and across heterogeneous evidence; their soundness is asserted, not demonstrated.
- **Sunk-cost descent.** Step 3's "stop once you can name the evidence type" does not counteract the operator's prior investment in a deep branch. Trees can grow past the point where the marginal sub-claim earns its keep.
