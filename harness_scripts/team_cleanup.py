#!/usr/bin/env python3
"""Team cleanup — kill leftover sub-agent processes and remove team config.

Usage: team_cleanup.py <team-name> [--dry-run]

Why this exists:
  Claude Code's TeamDelete only removes the team config directory + worktree.
  The actual sub-agent Claude processes survive and accumulate. This script
  finds them by matching team-name in their command line, sends SIGTERM, then
  SIGKILL after a short grace, and removes the team config dir.

Safety:
  - --dry-run lists targets without killing.
  - Searches for `<team-name>` in process command lines, which should be specific
    enough to avoid collateral damage. Use a unique team name in production.
  - Reports survivors after kill attempt; exits 2 if any remain.
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path


def find_team_config(team_name: str) -> Path | None:
    """Locate the team config directory under HOME/.claude/teams/."""
    candidates = [
        Path.home() / ".claude" / "teams" / team_name,
    ]
    for path in candidates:
        if path.is_dir():
            return path
    return None


def find_team_processes(team_name: str) -> list[int]:
    """Use pgrep -fl to find PIDs whose command line contains team_name.

    Returns sorted list of PIDs. Excludes the current process.
    """
    try:
        result = subprocess.run(
            ["pgrep", "-fl", team_name],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []

    pids: list[int] = []
    self_pid = os.getpid()
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        try:
            pid_str = line.split(maxsplit=1)[0]
            pid = int(pid_str)
        except ValueError:
            continue
        if pid == self_pid:
            continue
        pids.append(pid)
    return sorted(pids)


def kill_processes(pids: list[int], dry_run: bool) -> None:
    """SIGTERM, wait, SIGKILL survivors."""
    if dry_run:
        for pid in pids:
            print(f"  [dry-run] would SIGTERM {pid}")
        return

    sigterm_sent: list[int] = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            sigterm_sent.append(pid)
        except ProcessLookupError:
            pass
        except PermissionError:
            print(f"  ⚠ permission denied for PID {pid}", file=sys.stderr)

    if not sigterm_sent:
        return

    time.sleep(2)

    for pid in sigterm_sent:
        try:
            os.kill(pid, 0)  # check if alive
            os.kill(pid, signal.SIGKILL)
            print(f"  SIGKILL {pid} (survived SIGTERM)")
        except ProcessLookupError:
            pass


def remove_config(config_dir: Path | None, dry_run: bool) -> None:
    if config_dir is None:
        return
    if dry_run:
        print(f"  [dry-run] would rm -rf {config_dir}")
        return
    shutil.rmtree(config_dir, ignore_errors=True)
    if not config_dir.exists():
        print(f"  ✓ removed {config_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Cleanup leftover team processes + config")
    parser.add_argument("team_name", help="Team name (matches in process cmdline + config path)")
    parser.add_argument("--dry-run", action="store_true", help="List targets without killing")
    args = parser.parse_args()

    team_name = args.team_name
    print(f"Cleaning team: {team_name}{' (dry-run)' if args.dry_run else ''}")

    config = find_team_config(team_name)
    if config:
        print(f"  config: {config}")
    else:
        print("  config: not found (already removed?)")

    pids = find_team_processes(team_name)
    if pids:
        print(f"  processes: {len(pids)} found — {pids}")
    else:
        print("  processes: none found")

    kill_processes(pids, dry_run=args.dry_run)
    remove_config(config, dry_run=args.dry_run)

    if args.dry_run:
        return 0

    survivors = find_team_processes(team_name)
    if survivors:
        print(f"  ⚠ survivors after kill: {survivors}", file=sys.stderr)
        return 2

    print("  ✓ all clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
