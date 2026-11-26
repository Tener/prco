# prco

`prco <PR>` checks out a GitHub PR into its own git worktree, along with the
diff, description and existing review comments. It also adds a review prompt.
Hand that prompt to an AI agent and you get back a self-contained HTML review
report: findings grouped by severity, each with user impact and threat-model
assumptions.

![prco checking out a PR](demo/demo.gif)

    prco 66556
    cd ~/code/teleport-pr-66556 && claude "@PR_REVIEW.txt"
    # ... agent reviews, writes PR_REVIEW_REPORT.<model>.<ts>.html, opens it
    ./WORKTREE_REMOVE.sh

## Quick start

1. Requirements: Python 3.11+, [`gh`](https://cli.github.com/)
   (authenticated), and a local clone of each repo you review.
2. Install: `make install` symlinks `prco.py` as `~/.local/bin/prco`
   (`BINDIR=...` to change it; it must be on your `PATH`).
3. Configure: `prco --edit-config` writes a commented template and opens it in
   `$VISUAL`/`$EDITOR`. See [Configuration](#configuration).
4. Run `prco <PR_NUMBER>` or `prco <GITHUB_PR_URL>`, then the printed
   `cd ... && claude "@PR_REVIEW.txt"` line.

`make help` lists all targets; `make uninstall` removes the symlink,
`make test` runs the tests. `demo/record.sh` re-records the animation above.

## Usage

    prco <PR_NUMBER>        # PR in the default (first) repo
    prco <GITHUB_PR_URL>    # PR in the matching configured repo

    prco --update <PR>      # -u: refresh an existing checkout in place
    prco --suffix <PR>      # -s: create <repo>-pr-<N>-<YYYYmmdd-HHMMSS> instead
    prco --branch <PR>      # -b: local branch instead of a detached HEAD
    prco --edit-config      # -e: open the config file

prco creates `<clone-parent>/<repo>-pr-<N>/`, a worktree detached at the PR's
head. Fork, merged and closed PRs use upstream `refs/pull/<N>/head`. It then
prints one start command per available agent: always `claude`, plus `codex`
when installed, and a `prism <agent>` variant of each when `prism`'s router is
up (routing the agent's traffic through the Teleport cluster).

## Configuration

prco reads `${XDG_CONFIG_HOME:-~/.config}/prco/config.toml`, an ordered list
of repositories. The first entry is the default for bare PR numbers.

    [[repo]]
    clone    = "~/code/teleport"
    url      = "https://github.com/gravitational/teleport"
    setup    = "rm -f AGENTS.md"        # optional: run in the worktree at setup
    teardown = "git restore AGENTS.md"  # optional: run in cleanup before removal

    [[repo]]
    clone = "~/code/rfd"
    url   = "https://github.com/gravitational/rfd"

Per repo: `clone` (local path, `~` expanded) and `url` (full GitHub URL) are
required; `setup` and `teardown` are optional shell commands. prco opens the
editor automatically when there's no config, no default repo, or no repo
matching a PR URL.

## Files in the worktree

| File                          | Purpose                                             |
| ----------------------------- | --------------------------------------------------- |
| `PR_INFO.txt`                 | Title, author, URL, base, head, labels, timestamps. |
| `PR_DESCRIPTION.md`           | PR description (body) as written by the author.     |
| `PR_<N>.diff`                 | Full PR diff.                                       |
| `PR_COMMENTS.json`            | Reviews + inline review comments + issue comments.  |
| `PR_REVIEW.txt`               | Briefing and review methodology for the agent.      |
| `PR_RENDER.py`                | Stdlib render helpers (syntax coloring + HTML).     |
| `.claude/settings.local.json` | Grants the agent read access to `~/go/pkg/mod`.     |
| `WORKTREE_REMOVE.sh`          | Safe cleanup; aborts if you have other changes.     |

`PR_REVIEW.txt` and `PR_RENDER.py` are copied from `prompts/` at setup and
again on `--update`; older worktrees keep their old copies until then.

## The report

The agent writes `PR_REVIEW_REPORT.<model>.<ts>.html` in the worktree:
self-contained, dark-themed, severity-grouped, with highlighted snippets and
copyable IDs / `file:line` locations, and opens it in the browser. The model
ID and unix timestamp suffix let several agents review the same PR in
parallel from one worktree.

Every finding carries a **User impact** callout (what the affected person
sees and can or cannot do) and, for medium severity and above, a
**Threat-model assumptions** table: the unstated preconditions the failure
depends on, each rated on a fixed likelihood scale (`very-low` … `high`) with
a rationale, plus a combined likelihood set by the weakest necessary link.
The renderer refuses findings that omit them. Resolved prior concerns are not
rendered; they stay in the generator's data only.

## Existing checkouts

If `<repo>-pr-<N>/` already exists, prco stops and offers two modes:

- `--update` (`-u`): reuse the directory. Runs the repo `teardown`, fetches
  the current PR head, `git reset --keep`s the worktree onto it (local edits
  and untracked files such as review reports survive; a conflicting local
  change aborts the reset), rewrites the `PR_*` files and
  `WORKTREE_REMOVE.sh`, then runs `setup` again. The directory must be a
  worktree of the clone, either detached or on the PR's branch.
- `--suffix` (`-s`): leave it alone and create
  `<repo>-pr-<N>-<YYYYmmdd-HHMMSS>/` next to it. Works without a prior
  checkout too, when you want several independent copies.

Worktrees are detached by default, so any number of them can sit on the same
PR head. `--branch` (`-b`) checks out a local branch named after the PR head
instead (reset with `git worktree add -B`, so a stale local copy doesn't
anchor it on old commits); only one worktree can hold a branch, so prco
refuses if another already does. For fork PRs, the local branch is named
`pr-<N>` to avoid resetting an upstream branch with the same name as the
fork's head.
