# Tel Aviv Events API

A small backend that fetches, filters (by date or date range), and
bilingually returns Tel Aviv events. No UI — just an HTTP API.

## Data source

The **Tel Aviv Municipality's own "Events in DigiTel" dataset** —
published on the city's open data portal and hosted as a direct-download
CSV on Azure Blob Storage:

```
https://saopendata.blob.core.windows.net/open-data-public-site/events_digitel.csv
```

This isn't a query API — it's a flat file the municipality refreshes
periodically. That's actually fine for our purposes: the backend
downloads it, caches it in memory, and re-downloads on a timer (default
every 30 minutes — see `CACHE_TTL_SECONDS`) rather than parsing a
~35–40MB file on every request.

**Format** (confirmed from a real sample of the file):
- Encoding: UTF-16 LE, with a leading BOM
- Delimiter: semicolon (`;`)
- Columns: `rn;dt_event;title;NeighborhoodName;merhav;URL`

| Column | Meaning |
|---|---|
| `rn` | row number |
| `dt_event` | event date, `YYYY-MM-DD` |
| `title` | event title (Hebrew) |
| `NeighborhoodName` | neighborhood (Hebrew) |
| `merhav` | city area/district (Hebrew) |
| `URL` | link to the full event page on tel-aviv.gov.il |

No API key, no signup — it's a public file.

## Setup

```bash
cd tlv_events_api
pip install -r requirements.txt
```

## Verify it works (recommended)

```bash
python verify_source.py
```

This downloads the live file once and prints a few sample events so you
can confirm connectivity and parsing before starting the server.

## Run

```bash
uvicorn main:app --reload
```

## Endpoints

```
GET /events?start=2026-07-01&end=2026-07-31    # date range (inclusive)
GET /events?date=2026-07-04                     # single day
GET /events                                     # no filter (all ~82k rows)
GET /events?...&lang=he | en | both             # default: both
GET /events?...&refresh=true                    # force a fresh download, skip cache
```

Response shape per event:

```json
{
  "title_he": "מדיטציה ונשימות לפתיחת בוקר רגוע",
  "title_en": "Meditation and breathing for a calm morning start",
  "date_start": "2026-07-01",
  "neighborhood_he": "הצפון הישן - החלק הצפוני",
  "neighborhood_en": "The Old North - Northern Part",
  "area_he": "מרחב מרכז מערב",
  "area_en": "Central-West Area",
  "url": "https://www.tel-aviv.gov.il/Pages/MainItemPage.aspx?...",
  "raw": { "...original CSV row, unmodified..." }
}
```

`title_en`, `neighborhood_en`, and `area_en` are all produced with
on-the-fly translation (via `deep-translator`'s free Google Translate
wrapper). Neighborhood and area names repeat a lot across the ~82k rows
(Tel Aviv only has a few dozen of each), so they're cheap to translate
even at volume thanks to the in-memory cache in `translator.py`. If
translation fails for any field (rate limiting, no network), that field
comes back `null` — the Hebrew version is always still present, and the
request never fails outright because of a translation hiccup.

## Notes / next steps

- **Cache duration**: 30 minutes by default. Set `CACHE_TTL_SECONDS` as
  an env var to change it, or pass `?refresh=true` on any request to
  force an immediate re-download.
- **Translation performance**: for `lang=both` requests without a date
  filter, you'd be translating ~82k titles — slow and likely to hit
  rate limits. In practice you'll almost always pass `start`/`end`
  (or `date`), which filters *before* translation happens, so only the
  matching day's events get translated.
- **Historical junk data**: a handful of rows have a placeholder date of
  `1900-01-01` (missing/unset dates in the source). These are simply
  excluded whenever you filter by date, and only show up if you call
  `/events` with no date filter at all.
- **Sample file**: `sample_events_digitel.csv` in this folder is a small
  20-row excerpt (UTF-8, for easy inspection) — not used by the code,
  just there for reference.
