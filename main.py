"""
Tel Aviv Events API
====================
A small backend service that fetches, filters (by date or date range),
and bilingually returns public Tel Aviv events -- sourced directly from
the Tel Aviv Municipality's own "Events in DigiTel" open dataset.

Data source: a stable, direct-download CSV published by the Tel Aviv
Open Data portal (opendatasource.tel-aviv.gov.il), hosted on Azure Blob
Storage:

    https://saopendata.blob.core.windows.net/open-data-public-site/events_digitel.csv

This is the *actual* municipal events feed (not a nationwide proxy), no
API key required. It's a plain file, not a query endpoint, so this
service downloads and re-parses it on a refresh interval (see
CACHE_TTL_SECONDS below) rather than hitting it on every request -- the
file is ~35-40MB.

Known format (confirmed from a real sample of the file):
    Encoding:  UTF-16 LE, with a leading BOM
    Delimiter: semicolon (;)
    Columns:   rn;dt_event;title;NeighborhoodName;merhav;URL
      rn                row number
      dt_event          event date, YYYY-MM-DD
      title             event title (Hebrew)
      NeighborhoodName  neighborhood (Hebrew)
      merhav            city area/district (Hebrew)
      URL               link to the full event page on tel-aviv.gov.il

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

import csv
import io
import os
import time
from datetime import date, datetime
from typing import Optional, List, Dict, Any

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from translator import to_english

CSV_URL = "https://saopendata.blob.core.windows.net/open-data-public-site/events_digitel.csv"

# The file is large (~35-40MB); don't re-download/re-parse on every request.
# Refresh at most this often. Override with an env var if you want a
# different cadence.
CACHE_TTL_SECONDS = int(os.environ.get("CACHE_TTL_SECONDS", 30 * 60))  # 30 min

app = FastAPI(title="Tel Aviv Events API", version="2.0.0")

# Allow browser-based frontends (e.g. a Google AI Studio app, or any site)
# to call this API directly. Wide open ("*") since this only serves public
# read-only event data -- nothing sensitive to protect here.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache: Dict[str, Any] = {"records": None, "fetched_at": 0.0}


class Event(BaseModel):
    title_he: str
    title_en: Optional[str] = None
    date_start: Optional[str] = None
    neighborhood_he: Optional[str] = None
    neighborhood_en: Optional[str] = None
    area_he: Optional[str] = None
    area_en: Optional[str] = None
    url: Optional[str] = None
    raw: Dict[str, Any]  # full original record, for anything we didn't map


def _fetch_raw_records(force: bool = False) -> List[Dict[str, Any]]:
    """Download + parse the CSV, using an in-memory cache to avoid
    re-fetching a ~35-40MB file on every request."""
    now = time.time()
    if (
        not force
        and _cache["records"] is not None
        and (now - _cache["fetched_at"]) < CACHE_TTL_SECONDS
    ):
        return _cache["records"]

    resp = requests.get(CSV_URL, timeout=60)
    resp.raise_for_status()

    # Confirmed encoding: UTF-16 LE with a BOM.
    text = resp.content.decode("utf-16-le")
    text = text.lstrip("\ufeff")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")
    records = list(reader)

    _cache["records"] = records
    _cache["fetched_at"] = now
    return records


def _normalize(record: Dict[str, Any], lang: str) -> Event:
    title_he = (record.get("title") or "").strip()
    date_start = (record.get("dt_event") or "").strip() or None
    neighborhood_he = (record.get("NeighborhoodName") or "").strip() or None
    area_he = (record.get("merhav") or "").strip() or None
    url = (record.get("URL") or "").strip() or None

    title_en = neighborhood_en = area_en = None
    if lang in ("en", "both"):
        title_en = to_english(title_he) if title_he else None
        neighborhood_en = to_english(neighborhood_he) if neighborhood_he else None
        area_en = to_english(area_he) if area_he else None

    return Event(
        title_he=title_he,
        title_en=title_en,
        date_start=date_start,
        neighborhood_he=neighborhood_he,
        neighborhood_en=neighborhood_en,
        area_he=area_he,
        area_en=area_en,
        url=url,
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
    refresh: bool = Query(False, description="Force a re-download of the source CSV"),
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
        raw_records = _fetch_raw_records(force=refresh)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Upstream data source error: {e}")

    # Filter by date first (on the raw dt_event string) -- cheaper than
    # translating events we're going to throw away anyway.
    if start_d or end_d:
        filtered_raw = []
        for r in raw_records:
            raw_date = (r.get("dt_event") or "").strip()
            if not raw_date:
                continue
            try:
                ev_date = _parse_date(raw_date)
            except ValueError:
                continue
            if start_d and ev_date < start_d:
                continue
            if end_d and ev_date > end_d:
                continue
            filtered_raw.append(r)
        raw_records = filtered_raw

    return [_normalize(r, lang) for r in raw_records]


@app.get("/")
def root():
    return {
        "service": "Tel Aviv Events API",
        "usage": [
            "GET /events?start=YYYY-MM-DD&end=YYYY-MM-DD&lang=both",
            "GET /events?date=YYYY-MM-DD",
            "GET /events?...&refresh=true   (force re-download of the source file)",
        ],
        "source": "Tel Aviv Municipality -- 'Events in DigiTel' open dataset",
        "source_url": CSV_URL,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
    }
