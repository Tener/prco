# prco

Checks out a GitHub PR into its own worktree with the diff, description,
review comments and a review prompt. Hand the prompt to an AI agent; it
writes an HTML review report.

![prco checking out a PR](demo/demo.gif)

## Quick start

Needs Python 3.11+, an authenticated [`gh`](https://cli.github.com/), and a
local clone of each repo you review.

    make install            # symlink prco.py as ~/.local/bin/prco (BINDIR=...)
    prco --edit-config      # list your repos
    prco <PR>               # then run the printed `cd ... && claude ...` line

`make help` lists the other targets; `demo/record.sh` re-records the GIF.

## Usage

    prco <PR_NUMBER>        # PR in the default (first) repo
    prco <GITHUB_PR_URL>    # PR in the matching configured repo
    prco -u, --update <PR>  # refresh an existing checkout (git reset --keep)
    prco -s, --suffix <PR>  # new <repo>-pr-<N>-<timestamp> next to an existing one
    prco -b, --branch <PR>  # local branch instead of a detached HEAD (pr-<N> for forks)
    prco -e, --edit-config  # open the config file

The worktree is `<clone-parent>/<repo>-pr-<N>/`. prco also suggests `codex`
when installed, and `prism` variants when its router is up.
`./WORKTREE_REMOVE.sh` in the worktree tears it down.

## Configuration

`${XDG_CONFIG_HOME:-~/.config}/prco/config.toml`; the first repo is the
default.

    [[repo]]
    clone    = "~/code/teleport"
    url      = "https://github.com/gravitational/teleport"
    setup    = "rm -f AGENTS.md"        # optional, run after checkout
    teardown = "git restore AGENTS.md"  # optional, run before removal

## Files in the worktree

| File                          | Contents                                     |
| ----------------------------- | -------------------------------------------- |
| `PR_INFO.txt`                 | Title, author, URL, branches, labels.        |
| `PR_DESCRIPTION.md`           | The author's PR description.                 |
| `PR_<N>.diff`                 | Full diff.                                   |
| `PR_COMMENTS.json`            | Reviews, inline and issue comments.          |
| `PR_REVIEW.txt`               | Review prompt for the agent.                 |
| `PR_RENDER.py`                | HTML report helpers.                         |
| `.claude/settings.local.json` | Read access to `~/go/pkg/mod`.               |
| `WORKTREE_REMOVE.sh`          | Cleanup; aborts if you changed other files.  |

## The report

`PR_REVIEW_REPORT.<model>.<ts>.html`: self-contained, grouped by severity.
Each finding states its user impact; medium and above also list rated
threat-model assumptions. The filename suffix lets several agents review one
worktree in parallel.
