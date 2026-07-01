"""
Hebrew -> English translation helper.

Two backends, tried in this order:

1. Google Gemini (Google AI Studio) -- used automatically if the
   GEMINI_API_KEY environment variable is set. Higher quality, and
   handles idiomatic event titles better than a plain translate API.
   Plain REST call, no SDK dependency needed.

2. deep-translator's free Google Translate wrapper -- used as the
   fallback if no Gemini key is configured, or if a Gemini call fails.
   No API key required.

Either way, translation failures fail soft: this returns None rather
than raising, so the caller keeps the Hebrew field and just omits the
English one for that record instead of the whole request failing.
"""

import os
from functools import lru_cache
from typing import Optional

import requests

try:
    from deep_translator import GoogleTranslator
except ImportError:  # pragma: no cover
    GoogleTranslator = None

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def _translate_with_gemini(text: str) -> Optional[str]:
    if not GEMINI_API_KEY:
        return None
    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": GEMINI_API_KEY},
            json={
                "contents": [
                    {
                        "parts": [
                            {
                                "text": (
                                    "Translate the following Hebrew text to English. "
                                    "Reply with ONLY the translation, no quotes, no "
                                    "commentary:\n\n" + text
                                )
                            }
                        ]
                    }
                ]
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return None


def _translate_with_free_wrapper(text: str) -> Optional[str]:
    if GoogleTranslator is None:
        return None
    try:
        return GoogleTranslator(source="iw", target="en").translate(text)
    except Exception:
        return None


@lru_cache(maxsize=4096)
def to_english(text: Optional[str]) -> Optional[str]:
    if not text:
        return None

    result = _translate_with_gemini(text)
    if result:
        return result

    return _translate_with_free_wrapper(text)
