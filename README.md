# Tel Aviv Events API

A small backend that fetches, filters (by date or date range), and
bilingually returns public Tel Aviv events. No UI — just an HTTP API.

## Data source

**data.gov.il** — Israel's national open data portal. It's CKAN-based
(the same open-source platform used by most government open-data sites
worldwide), publicly queryable, and needs no API key. This service uses
its "events by district" dataset (package `eventsdistrict`), filtered to
records mentioning Tel Aviv.

I looked at three possible sources before picking this one:

| Source | Pros | Cons |
|---|---|---|
| **data.gov.il (used here)** | No signup, standard documented CKAN API, stable | Nationwide dataset filtered by city (less TLV-specific), Hebrew only |
| Tel Aviv Municipality API portal (`apiportal.tel-aviv.gov.il`, `CityPOI` service) | Official, TLV-specific, has a dedicated `GET Events` endpoint | Requires signing up for a free developer key; docs are behind a login-gated console I couldn't fully inspect |
| Tel Aviv Open Data Portal (`opendata.tel-aviv.gov.il`) — DigiTel events dataset | TLV-specific, no key needed, has a date/neighborhood breakdown | Site is JS-rendered so I couldn't verify its exact query parameters from here — worth checking manually before relying on it |

If you want richer, official Tel Aviv-only data later, sign up for a key
at https://apiportal.tel-aviv.gov.il and I can add it as a second source
that merges with this one.

## Setup

```bash
cd tlv_events_api
pip install -r requirements.txt
```

## Verify the data first (recommended)

Dataset field names can shift slightly between refreshes. Run this once:

```bash
python inspect_schema.py
```

It prints one real record so you can confirm the Hebrew field names.
If titles/dates come back empty once the server is running, copy the
correct keys into the `_first_present(...)` calls inside `main.py`'s
`_normalize()` function — that's the only place mapping is done.

## Run

```bash
uvicorn main:app --reload
```

## Endpoints

```
GET /events?start=2026-07-01&end=2026-07-31    # date range (inclusive)
GET /events?date=2026-07-04                     # single day
GET /events                                     # no filter
GET /events?...&lang=he | en | both             # default: both
```

Response shape per event:

```json
{
  "title_he": "...",
  "title_en": "...",
  "description_he": "...",
  "description_en": "...",
  "date_start": "2026-07-04",
  "date_end": null,
  "neighborhood": "...",
  "location": "...",
  "raw": { "...original CKAN record, unmapped fields included..." }
}
```

`title_en` / `description_en` are produced with on-the-fly translation
(via `deep-translator`'s free Google Translate wrapper). If translation
fails for a record (rate limiting, no network), that record still comes
back with the Hebrew fields — English is just `null` for it, rather than
the whole request failing.

## Notes / next steps

- **Caching**: right now every `/events` request re-fetches from
  data.gov.il and re-translates. For a real app, add a cache (e.g.
  refresh every 15–30 min in the background) rather than hitting the
  upstream API and translator on every request.
- **Rate limits**: the free translation wrapper isn't meant for high
  volume — cache translated strings (already done in-memory via
  `lru_cache`, but that resets on restart; persist it if you need scale).
- **Adding the official municipal API**: once you have a key from
  apiportal.tel-aviv.gov.il, add a second client module and merge its
  results with this one — happy to write that once you have the key and
  can share what a raw response looks like.
