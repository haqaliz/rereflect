#!/usr/bin/env python3
"""
Prospect research helper for Rereflect outreach.

Usage:
  python3 scripts/prospect.py add       # Add a new prospect interactively
  python3 scripts/prospect.py dm        # Generate personalized DMs for prospects without one
  python3 scripts/prospect.py list      # Show all prospects and their status
  python3 scripts/prospect.py stats     # Show outreach metrics
  python3 scripts/prospect.py export    # Export prospect list as markdown table
"""

import json
import os
import sys
from datetime import datetime, date
from pathlib import Path

PROSPECTS_FILE = Path(__file__).parent.parent / "prospects.json"

DM_TEMPLATES = {
    "product_hunt": """Hey {name}! Just came across {company} on Product Hunt — {personal_note}.

Quick question: how are you currently handling customer feedback as you scale?

I built Rereflect (rereflect.ca) — it uses AI to auto-categorize feedback into pain points, feature requests, and churn risk alerts.

Happy to give you 3 months of Pro free if you'd try it and share honest feedback. No strings attached.""",

    "indie_hackers": """Hey {name}, saw {company} on Indie Hackers — {personal_note}!

Now that users are rolling in, are you finding it hard to keep track of all the feedback?

I'm working on Rereflect — it auto-analyzes customer feedback (pain points, feature requests, churn signals). Takes 30 seconds to upload a CSV and see results.

Offering 3 months free Pro to early adopters who share feedback. Want to give it a spin?""",

    "twitter": """Hey {name}! Been following your #buildinpublic journey with {company} — {personal_note}.

Quick question: how are you organizing the customer feedback that's coming in?

I built Rereflect — AI-powered feedback analysis (sentiment, pain points, feature requests, churn risk). 30 seconds to see results from a CSV upload.

Happy to give you 3 months Pro free for honest feedback: app.rereflect.ca/signup?promo=EARLYPRO3""",

    "linkedin": """Hey {name}! Just came across {company} — {personal_note}.

Quick question: how are you currently handling customer feedback as you scale?

I built Rereflect (rereflect.ca) — it uses AI to auto-categorize feedback into pain points, feature requests, and churn risk alerts.

Happy to give you 3 months of Pro free if you'd try it and share honest feedback. No strings attached.""",

    "followup": """Hey {name}, just bumping this in case it got buried. No pressure at all!

If feedback management isn't a pain point right now, totally get it. But the offer for 3 months free Pro stands if you ever want to try it: app.rereflect.ca/signup?promo=EARLYPRO3""",
}

VALID_STATUSES = [
    "researched", "dm_sent", "followed_up", "replied",
    "interested", "signed_up", "activated", "no_reply", "not_interested"
]

VALID_SOURCES = ["product_hunt", "indie_hackers", "twitter", "linkedin", "reddit", "other"]


def load_prospects() -> list[dict]:
    if PROSPECTS_FILE.exists():
        return json.loads(PROSPECTS_FILE.read_text())
    return []


def save_prospects(prospects: list[dict]):
    PROSPECTS_FILE.write_text(json.dumps(prospects, indent=2, default=str))


def add_prospect():
    """Add a new prospect interactively."""
    prospects = load_prospects()

    print("\n--- Add New Prospect ---\n")

    name = input("Name: ").strip()
    if not name:
        print("Name is required.")
        return

    company = input("Company: ").strip()
    role = input("Role (e.g., Founder, Head of Product): ").strip() or "Founder"

    print(f"\nSource? {', '.join(VALID_SOURCES)}")
    source = input("Source: ").strip().lower()
    if source not in VALID_SOURCES:
        source = "other"

    linkedin = input("LinkedIn URL (optional): ").strip()
    website = input("Company website (optional): ").strip()
    personal_note = input("Personal note (what caught your eye about them): ").strip()

    prospect = {
        "id": len(prospects) + 1,
        "name": name,
        "company": company,
        "role": role,
        "source": source,
        "linkedin": linkedin,
        "website": website,
        "personal_note": personal_note,
        "status": "researched",
        "dm_sent_date": None,
        "dm_text": None,
        "replied_date": None,
        "signed_up_date": None,
        "notes": "",
        "created_at": datetime.now().isoformat(),
    }

    prospects.append(prospect)
    save_prospects(prospects)

    print(f"\n  Added: {name} ({company}) — status: researched")
    print(f"  Total prospects: {len(prospects)}\n")

    # Offer to generate DM
    gen = input("Generate DM now? (y/n): ").strip().lower()
    if gen == "y":
        generate_dm_for(prospect, prospects)


def generate_dm_for(prospect: dict, prospects: list[dict]):
    """Generate a personalized DM for a prospect."""
    source = prospect.get("source", "linkedin")
    template_key = source if source in DM_TEMPLATES else "linkedin"

    if not prospect.get("personal_note"):
        prospect["personal_note"] = input("Personal note (what caught your eye): ").strip()

    dm = DM_TEMPLATES[template_key].format(
        name=prospect["name"].split()[0],  # First name only
        company=prospect["company"],
        personal_note=prospect["personal_note"],
    )

    print(f"\n{'='*60}")
    print(f"DM for {prospect['name']} ({prospect['company']}):")
    print(f"{'='*60}")
    print(dm)
    print(f"{'='*60}")
    print(f"Characters: {len(dm)}")
    if len(dm) > 500:
        print("  (LinkedIn DMs have no strict limit, but shorter is better)")
    print()

    save_dm = input("Save this DM and mark as dm_sent? (y/n): ").strip().lower()
    if save_dm == "y":
        prospect["dm_text"] = dm
        prospect["dm_sent_date"] = date.today().isoformat()
        prospect["status"] = "dm_sent"
        save_prospects(prospects)
        print(f"  Saved! {prospect['name']} marked as dm_sent.\n")


def generate_dms():
    """Generate DMs for all prospects that don't have one yet."""
    prospects = load_prospects()
    pending = [p for p in prospects if p["status"] == "researched" and not p.get("dm_text")]

    if not pending:
        print("\nNo prospects need DMs. All researched prospects have DMs generated.\n")
        return

    print(f"\n{len(pending)} prospect(s) need DMs:\n")
    for p in pending:
        print(f"  [{p['id']}] {p['name']} ({p['company']}) — {p['source']}")

    print()
    for p in pending:
        generate_dm_for(p, prospects)


def list_prospects():
    """Show all prospects with their status."""
    prospects = load_prospects()

    if not prospects:
        print("\nNo prospects yet. Run: python3 scripts/prospect.py add\n")
        return

    print(f"\n{'='*80}")
    print(f"{'#':>3} | {'Name':<20} | {'Company':<18} | {'Source':<12} | {'Status':<14} | {'DM Sent':<10}")
    print(f"{'-'*3}-+-{'-'*20}-+-{'-'*18}-+-{'-'*12}-+-{'-'*14}-+-{'-'*10}")

    for p in prospects:
        status_icon = {
            "researched": "🔍",
            "dm_sent": "📨",
            "followed_up": "🔄",
            "replied": "💬",
            "interested": "🎯",
            "signed_up": "✅",
            "activated": "🚀",
            "no_reply": "⏳",
            "not_interested": "❌",
        }.get(p["status"], "  ")

        print(
            f"{p['id']:>3} | {p['name']:<20} | {p['company']:<18} | {p.get('source', ''):<12} | "
            f"{status_icon} {p.get('status', ''):<12} | {p.get('dm_sent_date') or '-':<10}"
        )

    print(f"{'='*80}\n")


def show_stats():
    """Show outreach metrics."""
    prospects = load_prospects()

    if not prospects:
        print("\nNo prospects yet.\n")
        return

    total = len(prospects)
    by_status = {}
    for p in prospects:
        by_status[p["status"]] = by_status.get(p["status"], 0) + 1

    dm_sent = sum(1 for p in prospects if p.get("dm_sent_date"))
    replied = by_status.get("replied", 0) + by_status.get("interested", 0) + by_status.get("signed_up", 0) + by_status.get("activated", 0)
    signed_up = by_status.get("signed_up", 0) + by_status.get("activated", 0)

    reply_rate = (replied / dm_sent * 100) if dm_sent > 0 else 0
    signup_rate = (signed_up / replied * 100) if replied > 0 else 0

    print(f"\n--- Outreach Stats ---")
    print(f"  Total prospects:    {total}")
    print(f"  DMs sent:           {dm_sent}")
    print(f"  Replies received:   {replied} ({reply_rate:.0f}% reply rate)")
    print(f"  Signups:            {signed_up} ({signup_rate:.0f}% of replies)")
    print()
    print("  By status:")
    for status in VALID_STATUSES:
        count = by_status.get(status, 0)
        if count > 0:
            print(f"    {status:<18} {count}")
    print()


def update_status():
    """Update a prospect's status."""
    prospects = load_prospects()
    list_prospects()

    try:
        pid = int(input("Prospect # to update: ").strip())
    except ValueError:
        print("Invalid number.")
        return

    prospect = next((p for p in prospects if p["id"] == pid), None)
    if not prospect:
        print(f"Prospect #{pid} not found.")
        return

    print(f"\nCurrent: {prospect['name']} ({prospect['company']}) — {prospect['status']}")
    print(f"Valid statuses: {', '.join(VALID_STATUSES)}")
    new_status = input("New status: ").strip().lower()

    if new_status not in VALID_STATUSES:
        print(f"Invalid status. Choose from: {', '.join(VALID_STATUSES)}")
        return

    prospect["status"] = new_status

    if new_status == "replied":
        prospect["replied_date"] = date.today().isoformat()
    elif new_status == "signed_up":
        prospect["signed_up_date"] = date.today().isoformat()

    notes = input("Add notes (optional): ").strip()
    if notes:
        prospect["notes"] = (prospect.get("notes", "") + f"\n[{date.today()}] {notes}").strip()

    save_prospects(prospects)
    print(f"\n  Updated: {prospect['name']} → {new_status}\n")


def export_markdown():
    """Export prospect list as markdown table for OUTREACH-TRACKING.md."""
    prospects = load_prospects()

    if not prospects:
        print("\nNo prospects to export.\n")
        return

    print("\n### Prospect List\n")
    print("| # | Name | Company | Role | Source | Status | DM Sent | Replied | Signed Up | Notes |")
    print("|---|------|---------|------|--------|--------|---------|---------|-----------|-------|")

    for p in prospects:
        print(
            f"| {p['id']} "
            f"| {p['name']} "
            f"| {p['company']} "
            f"| {p['role']} "
            f"| {p['source']} "
            f"| {p['status']} "
            f"| {p.get('dm_sent_date', '') or ''} "
            f"| {p.get('replied_date', '') or ''} "
            f"| {p.get('signed_up_date', '') or ''} "
            f"| {(p.get('notes', '') or '').replace(chr(10), ' ')[:50]} |"
        )

    print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()
    commands = {
        "add": add_prospect,
        "dm": generate_dms,
        "list": list_prospects,
        "stats": show_stats,
        "update": update_status,
        "export": export_markdown,
    }

    handler = commands.get(command)
    if handler:
        handler()
    else:
        print(f"Unknown command: {command}")
        print(f"Available: {', '.join(commands.keys())}")


if __name__ == "__main__":
    main()
