"""Remove an account's two-step sign-in (lost or replaced phone). Admins set
it up again at their next sign-in; other users can turn it back on in Profile.

Run with the production environment:

    venv/bin/python scripts/reset_admin_mfa.py admin@example.com

Imports only store (not app.py), so it starts no background jobs.
"""
import csv
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(ROOT, ".env"))

import store  # noqa: E402

PATH = os.path.join(ROOT, "database", "admin_mfa.csv")
FIELDS = ["user_id", "email", "secret_enc", "enabled_at", "last_step", "failed_count", "locked_until"]


def main(email):
    email = email.strip().lower()
    if not store.exists(PATH):
        sys.exit("No account has two-step sign-in yet.")
    with store.open(PATH, "r", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    keep = [r for r in rows if (r.get("email") or "").strip().lower() != email]
    if len(keep) == len(rows):
        sys.exit(f"No two-step sign-in found for {email}.")
    with store.open(PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows({k: r.get(k, "") for k in FIELDS} for r in keep)
    print(f"Reset. {email} can sign in with their password; admins set up two-step sign-in again.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
