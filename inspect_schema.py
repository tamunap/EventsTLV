"""
Run this once after installing requirements to see the *real* field names
coming back from data.gov.il for the events dataset. If main.py isn't
picking up titles/dates, copy the Hebrew keys you see printed here into
the _first_present(...) calls in main.py's _normalize() function.

Usage:
    python inspect_schema.py
"""

import json
import requests

from main import _get_resource_id, CKAN_BASE, CITY_FILTER


def main():
    resource_id = _get_resource_id()
    print(f"resource_id: {resource_id}\n")

    resp = requests.get(
        f"{CKAN_BASE}/datastore_search",
        params={"resource_id": resource_id, "q": CITY_FILTER, "limit": 3},
        timeout=20,
    )
    resp.raise_for_status()
    payload = resp.json()

    records = payload["result"]["records"]
    if not records:
        print("No records returned for the Tel Aviv filter -- try without "
              "the 'q' filter to see the dataset's general shape.")
        return

    print("Sample record (field names + example values):\n")
    print(json.dumps(records[0], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
