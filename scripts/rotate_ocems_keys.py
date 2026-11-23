"""Re-encrypt every stored OCEMS API key with the current OCEMS_KEY_SECRET.

Rotation:
  1. Set the new secret as OCEMS_KEY_SECRET and the previous one as
     OCEMS_KEY_SECRET_OLD (first rotation: leave _OLD empty; the old keys were
     encrypted with FLASK_SECRET_KEY, which is always tried).
  2. Run with the production environment:  venv/bin/python scripts/rotate_ocems_keys.py
     (add --dry-run first to see what would change).
  3. Deploy with the new OCEMS_KEY_SECRET; remove OCEMS_KEY_SECRET_OLD.

Imports only store + ocems_api (not app.py), so it starts no background jobs.
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

import ocems_api  # noqa: E402
import store  # noqa: E402

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database", "ocems_api_connections.csv")


def main(dry_run):
    if not os.getenv("OCEMS_KEY_SECRET"):
        sys.exit("OCEMS_KEY_SECRET is not set; nothing to rotate to.")
    if not store.exists(PATH):
        print("No stored OCEMS connections.")
        return
    with store.open(PATH, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    changed = failed = 0
    for row in rows:
        if not row.get("api_key_enc"):
            continue
        try:
            row["api_key_enc"] = ocems_api.rotate_key(row["api_key_enc"])
            changed += 1
        except ocems_api.OcemsApiError:
            failed += 1
            print("Can't read key for", row.get("connection_id"), "(left as is)")
    print(f"{changed} re-encrypted, {failed} unreadable")
    if dry_run or not changed:
        return
    with store.open(PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("Saved.")


if __name__ == "__main__":
    main("--dry-run" in sys.argv)
