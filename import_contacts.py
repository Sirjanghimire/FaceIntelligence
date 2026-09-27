"""One-time local CSV import so recipients can be chosen by eye, not typed.

Accepts a small name/email CSV or common Google Contacts / Outlook exports.
No account access, network request, or dependency is needed.
"""
import argparse
import csv
import json
from pathlib import Path
import re

from jeff_agent import load_contacts


EMAIL_COLUMNS = ("email", "email address", "e-mail address", "e-mail 1 - value",
                 "email 1 - value", "e-mail 2 - value", "e-mail 3 - value")
NAME_COLUMNS = ("name", "full name", "display name")


def _clean(value):
    return " ".join((value or "").split())


def _fields(row):
    return {" ".join((key or "").replace("_", " ").lower().split()): _clean(value)
            for key, value in row.items() if key is not None}


def import_contacts(csv_path, contacts_path, selected_names=""):
    csv_path, contacts_path = Path(csv_path), Path(contacts_path)
    existing = load_contacts(contacts_path)
    known = {contact["email"].casefold() for contact in existing}
    filters = [name.strip().casefold() for name in selected_names.split(",") if name.strip()]
    added = []
    with csv_path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        headers = {" ".join(header.replace("_", " ").lower().split())
                   for header in (reader.fieldnames or [])}
        if not headers.intersection(EMAIL_COLUMNS):
            raise ValueError("CSV needs an Email / E-mail Address / E-mail 1 - Value column")
        for raw in reader:
            row = _fields(raw)
            address = next((row[column] for column in EMAIL_COLUMNS if row.get(column)), "")
            if not re.fullmatch(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", address):
                continue
            name = next((row[column] for column in NAME_COLUMNS if row.get(column)), "")
            if not name:
                name = _clean(" ".join((row.get("first name", ""), row.get("last name", ""))))
            name = name or address.split("@")[0]
            if filters and not any(part in name.casefold() for part in filters):
                continue
            if address.casefold() in known:
                continue
            added.append({"name": name, "email": address, "role": "contact"})
            known.add(address.casefold())

    if added:
        temp = contacts_path.with_name(contacts_path.name + ".tmp")
        temp.write_text(json.dumps(existing + added, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        temp.replace(contacts_path)
    return len(added), len(existing) + len(added)


def main():
    parser = argparse.ArgumentParser(
        description="Import selected recipients from a local CSV once; no eye typing of addresses")
    parser.add_argument("csv", help="path to exported Google/Outlook CSV or a name,email CSV")
    parser.add_argument("--names", default="",
                        help='optional comma-separated name fragments, e.g. "Priya,Sam"')
    args = parser.parse_args()
    try:
        added, total = import_contacts(args.csv, Path(__file__).parent / "contacts.json", args.names)
    except (FileNotFoundError, OSError, UnicodeError, ValueError) as exc:
        parser.exit(1, f"Could not import contacts: {exc}\n")
    print(f"Added {added} contact(s); {total} total. Restart run.bat to see the names in the eye picker.")
    if not added and args.names:
        print("No new names matched. Check the names in your CSV, or omit --names.")


if __name__ == "__main__":
    main()
