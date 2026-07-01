"""
Quick sanity check: confirms the live CSV is reachable from your machine
and prints a couple of sample events. Run this once after setup.

Usage:
    python verify_source.py
"""

from main import _fetch_raw_records, _normalize


def main():
    print("Downloading + parsing the live events CSV (this file is ~35-40MB)...")
    records = _fetch_raw_records(force=True)
    print(f"OK -- parsed {len(records)} total event rows.\n")

    print("Sample (first 3, both languages):")
    for r in records[:3]:
        ev = _normalize(r, lang="both")
        print(f"- {ev.date_start} | {ev.title_he} | {ev.title_en}")


if __name__ == "__main__":
    main()
