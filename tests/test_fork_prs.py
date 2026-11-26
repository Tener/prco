import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import prco


@pytest.fixture
def checkout(monkeypatch, tmp_path):
    remote = tmp_path / "upstream"
    remote.mkdir()

    def git(cwd, *args):
        return subprocess.run(
            ["git", *args], cwd=cwd, check=True, text=True, capture_output=True,
        ).stdout.strip()

    git(remote, "init", "-b", "master")
    git(remote, "config", "user.name", "Test")
    git(remote, "config", "user.email", "test@example.com")
    git(remote, "config", "commit.gpgsign", "false")
    git(remote, "config", "core.hooksPath", "/dev/null")
    (remote / "base.txt").write_text("base\n")
    git(remote, "add", "base.txt")
    git(remote, "commit", "-m", "Base")
    base = git(remote, "rev-parse", "HEAD")
    git(remote, "checkout", "-b", "feature")
    (remote / "feature.txt").write_text("PR head\n")
    git(remote, "add", "feature.txt")
    git(remote, "commit", "-m", "PR head")
    head = git(remote, "rev-parse", "HEAD")
    git(remote, "update-ref", "refs/pull/7/head", head)
    git(remote, "checkout", "master")

    clone = tmp_path / "clone"
    git(tmp_path, "clone", str(remote), str(clone))
    repo = prco.Repo.from_toml({
        "clone": str(clone), "url": "https://github.com/upstream/project",
    })
    worktree = prco.worktree_path(repo, 7)
    meta = {
        "number": 7, "title": "Fork PR", "body": "Description",
        "author": {"login": "contributor"},
        "url": "https://github.com/upstream/project/pull/7",
        "baseRefName": "master", "headRefName": "master",
        "state": "OPEN", "isCrossRepository": True, "labels": [],
        "createdAt": "2026-01-01T00:00:00Z", "updatedAt": "2026-01-01T00:00:00Z",
    }
    real_run = prco.run

    def run(*args, **kwargs):
        if args[:3] == ("gh", "pr", "view"):
            return SimpleNamespace(stdout=json.dumps(meta))
        if args[:3] == ("gh", "pr", "diff"):
            return SimpleNamespace(stdout="PR diff\n")
        if args[:2] == ("gh", "api"):
            return SimpleNamespace(stdout="[]")
        return real_run(*args, **kwargs)

    def invoke(*flags):
        monkeypatch.setattr(sys, "argv", [prco.__file__, *flags, "7"])
        prco.main()

    def advance():
        git(remote, "checkout", "feature")
        (remote / "feature.txt").write_text("Updated PR head\n")
        git(remote, "add", "feature.txt")
        git(remote, "commit", "-m", "Update PR")
        new_head = git(remote, "rev-parse", "HEAD")
        git(remote, "update-ref", "refs/pull/7/head", new_head)
        git(remote, "checkout", "master")
        return new_head

    monkeypatch.setattr(prco, "load_config", lambda path: [repo])
    monkeypatch.setattr(prco, "run", run)
    monkeypatch.setattr(prco, "agent_commands", lambda: [])
    return SimpleNamespace(
        git=git, invoke=invoke, advance=advance, clone=clone, worktree=worktree,
        meta=meta, head=head, base=base,
    )


@pytest.mark.parametrize("state", ["OPEN", "CLOSED", "MERGED"])
@pytest.mark.parametrize("branch", [False, True])
def test_fork_checkout(checkout, state, branch):
    c = checkout
    c.meta["state"] = state
    c.invoke(*(["--branch"] if branch else []))
    assert c.git(c.worktree, "rev-parse", "HEAD") == c.head
    assert c.git(c.worktree, "rev-parse", "--abbrev-ref", "HEAD") == (
        "pr-7" if branch else "HEAD"
    )
    assert c.git(c.clone, "rev-parse", "master") == c.base
    assert "Head:    master\n" in (c.worktree / "PR_INFO.txt").read_text()
    assert (c.worktree / "PR_7.diff").read_text() == "PR diff\n"
    assert (c.worktree / "PR_REVIEW.txt").is_file()


@pytest.mark.parametrize("branch", [False, True])
def test_fork_update_preserves_local_edits(checkout, branch):
    c = checkout
    c.invoke(*(["--branch"] if branch else []))
    (c.worktree / "base.txt").write_text("local edit\n")
    (c.worktree / "review.txt").write_text("local report\n")
    new_head = c.advance()
    c.invoke("--update")
    assert c.git(c.worktree, "rev-parse", "HEAD") == new_head
    assert (c.worktree / "base.txt").read_text() == "local edit\n"
    assert (c.worktree / "review.txt").read_text() == "local report\n"
    assert c.git(c.clone, "rev-parse", "master") == c.base


def test_fork_update_aborts_on_conflicting_edit(checkout):
    c = checkout
    c.invoke()
    (c.worktree / "feature.txt").write_text("local edit\n")
    c.advance()
    with pytest.raises(SystemExit, match="could not move"):
        c.invoke("--update")
    assert c.git(c.worktree, "rev-parse", "HEAD") == c.head
    assert (c.worktree / "feature.txt").read_text() == "local edit\n"


def test_fork_branch_already_checked_out(checkout):
    c = checkout
    c.invoke("--branch", "--suffix")
    with pytest.raises(SystemExit, match="branch 'pr-7' is already checked out"):
        c.invoke("--branch")
    assert not c.worktree.exists()
    assert c.git(c.clone, "rev-parse", "master") == c.base


@pytest.mark.parametrize("state", ["OPEN", "MERGED"])
def test_same_repository_checkout(checkout, state):
    c = checkout
    c.meta.update(isCrossRepository=False, headRefName="feature", state=state)
    c.invoke("--branch")
    assert c.git(c.worktree, "rev-parse", "HEAD") == c.head
    assert c.git(c.worktree, "rev-parse", "--abbrev-ref", "HEAD") == "feature"
    new_head = c.advance()
    c.invoke("--update")
    assert c.git(c.worktree, "rev-parse", "HEAD") == new_head
