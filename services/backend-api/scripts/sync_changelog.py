#!/usr/bin/env python3
"""
Sync git commits to changelog_entries table.

Parses conventional commit messages and creates changelog entries.
Skips commits that already exist (by commit_hash).

Modes:
    --github          Fetch from GitHub API and insert into DB (production startup)
    --export <file>   Parse git log and save to JSON (run during Docker build)
    --import <file>   Read JSON and insert into DB (run on startup)
    (default)         Git log -> DB directly (for local development)

Usage:
    python scripts/sync_changelog.py              # Local: git -> DB (last 20)
    python scripts/sync_changelog.py --all        # Local: git -> DB (all)
    python scripts/sync_changelog.py --github     # Production: GitHub API -> DB
    python scripts/sync_changelog.py --export changelog_commits.json  # Build: git -> JSON
    python scripts/sync_changelog.py --import changelog_commits.json  # Startup: JSON -> DB
"""

import argparse
import json
import logging
import subprocess
import sys
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    sep = "<CHANGELOG_SEP>"
    fmt = f"%H{sep}%aI{sep}%s{sep}%b"

    cmd = ["git", "log", f"--format={fmt}", "--no-merges"]
    if limit:
        cmd.append(f"-{limit}")

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if result.returncode != 0:
        print(f"Error running git log: {result.stderr}")
        return []

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
        description = description[:2000]

    return {
        "commit_hash": commit["hash"],
        "title": title,
        "description": description,
        "entry_type": entry_type,
        "is_breaking": is_breaking,
        "committed_at": committed_at.isoformat(),
    }


def export_to_json(output_path, limit=None):
    """Parse git log and save parsed entries to JSON file."""
    commits = parse_git_log(limit)
    print(f"Found {len(commits)} commits to process")

    entries = []
    for commit in commits:
        entry = parse_commit(commit)
        if entry:
            entries.append(entry)

    with open(output_path, "w") as f:
        json.dump(entries, f, indent=2)

    print(f"Exported {len(entries)} changelog entries to {output_path}")


def import_from_json(input_path):
    """Read JSON file and insert entries into database."""
    from src.database.session import SessionLocal
    from src.models.changelog_entry import ChangelogEntry

    if not os.path.exists(input_path):
        print(f"No changelog file found at {input_path}, skipping import")
        return

    with open(input_path, "r") as f:
        entries_data = json.load(f)

    print(f"Importing {len(entries_data)} changelog entries...")

    db = SessionLocal()
    created = 0
    skipped = 0

    try:
        for entry_data in entries_data:
            existing = db.query(ChangelogEntry).filter(
                ChangelogEntry.commit_hash == entry_data["commit_hash"]
            ).first()

            if existing:
                skipped += 1
                continue

            entry = ChangelogEntry(
                commit_hash=entry_data["commit_hash"],
                title=entry_data["title"],
                description=entry_data.get("description"),
                entry_type=entry_data["entry_type"],
                is_breaking=entry_data["is_breaking"],
                committed_at=datetime.fromisoformat(entry_data["committed_at"]),
            )
            db.add(entry)
            created += 1

        db.commit()
        print(f"Changelog sync: created {created}, skipped {skipped}")

    except Exception as e:
        db.rollback()
        print(f"Changelog import error: {e}")
    finally:
        db.close()


def sync_direct(limit=None):
    """Sync git commits directly to database (for local development)."""
    from src.database.session import SessionLocal
    from src.models.changelog_entry import ChangelogEntry

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

            existing = db.query(ChangelogEntry).filter(
                ChangelogEntry.commit_hash == entry_data["commit_hash"]
            ).first()

            if existing:
                skipped += 1
                continue

            entry = ChangelogEntry(
                commit_hash=entry_data["commit_hash"],
                title=entry_data["title"],
                description=entry_data.get("description"),
                entry_type=entry_data["entry_type"],
                is_breaking=entry_data["is_breaking"],
                committed_at=datetime.fromisoformat(entry_data["committed_at"]),
            )
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


def fetch_github_commits(repo, token, limit=100):
    """Fetch commits from GitHub API. Returns list of commit dicts."""
    import httpx

    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"Bearer {token}",
    }

    commits = []
    page = 1
    per_page = min(limit, 100)
    remaining = limit

    while remaining > 0:
        params = {"per_page": min(per_page, remaining), "page": page}
        resp = httpx.get(
            f"https://api.github.com/repos/{repo}/commits",
            headers=headers,
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            logger.error(f"GitHub API error {resp.status_code}: {resp.text[:200]}")
            break

        data = resp.json()
        if not data:
            break

        for item in data:
            message = item["commit"]["message"]
            lines = message.split("\n", 1)
            commits.append({
                "hash": item["sha"],
                "date": item["commit"]["author"]["date"],
                "subject": lines[0],
                "body": lines[1].strip() if len(lines) > 1 else "",
            })

        remaining -= len(data)
        if len(data) < per_page:
            break
        page += 1

    return commits


def sync_from_github(repo, token, limit=100):
    """Fetch commits from GitHub API and sync to database."""
    from src.database.session import SessionLocal
    from src.models.changelog_entry import ChangelogEntry

    commits = fetch_github_commits(repo, token, limit)
    logger.info(f"Fetched {len(commits)} commits from GitHub API")

    db = SessionLocal()
    created = 0
    skipped = 0

    try:
        for commit in commits:
            entry_data = parse_commit(commit)
            if entry_data is None:
                skipped += 1
                continue

            existing = db.query(ChangelogEntry).filter(
                ChangelogEntry.commit_hash == entry_data["commit_hash"]
            ).first()

            if existing:
                skipped += 1
                continue

            entry = ChangelogEntry(
                commit_hash=entry_data["commit_hash"],
                title=entry_data["title"],
                description=entry_data.get("description"),
                entry_type=entry_data["entry_type"],
                is_breaking=entry_data["is_breaking"],
                committed_at=datetime.fromisoformat(entry_data["committed_at"]),
            )
            db.add(entry)
            created += 1

        db.commit()
        logger.info(f"Changelog sync: created {created}, skipped {skipped}")

    except Exception as e:
        db.rollback()
        logger.error(f"Changelog GitHub sync error: {e}")
    finally:
        db.close()


def run_changelog_sync():
    """Auto-sync changelog on startup. Called from main.py lifespan.

    Priority order:
    1. GitHub API if GITHUB_TOKEN and GITHUB_REPO are set (production)
    2. Import from JSON file if present (fallback)
    3. Local git log (local development)
    """
    # Try GitHub API (production)
    github_token = os.getenv("GITHUB_TOKEN", "").strip('"\'')
    github_repo = os.getenv("GITHUB_REPO", "").strip('"\'')

    if github_token and github_repo:
        logger.info(f"Syncing changelog from GitHub API ({github_repo})...")
        sync_from_github(github_repo, github_token, limit=100)
        return

    # Try JSON import (fallback)
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "changelog_commits.json")
    if os.path.exists(json_path):
        logger.info(f"Importing changelog from {json_path}...")
        import_from_json(json_path)
        return

    # Local dev fallback: try git log directly
    try:
        sync_direct(limit=50)
    except Exception as e:
        logger.warning(f"Changelog sync skipped (no git or GitHub config): {e}")


def main():
    parser = argparse.ArgumentParser(description="Sync git commits to changelog")
    parser.add_argument("--limit", type=int, default=20, help="Number of commits (default: 20)")
    parser.add_argument("--all", action="store_true", help="Process all commits")
    parser.add_argument("--github", action="store_true", help="Sync from GitHub API (uses GITHUB_TOKEN and GITHUB_REPO env vars)")
    parser.add_argument("--export", metavar="FILE", help="Export parsed commits to JSON file")
    parser.add_argument("--import", metavar="FILE", dest="import_file", help="Import commits from JSON file into DB")
    args = parser.parse_args()

    if args.github:
        token = os.getenv("GITHUB_TOKEN")
        repo = os.getenv("GITHUB_REPO")
        if not token or not repo:
            print("Error: GITHUB_TOKEN and GITHUB_REPO environment variables required")
            sys.exit(1)
        limit = None if args.all else args.limit
        sync_from_github(repo, token, limit or 100)
    elif args.export:
        limit = None if args.all else args.limit
        export_to_json(args.export, limit)
    elif args.import_file:
        import_from_json(args.import_file)
    else:
        limit = None if args.all else args.limit
        sync_direct(limit)


if __name__ == "__main__":
    main()
