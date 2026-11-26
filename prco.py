#!/usr/bin/env python3
"""Prepare a local worktree for reviewing a Teleport PR.

Creates inside ~/code/teleport-pr-<N>/ (a detached worktree at the PR head;
--branch checks out a local branch instead, --suffix appends a timestamp to
the directory name, --update refreshes an existing worktree in place):
  PR_INFO.txt          PR title, author, URL, base, head, etc.
  PR_DESCRIPTION.md    PR description (body) as written by the author
  PR_COMMENTS.json     reviews + review comments + issue comments
  PR_<N>.diff          full PR diff (via `gh pr diff`)
  PR_REVIEW.txt        situation briefing and thorough-review request
  PR_RENDER.py         stdlib render helpers used by the review's HTML report
  WORKTREE_REMOVE.sh   safe cleanup: rm those files, then `git worktree remove`
                       (no --force, so it aborts if anything else was changed)

Fork PRs use the upstream repository's refs/pull/<N>/head;
--branch names their local branch pr-<N>.
"""
import argparse
import datetime
import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
import urllib.parse
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"


def repo_slug(url):
    """Derive 'owner/repo' from a full GitHub URL."""
    path = urllib.parse.urlparse(url).path.strip("/")
    if path.endswith(".git"):
        path = path[: -len(".git")]
    parts = path.split("/")
    return "/".join(parts[:2])


def repo_name(url):
    """The repository name (the part after 'owner/')."""
    return repo_slug(url).split("/")[1]


def parse_pr_url(arg):
    """Parse a GitHub PR URL into ('owner/repo', number), or None if not one."""
    parsed = urllib.parse.urlparse(arg)
    if parsed.scheme not in ("http", "https") or parsed.netloc != "github.com":
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) < 4 or parts[2] != "pull" or not parts[3].isdigit():
        return None
    return (f"{parts[0]}/{parts[1]}", int(parts[3]))


@dataclass(frozen=True)
class Repo:
    clone: Path
    url: str
    slug: str
    name: str
    setup: str | None
    teardown: str | None

    @classmethod
    def from_toml(cls, d):
        url = d["url"]
        return cls(
            clone=Path(d["clone"]).expanduser(),
            url=url,
            slug=repo_slug(url),
            name=repo_name(url),
            setup=d.get("setup"),
            teardown=d.get("teardown"),
        )


def config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "prco" / "config.toml"


def load_config(path):
    """Return an ordered list of Repo, or None if the file does not exist."""
    if not path.exists():
        return None
    data = tomllib.loads(path.read_text())
    return [Repo.from_toml(d) for d in data.get("repo", [])]


class ConfigError(Exception):
    """Raised when the config can't satisfy the request; triggers the editor."""


def resolve_target(arg, repos):
    """Return (Repo, pr_number) for the argument, or raise ConfigError."""
    parsed = parse_pr_url(arg)
    if parsed is not None:
        slug, pr = parsed
        for repo in repos:
            if repo.slug.lower() == slug.lower():
                return repo, pr
        raise ConfigError(f"no configured repo matches {slug}")
    if arg.isdigit():
        if not repos:
            raise ConfigError("no repositories configured (need a default)")
        return repos[0], int(arg)
    raise ConfigError(f"not a PR number or GitHub PR URL: {arg!r}")


def worktree_path(repo, pr):
    return repo.clone.parent / f"{repo.name}-pr-{pr}"


def _color(code, stream=sys.stdout):
    use = stream.isatty() and not os.environ.get("NO_COLOR")
    return (lambda s: f"\033[{code}m{s}\033[0m") if use else (lambda s: s)


# Success palette (stdout).
bold, dim, green, yellow, cyan = (
    _color("1"), _color("2"), _color("32"), _color("33"), _color("36")
)

# Error palette (stderr) -- TTY-detected on stderr, so colors survive
# even when stdout is piped/redirected.
e_err = _color("1;31", sys.stderr)
e_hint = _color("1;33", sys.stderr)
e_green = _color("32", sys.stderr)
e_cyan = _color("36", sys.stderr)
e_dim = _color("2", sys.stderr)

PR_FIELDS = (
    "number,title,body,author,url,baseRefName,headRefName,state,"
    "isCrossRepository,labels,createdAt,updatedAt"
)


def run(*args, cwd=None, capture=False):
    return subprocess.run(
        args, cwd=cwd, check=True, text=True,
        stdout=subprocess.PIPE if capture else None,
    )


def prism_running():
    """Whether `prism`'s router daemon is up (`prism status` reports alive)."""
    try:
        result = subprocess.run(
            ["prism", "status"], capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and "alive" in result.stdout


def agent_commands():
    """Agent invocation prefixes to suggest, `claude` first.

    `codex` is added when installed. Each gets a `prism <agent>` variant
    alongside it when prism's router is up, routing the agent's traffic
    through the Teleport cluster.
    """
    prism_up = shutil.which("prism") is not None and prism_running()
    commands = ["claude"]
    if prism_up:
        commands.append("prism claude")
    if shutil.which("codex") is not None:
        commands.append("codex")
        if prism_up:
            commands.append("prism codex")
    return commands


@dataclass(frozen=True)
class Worktree:
    path: Path
    branch: str | None  # None when HEAD is detached


def parse_worktree_list(porcelain):
    """Parse `git worktree list --porcelain` output into Worktree entries."""
    entries = []
    path = None
    branch = None
    for line in porcelain.splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree "):])
            branch = None
        elif line.startswith("branch refs/heads/"):
            branch = line[len("branch refs/heads/"):]
        elif line == "" and path is not None:
            entries.append(Worktree(path, branch))
            path = None
    if path is not None:
        entries.append(Worktree(path, branch))
    return entries


def list_worktrees(clone):
    out = run("git", "worktree", "list", "--porcelain", cwd=clone, capture=True).stdout
    return parse_worktree_list(out)


def worktree_holding(entries, branch):
    """Path of the worktree that has `branch` checked out, or None."""
    for wt in entries:
        if wt.branch == branch:
            return wt.path
    return None


def worktree_at(entries, path):
    for wt in entries:
        if wt.path == path:
            return wt
    return None


def suffixed_worktree_path(repo, pr, now):
    return repo.clone.parent / f"{repo.name}-pr-{pr}-{now:%Y%m%d-%H%M%S}"


def update_problem(entries, worktree, branch):
    """Why `worktree` can't be updated for the PR on `branch`, or None if it can.

    Updating is safe when the directory is one of the clone's worktrees and
    is either detached (the default layout) or on the PR branch itself.
    """
    wt = worktree_at(entries, worktree)
    if wt is None:
        return f"{e_cyan(str(worktree))} is not a worktree of the clone"
    if wt.branch is not None and wt.branch != branch:
        return (f"{e_cyan(str(worktree))} is on branch '{e_green(wt.branch)}', "
                f"not '{e_green(branch)}'")
    return None


def conflict_message(worktree, pr_arg):
    q = shlex.quote(pr_arg)
    return "\n".join([
        f"{e_err('error:')} {e_cyan(str(worktree))} already exists",
        "",
        f"{e_hint('To refresh that checkout in place')} "
        f"{e_dim('(fetch, reset --keep, regenerate PR_* files)')}:",
        f"    {e_cyan(f'prco --update {q}')}",
        "",
        f"{e_hint('To leave it alone and create a second, timestamp-suffixed worktree')}:",
        f"    {e_cyan(f'prco --suffix {q}')}",
        "",
    ])


def fetch_comments(slug, pr):
    def api(path):
        return json.loads(run("gh", "api", "--paginate", path, capture=True).stdout)
    return {
        "reviews":         api(f"repos/{slug}/pulls/{pr}/reviews"),
        "review_comments": api(f"repos/{slug}/pulls/{pr}/comments"),
        "issue_comments":  api(f"repos/{slug}/issues/{pr}/comments"),
    }


def make_remove_script(clone, worktree, files, teardown=None):
    rm_lines = "\n".join(f"rm -- {shlex.quote(str(f))}" for f in files)
    teardown_line = (
        f"\n( cd {shlex.quote(str(worktree))} && {teardown} )\n" if teardown else ""
    )
    return (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "\n"
        "# Generated by prco. Removes only what that tool created here,\n"
        "# runs the repo's teardown, then `git worktree remove` (no --force, so\n"
        "# it aborts on other changes).\n"
        "\n"
        f"cd {shlex.quote(str(clone))}\n"
        "\n"
        f"{rm_lines}\n"
        f"{teardown_line}"
        "\n"
        f"git worktree remove {shlex.quote(str(worktree))}\n"
    )


CONFIG_TEMPLATE = """\
# prco configuration.
# The first repository is the default: a bare PR number resolves against it.
# To review a PR in another repo, pass its full GitHub PR URL.

[[repo]]
clone    = "~/code/teleport"                           # local clone (worktrees created beside it)
url      = "https://github.com/gravitational/teleport" # full GitHub URL; owner/repo derived from it
setup    = "rm -f AGENTS.md"                            # optional: shell command run in the worktree after creation
teardown = "git restore AGENTS.md"                      # optional: shell command run in cleanup before worktree remove

# [[repo]]
# clone = "~/code/rfd"
# url   = "https://github.com/gravitational/rfd"
"""


# Claude Code settings for agents launched in the worktree: read access to the
# Go module cache, so dependency sources can be inspected without prompts.
AGENT_SETTINGS = {
    "permissions": {
        "additionalDirectories": ["~/go/pkg/mod"],
        "allow": ["Read(~/go/pkg/mod/**)"],
    },
}


def config_template():
    return CONFIG_TEMPLATE


def open_editor(path):
    # VISUAL/EDITOR may carry flags (e.g. "code --wait"), so tokenize the
    # command rather than treating the whole string as one executable name.
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    subprocess.run([*shlex.split(editor), str(path)], check=False)


def edit_config(path, exit_code):
    """Ensure config exists (write template if not), open it, and exit."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(config_template())
    open_editor(path)
    sys.exit(exit_code)


def format_review(meta, pr, slug):
    template = (PROMPTS_DIR / "pr_review_template.md").read_text()
    return template.format(
        pr=pr,
        remote_repo=slug,
        title=meta["title"],
        author=meta["author"]["login"],
        url=meta["url"],
        head_branch=meta["headRefName"],
        base_branch=meta["baseRefName"],
    )


def format_info(meta):
    labels = ", ".join(l["name"] for l in meta["labels"]) or "(none)"
    return (
        f"PR #{meta['number']}: {meta['title']}\n"
        f"State:   {meta['state']}\n"
        f"Author:  {meta['author']['login']}\n"
        f"URL:     {meta['url']}\n"
        f"Base:    {meta['baseRefName']}\n"
        f"Head:    {meta['headRefName']}\n"
        f"Labels:  {labels}\n"
        f"Created: {meta['createdAt']}\n"
        f"Updated: {meta['updatedAt']}\n"
    )


def format_description(meta):
    body = meta["body"].strip() or "(no description)"
    return f"# PR #{meta['number']}: {meta['title']}\n\n{body}\n"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("pr", nargs="?", help="PR number (default repo) or GitHub PR URL")
    ap.add_argument("-e", "--edit-config", action="store_true",
                    help="open the config file in $VISUAL/$EDITOR and exit")
    ap.add_argument("-b", "--branch", action="store_true",
                    help="check out a local branch named after the PR head instead "
                         "of a detached HEAD (pr-<N> for forks; only one worktree "
                         "can hold a branch)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("-u", "--update", action="store_true",
                      help="refresh an existing <repo>-pr-<N> worktree in place: fetch, "
                           "`git reset --keep`, regenerate the PR_* files")
    mode.add_argument("-s", "--suffix", action="store_true",
                      help="create <repo>-pr-<N>-<YYYYmmdd-HHMMSS> instead of "
                           "<repo>-pr-<N>, so an existing checkout is left alone")
    args = ap.parse_args()

    cfg = config_path()

    if args.edit_config:
        edit_config(cfg, exit_code=0)

    if args.pr is None:
        ap.error("a PR number or URL is required (or use --edit-config)")

    repos = load_config(cfg)
    if repos is None:
        print(f"{e_err('error:')} no config at {e_cyan(str(cfg))}; opening editor",
              file=sys.stderr)
        edit_config(cfg, exit_code=1)

    try:
        repo, pr = resolve_target(args.pr, repos)
    except ConfigError as exc:
        print(f"{e_err('error:')} {exc}; opening config", file=sys.stderr)
        edit_config(cfg, exit_code=1)

    clone = repo.clone
    slug = repo.slug

    meta = json.loads(run(
        "gh", "pr", "view", str(pr), "-R", slug, "--json", PR_FIELDS, capture=True,
    ).stdout)

    branch = f"pr-{pr}" if meta["isCrossRepository"] else meta["headRefName"]
    if args.suffix:
        worktree = suffixed_worktree_path(repo, pr, datetime.datetime.now())
    else:
        worktree = worktree_path(repo, pr)
    info_file = worktree / "PR_INFO.txt"
    description_file = worktree / "PR_DESCRIPTION.md"
    diff_file = worktree / f"PR_{pr}.diff"
    comments_file = worktree / "PR_COMMENTS.json"
    review_file = worktree / "PR_REVIEW.txt"
    render_file = worktree / "PR_RENDER.py"
    settings_file = worktree / ".claude" / "settings.local.json"
    remove_script = worktree / "WORKTREE_REMOVE.sh"

    worktrees = list_worktrees(clone)

    if args.update:
        if not worktree.exists():
            sys.exit(f"{e_err('error:')} --update: {e_cyan(str(worktree))} does not exist")
        problem = update_problem(worktrees, worktree, branch)
        if problem:
            sys.exit(f"{e_err('error:')} --update: {problem}")
    elif worktree.exists():
        sys.exit(conflict_message(worktree, args.pr))

    if args.branch and not args.update:
        holder = worktree_holding(worktrees, branch)
        if holder:
            sys.exit("\n".join([
                f"{e_err('error:')} branch '{e_green(branch)}' is already checked out at",
                f"       {e_cyan(str(holder))}",
                f"{e_hint('hint: ')} drop --branch for a detached worktree, or free it with:",
                f"       git -C {e_cyan(shlex.quote(str(holder)))} checkout --detach",
            ]))

    if meta["state"] == "OPEN" and not meta["isCrossRepository"]:
        run("git", "fetch", "origin", branch, cwd=clone)
        start_point = f"origin/{branch}"
    else:
        # Fork branches aren't on origin, and source branches are typically
        # deleted after merge/close. GitHub keeps the pre-merge head commit
        # reachable via refs/pull/<N>/head -- that's what we
        # want to review (and, for squash merges, it's the only place the
        # individual commits still exist).
        run("git", "fetch", "origin", f"refs/pull/{pr}/head", cwd=clone)
        start_point = run("git", "rev-parse", "FETCH_HEAD", cwd=clone, capture=True).stdout.strip()

    if args.update:
        # Undo the setup hook first (e.g. restore AGENTS.md) so its uncommitted
        # edits can't collide with upstream changes during the reset. The hook
        # is re-applied below. `reset --keep` moves HEAD (and the branch, if
        # any) while preserving local edits and untracked files such as review
        # reports; it aborts instead of clobbering a conflicting local change.
        if repo.teardown:
            run("bash", "-c", repo.teardown, cwd=worktree)
        try:
            run("git", "reset", "--keep", start_point, cwd=worktree)
        except subprocess.CalledProcessError:
            sys.exit("\n".join([
                f"{e_err('error:')} could not move {e_cyan(str(worktree))} to the new PR head",
                f"{e_hint('hint: ')} commit or stash the conflicting local changes, "
                f"or use {e_cyan('--suffix')}",
            ]))
    elif args.branch:
        # -B resets the local branch so a stale local copy (e.g. after a PR
        # force-push, or a leftover branch from a now-merged PR) doesn't put
        # the worktree on old commits.
        run("git", "worktree", "add", "-B", branch, str(worktree), start_point, cwd=clone)
    else:
        # Detached by default: no local branch means any number of worktrees
        # can check out the same PR without fighting over who holds it.
        run("git", "worktree", "add", "--detach", str(worktree), start_point, cwd=clone)

    created = []

    def emit(path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        created.append(path)

    emit(info_file, format_info(meta))
    emit(description_file, format_description(meta))
    emit(diff_file, run("gh", "pr", "diff", str(pr), "-R", slug, capture=True).stdout)
    emit(comments_file, json.dumps(fetch_comments(slug, pr), indent=2))
    emit(review_file, format_review(meta, pr, slug))
    emit(render_file, (PROMPTS_DIR / "PR_RENDER.py").read_text())
    emit(settings_file, json.dumps(AGENT_SETTINGS, indent=2) + "\n")

    # Per-repo setup hook (e.g. teleport deletes AGENTS.md, whose instructions
    # conflict with the review prompt). The teardown in WORKTREE_REMOVE.sh
    # undoes it before `git worktree remove`.
    if repo.setup:
        run("bash", "-c", repo.setup, cwd=worktree)

    # WORKTREE_REMOVE.sh is in its own cleanup list — append before generating.
    created.append(remove_script)
    remove_script.write_text(make_remove_script(clone, worktree, created, repo.teardown))
    remove_script.chmod(0o755)

    print()
    print(f"{bold(f'PR #{pr}')}: {bold(meta['title'])}")
    print(f"  {dim('worktree:')} {cyan(str(worktree))}")
    on_branch = worktree_at(list_worktrees(clone), worktree).branch is not None
    head_note = "" if on_branch else f"  {dim('(detached)')}"
    if on_branch and meta["isCrossRepository"]:
        head_note = f"  {dim(f'(branch: {branch})')}"
    print(f"  {dim('head:    ')} {green(meta['headRefName'])}{head_note}  ({dim('base:')} {yellow(meta['baseRefName'])})")
    for label, path in [("info", info_file), ("desc", description_file),
                        ("diff", diff_file),
                        ("comments", comments_file), ("review", review_file),
                        ("render", render_file), ("settings", settings_file),
                        ("cleanup", remove_script)]:
        print(f"  {dim(f'{label:9s}')} {cyan(str(path))}")
    print()
    print(dim("To start the review:"))
    print()
    for agent in agent_commands():
        print(f"cd {cyan(str(worktree))} && {agent} \"@PR_REVIEW.txt\"")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        # The command has already reported its own error on stderr.
        sys.exit(f"{e_err('error:')} {e_cyan(shlex.join(exc.cmd))} "
                 f"failed (exit {exc.returncode})")
