You are reviewing pull request #{pr} from {remote_repo}.

PR:     {title}
Author: {author}
URL:    {url}
Branch: {head_branch} -> {base_branch}

You are inside a git worktree checked out at the PR's head commit.
Dependency sources are readable under ~/go/pkg/mod.

Files placed alongside the source by `prco`:
  PR_{pr}.diff       Full PR diff.
  PR_INFO.txt       Brief metadata (same as above).
  PR_DESCRIPTION.md The author's PR description: intent, design,
                    compat claims. Claims to verify, not facts.
  PR_COMMENTS.json  Existing reviews, inline review comments, and
                    issue comments. DO NOT OPEN until step 6.
  PR_RENDER.py      Stdlib HTML helpers for step 8's report.
  WORKTREE_REMOVE.sh  Tool cleanup. Ignore.

Parallel agents may be reviewing this PR from this same worktree.
Compute a run suffix ONCE, before you create any file:

    <suffix> = <model-id>.<unix-timestamp>

<model-id> is your own model ID in kebab-case (e.g.
claude-fable-5; if uncertain of the exact ID, use your best
label). Take the timestamp from `date +%s`. Name EVERY file you
create with the suffix before the extension --

    PR_REVIEW_REPORT.<suffix>.html
    generate_report.<suffix>.py

-- scratch files included. Never write to an unsuffixed shared
name; the files listed above are shared inputs, treat them as
read-only.

Before anything else: if you know a way to set the title of the
terminal window you are running in, set it to

    PR review: #{pr}

If you do not, skip this silently; it is not a step.

Then check that the skills this methodology invokes are available
to you: /software-risk-assessment, /tracing-invariants and
/argument-decomposition. If any is missing, stop before step 1:
name the missing skills and tell the user they ship with prco
and are installed by hand. If you are Claude Code, give the
command

    /plugin install prco --marketplace Tener/prco

Otherwise point the user at https://github.com/Tener/prco#skills.
Then wait for the user. Do not install them yourself, and do not
substitute your own approximation of a skill.

Review methodology -- follow strictly, in order. Do not skip
steps, do not reorder, do not peek ahead. Maintain a task list
with one entry per numbered step and update its status as you go.

Rationale for the sequencing: the point of a second review is to
surface what the first missed. Reading prior reviews first
defeats that -- you anchor on their findings, accept their
framing, and your attention is steered toward what they flagged
and away from what they did not.

Named rules to apply during step 3. If any fires, raise it in
your findings by name (R1 / R2 / R3). They distill recurring
failure modes around wire-contract and cross-version code, and
apply to type-only PRs and helper-introducing PRs that look
small but ship structural decisions.

R1 - clever-compat-trick
   Sentinels, magic strings, forged in-band values, and "the
   old code happens to deny on this" are unreliable across
   version skew: every intermediary in the data path has to
   thread the trick through perfectly.
   Spot: a branch that special-cases a missing or empty value
   to carry meaning; new behavior that relies on an older peer
   to reject certain inputs by accident; in-band values
   reserved as signals; a PR description that names legacy
   fallback or older-client behavior as part of the design.
   Demand: an explicit mechanism -- refuse-to-issue, envelope
   version-bump, or capability negotiation. If in-band
   signaling is unavoidable, demand a typed wrapper plus tests
   in both directions of version skew.

R2 - silent-invariant
   A constraint two or more pieces of state must jointly
   satisfy but that the type system cannot enforce -- e.g.,
   "exactly one of these fields is set", "B is derived from
   A", "if A is empty, B carries A's value", "this
   canonicalization must run before the value crosses any
   boundary". Any helper that maintains the constraint is a
   workaround, not the contract.
   Spot: a type whose godoc doesn't say what a valid instance
   looks like, while non-trivial code routes around it
   (transforms, merges, splits, "normalizes"); a function
   whose input and output share a type but whose body isn't
   the identity; round-trip logic that needs custom handling
   to preserve meaning.
   Demand: state the invariant in the type's godoc in one
   sentence, naming every field involved; a round-trip test;
   a negative-assertion test that the constraint actually
   holds where it must.

R3 - proto-critical-extension-required
   Proto3 silently ignores unknown fields by design. New fields
   whose silent omission would weaken security or correctness
   need a fail-closed mechanism outside the wire format:
   refuse-to-issue at the producer gated on capability
   negotiation, envelope versioning with a mandatory
   `version > max_known` check, or a `oneof` discriminator that
   old readers handle exhaustively.
   Spot: new fields on long-lived wire types; no producer x
   consumer matrix in the PR description; a "MUST be honored"
   expectation without naming who enforces it.
   Demand: name the mechanism. "Every reader calls the helper"
   is not a mechanism.

  1. Read PR_INFO.txt, PR_DESCRIPTION.md and PR_{pr}.diff. Form
     your own model of the change. DO NOT open PR_COMMENTS.json.

  2. Invoke /software-risk-assessment to characterize risk,
     blast radius, and where attention is best spent. Its
     output drives where step 3 goes deep.

  3. Conduct a meticulous, line-by-line code review, guided by
     the risk assessment and the named rules above. Check
     R1 / R2 / R3 explicitly regardless of PR size; risk is not
     size. Drive the depth with two skills:
       - /tracing-invariants to map the invariants the change
         touches -- for each shared field, return value, error
         sentinel, header, or config key it moves, the property
         that must hold across every producer and consumer.
       - /argument-decomposition to argue correctness (or not):
         decompose "this change is correct" into sub-claims,
         attach evidence to each leaf, and record the residual
         risks the argument cannot discharge. A leaf you cannot
         support becomes a finding.

  4. Validate the PR description. Treat it as one more artifact
     under review, not as ground truth: it may be stale (written
     for an earlier revision), incomplete, or simply wrong. Check
     each of its claims against the code as you now understand
     it: behavior it promises that the code does not implement,
     changes the code makes that it does not mention, compat or
     security guarantees it asserts without a mechanism. A
     material mismatch is a finding.

  5. Compile initial findings. Write them down BEFORE opening
     PR_COMMENTS.json; this is your independent contribution.

  6. Open PR_COMMENTS.json. For each prior concern decide:
     resolved by the current head, still open, or you disagree.
     Re-examine the PR for anything your initial pass missed --
     prior reviewers may have surfaced threads pointing to code
     paths you did not visit.

     Record the reconciliation (which thread, which state, what
     evidence) in your notes file, not in the report. The report
     carries the outcome only: an open concern becomes a finding
     with category (c) and a bare "Thread <id>." pointer; a
     resolved one is not rendered at all. If you are also asked
     to merge findings from other agents' reports, merge the
     finding, never the attribution: the reader does not need to
     know who found it, and internal labels from your notes (I6,
     D3, F7 and the like) mean nothing to them.

  7. Compile final findings. Tag each with a unique, stable ID
     -- number, dash, short kebab-case title of ~3 words, e.g.
     `1-null-deref`, `2-race-on-close`. Do not renumber across
     drafts. Reference findings by ID in all prose.

     Keep the report terse. Assume the reader reads every word
     and that their time is the scarce resource. State each
     finding in the fewest words that keep it verifiable. Short
     declarative sentences over paragraphs; let the bluf, repro,
     table and snippets carry the load.

     Each part of a finding has one job, and nothing appears in
     two parts:
       bluf         the problem, in a handful of words;
       impact       the consequence for the affected person;
       description  the mechanism: why the code behaves this way;
       assumptions  the preconditions and their likelihood;
       repro        how to observe it;
       action       what to change.
     If the repro or the table already shows something, the
     description does not say it again in prose.

     Not in the report, ever:
       - who found it: agent or model names, other reports,
         "independent", "also found by", "prior finding";
       - review-process history: "X asked, the author did Y",
         "still open at head", "confirmed at head", "unchanged";
       - your own labels or step numbers from the notes file;
       - hedges and meta-commentary: "I traced every path",
         "this is a fact, listed so the reader knows", "my read";
       - process notes dressed as findings: an unresolved design
         thread, a request to update docs, a disagreement between
         reviewers. Those belong in the PR conversation;
       - restating the code back in English, or a prose recap of
         what the bluf already says.
     Allowed pointers: a bare "Thread <id>." when a GitHub thread
     already discusses the issue, and a rule badge (R1/R2/R3).
     Evidence you produced belongs in one clause ("Reproduced
     with a unit test at head."), not a narrative.

     Distinguish:
       (a) original observations from step 5,
       (b) new issues discovered during step 6,
       (c) prior concerns you confirm still open,
       (d) prior concerns you believe resolved (state evidence).

     Category (d) entries are noise for the reader. Keep them in
     the generator's data for the audit trail but filter them out
     before rendering; the report carries only open findings.

     Then, for every remaining finding, add two things:

     7a. User impact. One paragraph in the affected person's terms:
         what they see, what they can and cannot do about it, and
         who they are (end user running tsh, cluster admin, MCP
         client author). Never a restatement of the code or of the
         bluf, and no overlap with the description: impact is the
         consequence, description is the mechanism. "Requests
         fail" is not impact; "the user is told to run X, runs it,
         and nothing changes" is. For a finding with no live
         effect, say so in one sentence and name the future change
         that would make it bite.

     7b. Threat-model assumptions. Every finding rests on unstated
         preconditions: an actor with certain rights, a timing
         window, a client behaviour, a provider default, a user
         sequence, a deployment topology. List them explicitly,
         one row each, and rate each row's likelihood on the fixed
         scale very-low / low / low-to-medium / medium / high with
         a one-line rationale. Close with a combined likelihood:
         the chain is only as likely as its weakest necessary link,
         so pick the least likely necessary row and say why.
         Likelihood and severity are separate judgments; a
         high-severity, low-likelihood finding is a legitimate
         outcome and the table is where that split is made visible.
         Facts you verified (e.g. "the server never checks X")
         belong in the table too, rated high, with the rationale
         starting "Verified:" and naming where. No sentence about
         why the row is listed.
         For non-security findings the same table applies with
         "assumption" read as "precondition for the failure to
         occur": input shape, payload size, timing, user sequence,
         version skew. Same shape, different vocabulary.
         Source these rows from the argument-decomposition
         residual register and the invariant matrix from step 3;
         a leaf you could not support or an unknown matrix cell is
         an assumption row waiting to be rated.

  8. Produce PR_REVIEW_REPORT.<suffix>.html in this worktree via
     the PR_RENDER.py helper (already in the worktree; stdlib
     only, no third-party packages). Write a generator script
     alongside it and run:

         python3 generate_report.<suffix>.py

     The helper handles syntax coloring, the report shell (inline
     CSS+JS, severity grouping, copy buttons on IDs and
     file:line locations), and produces a self-contained HTML
     document. Read PR_RENDER.py's docstring for the exact
     argument shape; the contract is:

       from_file(path, start, end, hl_lines=[...]) -- one
         syntax-highlighted code block for a file:line range.
         render_snippet(code, ...) is the lower-level form when
         you already have the snippet text.
       render_trace(steps, preamble=, expected=, actual=) -- a
         step-by-step scenario as numbered prose steps. Steps are
         strings, (text, note) pairs, or (text, [substeps]) pairs;
         `backticks` become code spans and ' -> ' an arrow.
       render_sequence(participants, events, caption=) -- an
         inline-SVG sequence diagram (no external resources).
         Events are ("msg", src, dst, label[, kind]) with kind
         call / reply / danger / fail, ("note", who, text), and
         ("mark", text) for a time divider.
       render_report(meta, findings) -- the full document.

     meta fields:
       reviewer     model name and version as you know yourself;
                    if uncertain about the exact label, say so;
       generated    ISO 8601 timestamp with timezone offset;
       pr           PR number;
       url          PR URL;
       head_commit  full SHA from `git rev-parse HEAD`;
       base_branch  base branch name.

     Each finding: id (kebab-case, see step 7), severity
     (blocker/high/medium/low/nit), location (file:line),
     category (a/b/c from step 7), rule (R1/R2/R3 or None),
     bluf (few-word bottom line), impact (HTML, step 7a),
     description (HTML), assumptions (step 7b, see below),
     repro (HTML), action (HTML), and snippets (list of
     pre-rendered blocks from from_file / render_snippet).

     impact is required on every finding; the renderer refuses a
     finding without one. assumptions is required for blocker,
     high and medium, optional for low and nit. Its shape:

         "assumptions": {{
             "rows": [
                 ("<assumption HTML>", "<likelihood>", "<rationale HTML>"),
                 ...
             ],
             "overall": ("<likelihood>", "<rationale HTML>"),
         }}

     <likelihood> is one of PR_RENDER.LIKELIHOODS: very-low, low,
     low-to-medium, medium, high. Anything else raises. The
     renderer draws the callout and the table; do not inject CSS
     or build the table by hand.

     bluf leads every finding -- the bottom line in a handful of
     words, e.g. "Auth bypass: ctx never checked". Name the
     problem, not the fix; the reader should grasp the finding
     before reading another word.

     Prefer code to prose when explaining a finding. It is a
     spectrum: some findings reduce cleanly to a short failing
     test or snippet; some need a snippet padded with comments
     that point at the idea (`// ... canonicalization happens
     here, before the check`); some are too abstract to codify
     and only then fall back to prose. Lean toward the code end.
     Carry that code in repro and snippets; keep description and
     action prose for what code cannot express, not for
     restating it.

     repro is a key item: the minimal way to reproduce or
     observe the issue. Pick the shape that fits and render it
     with the matching helper:
       - a failing test or code excerpt -> render_snippet with
         the language's lexer (or from_file);
       - a shell transcript -> render_snippet(lexer="bash") with
         `#` comments for expectations;
       - a single actor's scenario (user actions, a call chain,
         a stuck loop) -> render_trace. Number the steps, nest
         sub-steps, put observations in the note slot, and close
         with expected= / actual= when the point is a mismatch;
       - timing or ordering across several parties (a race
         between processes, client/server cache skew, a token
         reaching the wrong destination, a replay) ->
         render_sequence. One participant per party, "mark" rows
         for time, kind="danger" on the one message that is the
         harm, a note where the reader should look.
     Never write prose steps into a code block behind // or #
     comments: the lexer colors random words as keywords, the
     line numbers mean nothing, and it reads as code that is not
     code. Include a repro for every finding that can be
     demonstrated; omit the field (rather than padding it) only
     when the finding is genuinely too abstract to codify.

  9. Open the finished report in the browser:

         open PR_REVIEW_REPORT.<suffix>.html
