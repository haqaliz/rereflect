#!/usr/bin/env python3
"""
Sync git commits to changelog_entries table.

Parses conventional commit messages and creates changelog entries.
Skips commits that already exist (by commit_hash).

Usage:
    python scripts/sync_changelog.py              # Last 20 commits
    python scripts/sync_changelog.py --limit 50   # Last 50 commits
    python scripts/sync_changelog.py --all         # All commits
"""

import argparse
import subprocess
import sys
import os
import re
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.session import SessionLocal
from src.models.changelog_entry import ChangelogEntry

# Conventional commit type mapping
TYPE_MAP = {
    "feat": "feature",
    "fix": "fix",
    "chore": "chore",
    "refactor": "improvement",
    "perf": "improvement",
    "style": "chore",
    "build": "chore",
    "ci": "chore",
}

# Types to skip
SKIP_TYPES = {"docs", "test", "tests"}

# Pattern: optional scope, optional ! for breaking
CONVENTIONAL_RE = re.compile(
    r"^(?P<type>\w+)(?:\((?P<scope>[^)]*)\))?(?P<breaking>!)?\s*:\s*(?P<title>.+)$"
)


def parse_git_log(limit=None):
    """Parse git log and return list of commit dicts."""
    # Format: hash<SEP>date<SEP>subject<SEP>body
    sep = "<CHANGELOG_SEP>"
    fmt = f"%H{sep}%aI{sep}%s{sep}%b"

    cmd = ["git", "log", f"--format={fmt}", "--no-merges"]
    if limit:
        cmd.append(f"-{limit}")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if result.returncode != 0:
        print(f"Error running git log: {result.stderr}")
        sys.exit(1)

    commits = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split(sep, 3)
        if len(parts) < 3:
            continue
        commits.append({
            "hash": parts[0],
            "date": parts[1],
            "subject": parts[2],
            "body": parts[3].strip() if len(parts) > 3 else "",
        })

    return commits


def parse_commit(commit):
    """Parse a conventional commit into a changelog entry dict, or None to skip."""
    subject = commit["subject"]
    match = CONVENTIONAL_RE.match(subject)

    if not match:
        return None

    commit_type = match.group("type").lower()
    breaking_marker = match.group("breaking")
    title = match.group("title").strip()

    if commit_type in SKIP_TYPES:
        return None

    entry_type = TYPE_MAP.get(commit_type)
    if not entry_type:
        return None

    is_breaking = bool(breaking_marker) or "BREAKING CHANGE" in commit.get("body", "")
    if is_breaking:
        entry_type = "breaking_change"

    # Parse ISO date
    date_str = commit["date"]
    try:
        committed_at = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        committed_at = datetime.utcnow()

    description = commit.get("body") or None
    if description:
        # Truncate overly long descriptions
        description = description[:2000]

    return {
        "commit_hash": commit["hash"],
        "title": title,
        "description": description,
        "entry_type": entry_type,
        "is_breaking": is_breaking,
        "committed_at": committed_at,
    }


def sync(limit=None):
    """Sync git commits to database."""
    commits = parse_git_log(limit)
    print(f"Found {len(commits)} commits to process")

    db = SessionLocal()
    created = 0
    skipped = 0

    try:
        for commit in commits:
            entry_data = parse_commit(commit)
            if entry_data is None:
                skipped += 1
                continue

            # Check if already exists
            existing = db.query(ChangelogEntry).filter(
                ChangelogEntry.commit_hash == entry_data["commit_hash"]
            ).first()

            if existing:
                skipped += 1
                continue

            entry = ChangelogEntry(**entry_data)
            db.add(entry)
            created += 1

        db.commit()
        print(f"Created {created} entries, skipped {skipped}")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Sync git commits to changelog")
    parser.add_argument("--limit", type=int, default=20, help="Number of commits to process (default: 20)")
    parser.add_argument("--all", action="store_true", help="Process all commits")
    args = parser.parse_args()

    limit = None if args.all else args.limit
    sync(limit)


if __name__ == "__main__":
    main()
