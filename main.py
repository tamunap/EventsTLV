"""
Tel Aviv Events API
====================
A small backend service that aggregates public event data for Tel Aviv
and exposes a filterable REST API (by single date or date range).

Data source: data.gov.il -- Israel's national open data portal, which is
CKAN-based (https://data.gov.il/api/3/action/...). It hosts a nationwide
"events by district" dataset that includes Tel Aviv-Yafo. This is used
instead of the Tel Aviv Municipality's own API portal because that one
requires a manually-issued developer key (see README.md for details on
adding it later as a second source).

Run:
    pip install -r requirements.txt
    uvicorn main:app --reload

Then:
    GET http://127.0.0.1:8000/events?start=2026-07-01&end=2026-07-31
    GET http://127.0.0.1:8000/events?date=2026-07-04
    GET http://127.0.0.1:8000/events                (no filter -> everything found)

Query params:
    start, end   ISO date (YYYY-MM-DD), inclusive range
    date         single ISO date, shorthand for start=end=date
    lang         "he" | "en" | "both" (default "both")
"""

from datetime import date, datetime
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from translator import to_english

CKAN_BASE = "https://data.gov.il/api/3/action"

# The dataset's CKAN "package" slug (stable) -- resource_id underneath it
# can be regenerated when the file is refreshed, so we look that part up
# dynamically instead of hardcoding it.
PACKAGE_ID = "eventsdistrict"  # "Events by district" (אירועים לפי מחוז)

CITY_FILTER = "תל אביב"

app = FastAPI(title="Tel Aviv Events API", version="1.0.0")

_resource_id_cache: Optional[str] = None


def _get_resource_id() -> str:
    """Resolve the current datastore resource_id for the events package."""
    global _resource_id_cache
    if _resource_id_cache:
        return _resource_id_cache

    resp = requests.get(f"{CKAN_BASE}/package_show", params={"id": PACKAGE_ID}, timeout=15)
    resp.raise_for_status()
    payload = resp.json()

    if not payload.get("success"):
        raise RuntimeError(f"CKAN package_show failed: {payload}")

    resources = payload["result"]["resources"]
    if not resources:
        raise RuntimeError("No resources found under the events dataset")

    for r in resources:
        if r.get("datastore_active"):
            _resource_id_cache = r["id"]
            return _resource_id_cache

    # Fall back to the first listed resource if none is flagged datastore-active
    _resource_id_cache = resources[0]["id"]
    return _resource_id_cache


class Event(BaseModel):
    title_he: str
    title_en: Optional[str] = None
    description_he: Optional[str] = None
    description_en: Optional[str] = None
    date_start: Optional[str] = None
    date_end: Optional[str] = None
    neighborhood: Optional[str] = None
    location: Optional[str] = None
    raw: Dict[str, Any]  # full original record, for fields we didn't map


def _fetch_raw_records(limit: int = 1000) -> List[Dict[str, Any]]:
    resource_id = _get_resource_id()
    params = {
        "resource_id": resource_id,
        "q": CITY_FILTER,
        "limit": limit,
    }
    resp = requests.get(f"{CKAN_BASE}/datastore_search", params=params, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    if not payload.get("success"):
        raise RuntimeError(f"CKAN datastore_search failed: {payload}")
    return payload["result"]["records"]


def _first_present(record: Dict[str, Any], *keys: str) -> Optional[str]:
    for k in keys:
        if record.get(k):
            return record[k]
    return None


def _normalize(record: Dict[str, Any], lang: str) -> Event:
    # NOTE: Hebrew column names in this dataset can vary slightly between
    # refreshes. Run inspect_schema.py once to print real field names for
    # your current snapshot, then adjust the key lists below if nothing
    # is coming through.
    title_he = _first_present(record, "שם_אירוע", "שם האירוע", "event_name", "שם") or ""
    desc_he = _first_present(record, "תיאור", "תיאור_אירוע", "description")
    date_start = _first_present(record, "תאריך_התחלה", "תאריך", "start_date", "מתאריך")
    date_end = _first_present(record, "תאריך_סיום", "עד_תאריך", "end_date")
    neighborhood = _first_present(record, "שכונה", "אזור", "neighborhood")
    location = _first_present(record, "מיקום", "כתובת", "location")

    title_en = desc_en = None
    if lang in ("en", "both"):
        title_en = to_english(title_he) if title_he else None
        desc_en = to_english(desc_he) if desc_he else None

    return Event(
        title_he=title_he,
        title_en=title_en,
        description_he=desc_he,
        description_en=desc_en,
        date_start=date_start,
        date_end=date_end,
        neighborhood=neighborhood,
        location=location,
        raw=record,
    )


def _parse_date(value: str) -> date:
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {value!r}")


@app.get("/events", response_model=List[Event])
def get_events(
    start: Optional[str] = Query(None, description="Start date, YYYY-MM-DD"),
    end: Optional[str] = Query(None, description="End date, YYYY-MM-DD (inclusive)"),
    date_: Optional[str] = Query(None, alias="date", description="Single date, YYYY-MM-DD"),
    lang: str = Query("both", pattern="^(he|en|both)$"),
):
    """Return Tel Aviv events, optionally filtered to a date or date range."""
    if date_:
        start = end = date_

    try:
        start_d = _parse_date(start) if start else None
        end_d = _parse_date(end) if end else None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        raw_records = _fetch_raw_records()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream data source error: {e}")

    events = [_normalize(r, lang) for r in raw_records]

    if start_d or end_d:
        filtered = []
        for ev in events:
            if not ev.date_start:
                continue
            try:
                ev_date = _parse_date(ev.date_start)
            except ValueError:
                continue
            if start_d and ev_date < start_d:
                continue
            if end_d and ev_date > end_d:
                continue
            filtered.append(ev)
        events = filtered

    return events


@app.get("/")
def root():
    return {
        "service": "Tel Aviv Events API",
        "usage": [
            "GET /events?start=YYYY-MM-DD&end=YYYY-MM-DD&lang=both",
            "GET /events?date=YYYY-MM-DD",
        ],
        "source": "data.gov.il (CKAN) -- dataset: events by district",
    }
