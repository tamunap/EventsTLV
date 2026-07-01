"""
Minimal Hebrew -> English translation helper.

The events dataset only comes back in Hebrew, so to satisfy a "both
languages" API response we translate on the fly using deep-translator's
free Google Translate wrapper (no API key required).

If translation fails for any reason (no network, rate limiting, service
down), we fail soft and return None -- the caller keeps the Hebrew field
and just omits the English one for that record, rather than the whole
request failing.
"""

from functools import lru_cache
from typing import Optional

try:
    from deep_translator import GoogleTranslator
except ImportError:  # pragma: no cover
    GoogleTranslator = None


@lru_cache(maxsize=4096)
def to_english(text: Optional[str]) -> Optional[str]:
    if not text or GoogleTranslator is None:
        return None
    try:
        return GoogleTranslator(source="iw", target="en").translate(text)
    except Exception:
        return None
