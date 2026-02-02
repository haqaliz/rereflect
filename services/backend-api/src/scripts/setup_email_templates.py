"""
Script to create/update email templates in Resend.

Usage:
    cd services/backend-api
    python -m src.scripts.setup_email_templates --create    # Create new templates
    python -m src.scripts.setup_email_templates --update    # Update existing templates
    python -m src.scripts.setup_email_templates --list      # List all templates
    python -m src.scripts.setup_email_templates --delete    # Delete all templates
"""
import os
import sys
import argparse
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

import resend

# Initialize Resend
resend.api_key = os.getenv("RESEND_API_KEY")

if not resend.api_key:
    print("Error: RESEND_API_KEY not set in environment")
    sys.exit(1)

# Import templates
from src.templates.email_templates import ALL_TEMPLATES


def create_templates():
    """Create all email templates in Resend."""
    print("\n🎨 Creating email templates in Resend...\n")
    print("=" * 60)

    created_templates = {}

    for template_config in ALL_TEMPLATES:
        name = template_config["name"]
        print(f"\n📧 Creating template: {name}")

        try:
            result = resend.Templates.create({
                "name": name,
                "subject": template_config["subject"],
                "html": template_config["html"],
                "variables": template_config["variables"],
            })

            template_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
            if template_id:
                created_templates[name] = template_id
                print(f"   ✅ Created: {template_id}")
            else:
                print(f"   ❌ Failed: {result}")

        except Exception as e:
            print(f"   ❌ Error: {e}")

    print("\n" + "=" * 60)
    print("\n📋 Add these to your .env file:\n")
    for name, template_id in created_templates.items():
        env_name = f"RESEND_TEMPLATE_{name.upper().replace('-', '_')}"
        print(f"{env_name}={template_id}")

    return created_templates


def update_templates():
    """Update existing templates in Resend."""
    print("\n🔄 Updating email templates in Resend...\n")

    # First, list existing templates
    try:
        result = resend.Templates.list()
        templates = result.get("data", []) if isinstance(result, dict) else getattr(result, "data", [])
    except Exception as e:
        print(f"❌ Error listing templates: {e}")
        return

    # Create a map of name -> id
    existing = {}
    for t in templates:
        t_id = t.get("id") if isinstance(t, dict) else getattr(t, "id", None)
        t_name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
        if t_name and t_id:
            existing[t_name] = t_id

    print(f"Found {len(existing)} existing templates\n")
    print("=" * 60)

    for template_config in ALL_TEMPLATES:
        name = template_config["name"]

        if name in existing:
            template_id = existing[name]
            print(f"\n🔄 Updating template: {name} ({template_id})")

            try:
                # Delete and recreate to update (simpler than update API)
                resend.Templates.remove(template_id)
                print(f"   🗑️  Deleted old version")

                result = resend.Templates.create({
                    "name": name,
                    "subject": template_config["subject"],
                    "html": template_config["html"],
                    "variables": template_config["variables"],
                })
                new_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
                print(f"   ✅ Recreated: {new_id}")

            except Exception as e:
                print(f"   ❌ Error: {e}")
        else:
            print(f"\n⚠️  Template '{name}' not found - creating new...")
            try:
                result = resend.Templates.create({
                    "name": name,
                    "subject": template_config["subject"],
                    "html": template_config["html"],
                    "variables": template_config["variables"],
                })
                template_id = result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
                print(f"   ✅ Created: {template_id}")
            except Exception as e:
                print(f"   ❌ Error: {e}")

    print("\n" + "=" * 60)
    print("\n✅ Templates updated!\n")


def list_templates():
    """List all existing templates."""
    print("\n📋 Existing templates in Resend:\n")
    print("=" * 60)

    try:
        result = resend.Templates.list()
        templates = result.get("data", []) if isinstance(result, dict) else getattr(result, "data", [])

        if not templates:
            print("\nNo templates found.\n")
            return

        for t in templates:
            t_id = t.get("id") if isinstance(t, dict) else getattr(t, "id", None)
            t_name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
            t_created = t.get("created_at") if isinstance(t, dict) else getattr(t, "created_at", None)
            print(f"\n📧 {t_name}")
            print(f"   ID: {t_id}")
            if t_created:
                print(f"   Created: {t_created}")

        print("\n" + "=" * 60 + "\n")

    except Exception as e:
        print(f"❌ Error listing templates: {e}\n")


def delete_all_templates():
    """Delete all templates (use with caution!)."""
    print("\n⚠️  Deleting all templates in Resend...\n")

    try:
        result = resend.Templates.list()
        templates = result.get("data", []) if isinstance(result, dict) else getattr(result, "data", [])

        if not templates:
            print("No templates to delete.\n")
            return

        confirm = input(f"Are you sure you want to delete {len(templates)} templates? (yes/no): ")
        if confirm.lower() != "yes":
            print("Cancelled.\n")
            return

        for t in templates:
            t_id = t.get("id") if isinstance(t, dict) else getattr(t, "id", None)
            t_name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
            try:
                resend.Templates.remove(t_id)
                print(f"   🗑️  Deleted: {t_name}")
            except Exception as e:
                print(f"   ❌ Error deleting {t_name}: {e}")

        print("\n✅ All templates deleted.\n")

    except Exception as e:
        print(f"❌ Error: {e}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage Resend email templates")
    parser.add_argument("--list", action="store_true", help="List existing templates")
    parser.add_argument("--create", action="store_true", help="Create new templates")
    parser.add_argument("--update", action="store_true", help="Update existing templates")
    parser.add_argument("--delete", action="store_true", help="Delete all templates")
    args = parser.parse_args()

    if args.list:
        list_templates()
    elif args.create:
        create_templates()
    elif args.update:
        update_templates()
    elif args.delete:
        delete_all_templates()
    else:
        print("\nUsage:")
        print("  python -m src.scripts.setup_email_templates --create  # Create new templates")
        print("  python -m src.scripts.setup_email_templates --update  # Update existing templates")
        print("  python -m src.scripts.setup_email_templates --list    # List all templates")
        print("  python -m src.scripts.setup_email_templates --delete  # Delete all templates")
        print()
