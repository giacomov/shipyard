#!/usr/bin/env python3
"""Shared git subprocess wrappers used across command modules."""

import subprocess

import click

from shipyard.sim import is_sim_mode

_MUTATING_GIT_SUBCOMMANDS = {"push", "commit", "checkout", "reset", "add", "merge"}


def git(args: list[str]) -> str:
    """Run a git command and return trimmed stdout.

    Raises RuntimeError on non-zero exit. In sim mode, mutating subcommands
    (push, commit, checkout, reset, add, merge) print [sim] lines and no-op.
    """
    if is_sim_mode() and args and args[0] in _MUTATING_GIT_SUBCOMMANDS:
        click.echo(f"[sim] git {' '.join(args)}")
        return ""
    result = subprocess.run(["git"] + args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"git command failed (exit {result.returncode}): git {' '.join(args)}\n{result.stderr}"
        )
    return result.stdout.strip()


def checkout_new_branch(branch: str) -> None:
    """Create and check out a new branch."""
    git(["checkout", "-b", branch])


def push(branch: str, remote: str = "origin", set_upstream: bool = False) -> None:
    """Push a branch to a remote."""
    args = ["push"]
    if set_upstream:
        args.append("-u")
    args += [remote, branch]
    git(args)


def reset_hard(ref: str) -> None:
    """Reset HEAD to ref, discarding all changes."""
    git(["reset", "--hard", ref])


def get_head_sha() -> str:
    """Return the current HEAD commit SHA."""
    return git(["rev-parse", "HEAD"])
