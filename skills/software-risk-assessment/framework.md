# A Software Risk Assessment Framework

*The risk-profile component that slots into a decomposition-based software assurance method.*

## 1. Purpose and position

Assurance-case methods give a structure for arguing that a change is sound: a top claim decomposed into sub-claims, supported at the leaves by evidence, with explicit context, assumptions, and defeaters. That structure deliberately leaves one thing unspecified: how much of itself any given change actually needs. A two-line logging tweak does not deserve a multi-page case; a payment-flow rewrite during a regulatory audit needs more than a couple of paragraphs.

This framework is how that determination gets made — not by intuition, not by a single severity score, but by a structured profile that captures the diverse ways a change can put a system under stress, the way those stresses combine, and the modularity context that determines whether they combine cleanly or catastrophically.

The output is a profile and a derived score. The profile is the primary artifact: it preserves which kinds of risk are loaded, which is the actionable information. The score is for sorting, banding, and gating. The two together determine the required depth and shape of the assurance case the change needs to produce.

```
Change
   │
   ▼
[ Profile: 7 properties × 4 factors ] ──► per-property contributions
   │                                              │
   │                                              ▼
   │                                            Σ raw risk
   │                                              │
   │              [ Interaction factor ] ─────┤   (super-additivity from coupling)
   │                                              │
   │              [ Modularity discount ]   ─────┤   (interaction suppression)
   │                                              ▼
   │                                          Final score
   │                                              │
   │                                              ▼
   └──────────────────────────────────────► Band → required case depth & shape
```

## 2. The basis: seven software-native properties

Every running software system maintains a set of properties for the system to be considered working. These are software-native — drawn from what software actually has to do, not borrowed from finance or manufacturing. A change introduces risk in proportion to which of these properties it puts under stress, and by how much.

The seven baseline properties are independent in the sense that a change can stress any one without touching the others:

- **Correctness** — outputs match the specification under valid inputs, deterministically. Stressed by anything that changes computation, especially when the specification is fuzzy or the input space is diverse.
- **Integrity** — persistent state stays in a valid form. Stressed by anything that writes, mutates, or migrates state.
- **Availability** — the service responds within tolerable bounds. Stressed by anything that affects latency, throughput, resource consumption, or failure handling.
- **Access control** — only authorized principals can take actions. Stressed by anything that touches authn, authz, session handling, permission checks, or tenancy isolation.
- **Confidentiality** — data flows only to authorized destinations. Stressed by anything that adds outputs, surfaces internal state, logs sensitive values, or crosses trust boundaries.
- **Compatibility** — external contracts (API consumers, schemas, file formats, persisted shapes) continue to hold. Stressed by anything that changes a published interface or stored representation.
- **Operability** — failures can be detected, diagnosed, and recovered from by whoever's on call. Stressed by anything that removes observability, adds opacity, or introduces failure modes nobody has runbooks for.

The list is open-ended. Systems with domain-specific requirements — regulatory traceability, audit-log immutability, jurisdictional data residency, accessibility conformance, contractual SLAs, real-time deadlines — add corresponding properties. The structure absorbs new dimensions; the seven are the starting basis, not a closed enumeration.

## 3. The factors: four per-property loadings

For each property a change touches, four factors shape the size of the contribution. They're orthogonal to the property axis: they describe *how* a change affects a property, not *which* property is affected:

- **Stress depth** — how fundamentally the mechanism maintaining the property is altered. Cosmetic adjustment to an existing pattern: low. New mechanism replacing a load-bearing piece: high.
- **Reach** — how much of the system, internally and externally, relies on the property holding at this point. Leaf module with one caller: low. Core abstraction with broad fan-in: high.
- **Comprehension gap** — how well the existing mechanism is understood by whoever is making the change. Well-documented area, recent activity, primary authors available: low. Legacy code, last expert gone, documentation stale: high.
- **Adversarial pressure** — whether there's an active force trying to make the property fail. Internal batch job called from one place: none. Public-facing surface, monetary value attached: high.

A workable categorical scale per factor: 1 (none/low), 2 (medium), 4 (high). The contribution from a (change, property) pair is the product. The exact arithmetic is the least important part of the framework — what matters is that low values on any factor reduce the contribution, and high values on multiple factors compound. Organizations may calibrate the formula (weighted sum, capped product, hybrid) so long as that principle holds.

## 4. Per-change profile

The first artifact a change produces is its risk profile: for each property the change touches, the four factors and the resulting contribution.

```
                    Stress  Reach  Gap  Adversary  Contribution
Correctness            2      2     1       1            4
Integrity              4      4     2       1           32
Availability           1      2     1       1            2
Access control         0      0     0       0            0
Confidentiality        0      0     0       0            0
Compatibility          4      4     2       1           32
Operability            2      1     1       1            2
                                                     ----
                                                       72
```

The vector — `(4, 32, 2, 0, 0, 32, 2)` — is the primary artifact. The 72 is derived for sorting and banding. Two changes with the same total can have very different profiles, and that profile dictates different mitigations: heavy on Correctness suggests test investment; heavy on Compatibility suggests consumer coordination and versioning; heavy on Integrity suggests data validation, schema review, and reversibility planning; heavy on Access control suggests adversarial test cases and abuse modelling.

Publish the profile, not just the score. Teams that consume the scalar end up gaming the scalar; teams that consume the profile end up addressing the actual loaded properties.

## 5. Combination: how risks combine

The additive view of the profile — sum the contributions across properties — is correct only when the parts of the change are genuinely independent of each other and of the existing code. As soon as they interact, the combination is super-additive.

Sources of super-additivity within a change:

- **Coupled properties.** A change that stresses Integrity and Compatibility together is worse than the sum, because corruption now propagates through trusting consumers. Access control and Confidentiality together turn every authz miss into a leak. Correctness and Availability together turn a logic error into an outage. The properties' stresses are independent; their consequences are not.
- **Common-mode causes.** Two parts of a change motivated by the same misunderstanding fail in correlated ways. The misread of the data flow that drove the schema change also drove the API change; both will be wrong together.
- **Reviewer attention.** Bundling diverse concerns in one PR is super-linear in review cost. Two ten-point sub-changes in one diff cost more than twenty points to review, because the reviewer can't isolate "is the refactor behavior-preserving" from "is the new behavior correct".
- **Deployment non-atomicity.** Sub-changes shipped together cross the wire one instance at a time. If part A writes a field and part B reads it, instances with old A and new B exist briefly, and that combination wasn't tested.

Sources of super-additivity from existing code:

- **Latent bug activation.** Your change exercises code paths that existing dormant bugs were hiding in. The change itself is correct; the system around it isn't.
- **Implicit invariant violation.** Code is full of invariants encoded nowhere — "callers always pass non-null", "responses are always sorted", "this is only called once per request". A change that violates one breaks distant code without touching it.
- **Bug cancellation.** Two bugs that cancel each other out — one over-counts, another under-counts, net is correct. A change that fixes one introduces a regression. Never fix a single bug in a system running fine without checking what depended on the broken behavior.
- **Carrier-code fault transmission.** Your correct function is called by buggy upstream code that passes garbage. The effective risk inherits the bugginess of its surroundings.

The mathematical shape: `Risk = Σ(per-property contributions) + Interaction`. The interaction term grows with the coupling between change parts, with coupling to existing code, and with how shaky that existing code is. In poorly-isolated systems the interaction term dominates the additive sum, which is why "small changes" routinely cause incidents an order of magnitude beyond their stated scope.

The interaction is not estimated with precision. It's flagged with a categorical factor on the raw total:

- ×1 — clean change, isolated, no bundling, well-tested neighbourhood
- ×2 — one amplifier present (bundled concerns, or touches recently-reverted code, or violates a known fragile invariant)
- ×4 — two or more amplifiers
- ×8+ — multiple amplifiers in a known-fragile area

Each amplifier should have a mechanically checkable form: "does this PR bundle a refactor with a behavior change", "does any touched file have ≥3 reverts in the last quarter", "does the change cross a known-fragile interface listed in `RISKY.md`". Mechanical checks defeat self-scoring optimism.

## 6. The modularity discount

Modularity is the structural counterweight to the interaction term. Good modularity bounds each factor and suppresses cross-change interactions; pretend modularity does neither while looking like it does. The risk assessment includes an explicit modularity audit of the area being changed.

Modularity contributes the following effects, when verified:

- **Bounded reach.** A change inside module M only affects M's callers via M's contract. Reach is bounded by interface fan-in, not by the global call graph.
- **Bounded comprehension gap.** Changing M requires understanding M and its contract, not the rest of the system.
- **Stress containment.** A deep change inside M is shallow from the outside, as long as the contract holds.
- **Latent-bug isolation.** Bugs outside M don't activate from changes inside M unless M starts exposing new behavior at its interface.
- **Invariant locality.** Invariants enforced at module boundaries can't be violated by changes that respect the contract.
- **Independent rollout.** Genuinely independent modules deploy and roll back independently. Deployment non-atomicity shrinks to within-module.

The failure modes that erase these benefits:

- *Pretend modularity* — modules that share state through globals, shared databases, shared caches, shared file paths, shared queues with implicit ordering, or shared environment variables. The contract is fictional; coupling is invisible.
- *Wrong axis* — modularity drawn along boundaries that typical changes don't respect. Layered architectures where every feature crosses every layer; service boundaries that don't match data boundaries; per-team modules where features routinely span teams. The diagnostic is the count of module boundaries a typical change crosses; when high, the modularity isn't paying its costs.
- *Leaky abstractions* — interfaces that hide some details but leak performance, error modes, ordering, concurrency, retry semantics, or memory pressure. Leaked properties become Hyrum's-law load-bearing.
- *Distributed monolith* — separate services with synchronous call chains, shared schemas, or lock-step deployment. The cost of distribution without the isolation.

The audit asks: do the modules touched by this change have *enforceable* contracts (types, runtime checks, integration tests against the contract), or only *declared* ones? Enforceable contracts earn the discount; declared-only contracts don't.

A workable categorical scale:

- ×1.0 — pretend or wrong-axis modularity in the touched area
- ×0.8 — declared contracts, generally respected, no enforcement
- ×0.6 — enforceable contracts (types, integration tests against the interface)
- ×0.4 — enforceable contracts plus strong fault isolation (separate process/service with hard boundary)

The discount applies after the interaction factor — modularity reduces the *combined* risk, not the per-property contributions.

## 7. From score to band

The full computation:

```
Raw      = Σ over properties of (stress × reach × gap × adversary)
Adjusted = Raw × Interaction-factor
Final    = Adjusted × Modularity-discount
```

Bands drive process, not feelings. Illustrative thresholds (calibrate locally so the band distribution is useful — most changes routine, a handful elevated, very few critical):

- **Routine (0–10):** standard PR review, normal test additions; no written case required.
- **Standard (11–50):** standard review plus tests addressing each loaded property; brief PR description naming the loaded properties.
- **Elevated (51–150):** domain expert review, written assurance case structured around the loaded properties, staged rollout with explicit verification.
- **High (151–500):** pre-implementation design review, full assurance case with named defeaters and rollback plan, post-deploy verification, named accountable owner.
- **Critical (>500):** formal sign-off, multi-reviewer assurance case, dependency mapping, rehearsed rollback, monitoring plan with defined success criteria, automatic post-deploy review.

## 8. Integration with the assurance case

The risk profile slots into the decomposition-based assurance case in three places:

- **It scopes the case.** Every property with non-zero loading becomes a required sub-claim. A change loaded on Integrity needs a sub-claim about state validity; loaded on Compatibility, a sub-claim about preserved contracts; on Access control, a sub-claim about authorization correctness. Zero-loaded properties don't need sub-claims. The profile is the table of contents.
- **It dictates the strategy.** Each loaded property suggests a decomposition strategy for its sub-claim. Integrity decomposes by data path or invariant. Compatibility decomposes by consumer or contract surface. Access control decomposes by principal type or operation. Correctness decomposes by input class. Availability decomposes by failure mode. The profile is upstream of strategy selection.
- **It informs the context section.** The change's profile, the interaction factor, and the modularity audit findings all belong in the case's stated context. "This change scores 280 on the risk framework; interaction factor 2× because it bundles a refactor with a behavior change; modularity discount 0.6× because the storage layer has enforceable contracts" is a one-line summary that locates the case in the framework.

The depth of evidence at the leaves is set by the band. A routine change has informal review notes; an elevated change has property-specific tests with mutation-score evidence; a critical change has formal verification, independent reproduction, or both at the leaves. The defeaters section of the case is enriched directly from the amplifiers that drove the interaction factor — each amplifier is a named defeater for the case.

## 9. Calibration and operation

The framework only works if operated honestly. Five practical disciplines:

- **Mechanically checkable factors.** Factors should be mechanically checkable wherever possible. "Does the diff touch any file under `/auth/`?" admits no gaming; "is this change risky?" invites it. Self-scoring authors will tend to under-score subjective factors; checkable ones level the field. As much as possible, derive factor values from the diff and the repository state, not from author judgment.
- **Ordinal calibration.** Weights are ordinally calibrated, not measured. "Touching auth is roughly four times a logging change" is the discipline; arguing about whether it's exactly 4 or 5 is the trap. Categorical factors (1 / 2 / 4) work better than continuous scales for this reason.
- **Recalibrate from incidents.** Every postmortem asks: would this framework have flagged the change that caused this? If not, what's missing? Property weights, factor weights, the property list itself, the interaction amplifiers, the band thresholds — all are living. Static menus calcify into uselessness within a year.
- **Watch the distribution.** If most changes land in the same band, the framework has lost discriminating power. Quarterly audit of the distribution against process load is the diagnostic. CVSS-shaped concentration at the top is the failure mode to detect early.
- **Publish profiles, not scores.** The vector is the primary artifact; the scalar is for sorting. Profiles preserve the qualitative information about *why* the risk is loaded, which is what drives the right mitigations.

## 10. Worked examples

### Adding a logging statement to an existing path

| Property | Stress | Reach | Gap | Adv | Contribution |
|---|---|---|---|---|---|
| Operability | 1 | 1 | 1 | 1 | 1 |

Raw: 1. Interaction ×1. Modularity ×1. Final: ~1. **Routine.** No case required.

### Hot-path query optimization

| Property | Stress | Reach | Gap | Adv | Contribution |
|---|---|---|---|---|---|
| Correctness | 2 | 2 | 1 | 1 | 4 |
| Integrity | 1 | 2 | 1 | 1 | 2 |
| Availability | 4 | 4 | 2 | 1 | 32 |
| Operability | 2 | 2 | 2 | 1 | 8 |

Raw: 46. Interaction ×2 (touches a known-fragile cache layer). Modularity ×0.8 (declared contracts, no enforcement). Final: ~74. **Elevated.** Case structured by performance correctness, latent-failure-mode coverage at higher cardinality, observability of new states, named rollback path.

### Schema migration dropping a column with live data

| Property | Stress | Reach | Gap | Adv | Contribution |
|---|---|---|---|---|---|
| Correctness | 1 | 2 | 1 | 1 | 2 |
| Integrity | 4 | 4 | 2 | 1 | 32 |
| Availability | 2 | 2 | 1 | 1 | 4 |
| Compatibility | 4 | 4 | 2 | 2 | 64 |

Raw: 102. Interaction ×4 (Integrity × Compatibility coupling, irreversibility, common-mode upstream change). Modularity ×0.8. Final: ~326. **High.** Case structured by data-loss prevention, consumer migration, irreversibility planning, rehearsed restore-from-backup with bounded data-loss window.

### Auth refactor consolidating three permission checks into one helper

| Property | Stress | Reach | Gap | Adv | Contribution |
|---|---|---|---|---|---|
| Correctness | 1 | 2 | 1 | 2 | 4 |
| Access control | 4 | 4 | 2 | 4 | 128 |
| Confidentiality | 2 | 2 | 1 | 4 | 16 |
| Compatibility | 1 | 2 | 1 | 1 | 2 |

Raw: 150. Interaction ×2 (Access × Confidentiality coupling). Modularity ×0.6 (auth module has enforceable contracts and integration tests). Final: ~180. **High.** Case structured by per-principal authorization correctness across every old call site, abuse-case testing, regression coverage proving equivalence with the prior three checks.

The profiles show what a single severity score conceals. The schema migration and the auth refactor end up in the same band, but for different reasons and with different shapes: the migration's risk is concentrated in irreversibility and consumer coupling; the auth refactor's risk is concentrated in authorization correctness under adversarial pressure. Their cases need different decomposition strategies, different evidence, and different rollback plans.

## 11. What this framework deliberately does not do

It does not produce a probability of failure. It produces a structured measure of *concern* — an answer to "how much should we worry about this, in what ways, and what should we do about it?" The number isn't a forecast; it's a budget. This is the same reason FICO isn't a probability and clinical scores aren't probabilities — they're decision-support, not predictions.

It does not eliminate judgment. The factors, the property loadings, the interaction call, the modularity audit — all require judgment. What the framework does is *locate* the judgment: it forces the judgment to be applied to specific, named questions in specific, named places, where it can be reviewed, challenged, and recalibrated. Judgment in a vacuum becomes LGTM; judgment in a framework becomes assurance.

It does not work without recalibration. Frameworks that don't get retuned from incident data drift into folklore within a year. The recalibration loop is part of the framework, not optional decoration. CVSS's failure to do this is the cautionary case.

It does not work in pretend-modular systems. The modularity discount has teeth only when modularity is real. In systems where every module shares state with every other through a back door, the interaction term dominates everything else and the score becomes a measure of how much trouble the team is about to get into rather than how much trouble the change should cause. The framework still surfaces this — the score is just always elevated — but the right response is to fix the modularity, not the changes.

It does not substitute for the assurance case. The risk profile says how much case is needed and what shape it should take; the case is still the artifact that argues the change is sound. Risk assessment without an assurance case is gating without justification; an assurance case without risk assessment is justification without scaling. The two pieces are designed to fit together — the framework here, the case in the companion document.
