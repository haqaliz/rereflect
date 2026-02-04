#!/usr/bin/env python3
"""
Resend Email Template Management Script

Usage:
    python scripts/manage_resend_templates.py list
    python scripts/manage_resend_templates.py get <template_id>
    python scripts/manage_resend_templates.py create <name> <subject> <html_file>
    python scripts/manage_resend_templates.py update <template_id> <html_file>
    python scripts/manage_resend_templates.py delete <template_id>

Requires RESEND_API_KEY environment variable.
"""
import os
import sys
import json
import requests
from typing import Optional

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RESEND_API_BASE = "https://api.resend.com"


def get_headers():
    if not RESEND_API_KEY:
        print("Error: RESEND_API_KEY environment variable not set")
        sys.exit(1)
    return {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }


def list_templates():
    """List all templates in Resend account."""
    response = requests.get(
        f"{RESEND_API_BASE}/templates",
        headers=get_headers(),
        timeout=30,
    )

    if response.status_code == 200:
        data = response.json()
        templates = data.get("data", [])
        print(f"\nFound {len(templates)} templates:\n")
        for t in templates:
            print(f"  ID: {t.get('id')}")
            print(f"  Name: {t.get('name')}")
            print(f"  Subject: {t.get('subject', 'N/A')}")
            print(f"  Created: {t.get('created_at', 'N/A')}")
            print("-" * 50)
        return templates
    else:
        print(f"Error listing templates: {response.status_code}")
        print(response.text)
        return None


def get_template(template_id: str):
    """Get a specific template by ID."""
    response = requests.get(
        f"{RESEND_API_BASE}/templates/{template_id}",
        headers=get_headers(),
        timeout=30,
    )

    if response.status_code == 200:
        data = response.json().get("data", response.json())
        print(f"\nTemplate: {data.get('name')}")
        print(f"ID: {data.get('id')}")
        print(f"Subject: {data.get('subject')}")
        print(f"Created: {data.get('created_at')}")
        print(f"\nHTML Content:\n{'-' * 50}")
        print(data.get('html', 'N/A'))
        print(f"{'-' * 50}")
        return data
    else:
        print(f"Error getting template: {response.status_code}")
        print(response.text)
        return None


def extract_variables(html_content: str) -> list:
    """Extract {{{VAR}}} variables from HTML content."""
    import re
    pattern = r'\{\{\{([A-Z_]+)\}\}\}'
    matches = re.findall(pattern, html_content)
    # Return unique variables
    unique_vars = list(dict.fromkeys(matches))
    return [{"key": var, "type": "string"} for var in unique_vars]


def create_template(name: str, subject: str, html_file: str):
    """Create a new template from an HTML file."""
    if not os.path.exists(html_file):
        print(f"Error: HTML file not found: {html_file}")
        sys.exit(1)

    with open(html_file, "r") as f:
        html_content = f.read()

    # Extract variables from HTML and subject
    variables = extract_variables(html_content + subject)

    payload = {
        "name": name,
        "subject": subject,
        "html": html_content,
        "variables": variables,
    }

    print(f"Creating template with variables: {[v['key'] for v in variables]}")

    response = requests.post(
        f"{RESEND_API_BASE}/templates",
        headers=get_headers(),
        json=payload,
        timeout=30,
    )

    if response.status_code in [200, 201]:
        data = response.json()
        template_id = data.get("id")
        print(f"\nTemplate created successfully!")
        print(f"ID: {template_id}")
        print(f"Name: {name}")
        print(f"\nAdd to your .env file:")
        print(f"RESEND_TEMPLATE_{name.upper().replace('-', '_').replace(' ', '_')}={template_id}")
        return data
    else:
        print(f"Error creating template: {response.status_code}")
        print(response.text)
        return None


def update_template(template_id: str, html_file: str, subject: Optional[str] = None):
    """Update an existing template."""
    if not os.path.exists(html_file):
        print(f"Error: HTML file not found: {html_file}")
        sys.exit(1)

    with open(html_file, "r") as f:
        html_content = f.read()

    payload = {"html": html_content}
    if subject:
        payload["subject"] = subject

    response = requests.patch(
        f"{RESEND_API_BASE}/templates/{template_id}",
        headers=get_headers(),
        json=payload,
        timeout=30,
    )

    if response.status_code == 200:
        print(f"\nTemplate {template_id} updated successfully!")
        return response.json()
    else:
        print(f"Error updating template: {response.status_code}")
        print(response.text)
        return None


def delete_template(template_id: str):
    """Delete a template."""
    confirm = input(f"Are you sure you want to delete template {template_id}? (yes/no): ")
    if confirm.lower() != "yes":
        print("Cancelled.")
        return

    response = requests.delete(
        f"{RESEND_API_BASE}/templates/{template_id}",
        headers=get_headers(),
        timeout=30,
    )

    if response.status_code in [200, 204]:
        print(f"\nTemplate {template_id} deleted successfully!")
        return True
    else:
        print(f"Error deleting template: {response.status_code}")
        print(response.text)
        return False


def print_usage():
    print(__doc__)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1].lower()

    if command == "list":
        list_templates()

    elif command == "get":
        if len(sys.argv) < 3:
            print("Usage: python manage_resend_templates.py get <template_id>")
            sys.exit(1)
        get_template(sys.argv[2])

    elif command == "create":
        if len(sys.argv) < 5:
            print("Usage: python manage_resend_templates.py create <name> <subject> <html_file>")
            sys.exit(1)
        create_template(sys.argv[2], sys.argv[3], sys.argv[4])

    elif command == "update":
        if len(sys.argv) < 4:
            print("Usage: python manage_resend_templates.py update <template_id> <html_file> [subject]")
            sys.exit(1)
        subject = sys.argv[4] if len(sys.argv) > 4 else None
        update_template(sys.argv[2], sys.argv[3], subject)

    elif command == "delete":
        if len(sys.argv) < 3:
            print("Usage: python manage_resend_templates.py delete <template_id>")
            sys.exit(1)
        delete_template(sys.argv[2])

    else:
        print(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)
