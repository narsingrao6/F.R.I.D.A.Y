"""
F.R.I.D.A.Y. Browser / Web Search tool.

Opens websites and performs web searches in the default browser.

Handles:
    "open youtube"                    -> open the website
    "search for bitcoin price"        -> Google search
    "google how to cook rice"         -> Google search
    "open youtube and search minecraft"
    "open browser and search python"  -> site-specific search
"""

from __future__ import annotations

import os
import re
import urllib.parse

from app_launcher import (
    _WEBSITES,
    _resolve_canonical,
    handle_app_command,
)


_WAKE_WORD = re.compile(
    r"^(?:hey\s+)?"
    r"(?:friday|fraiday|fry\s*day|fryday)"
    r"(?:[,.\s]+|$)",
    re.IGNORECASE,
)

# "open <site> and search <query>" / "open <site> then look up <query>"
_OPEN_SEARCH_RE = re.compile(
    r"^(?:open|launch|start)\s+(?:the\s+)?(.+?)"
    r"\s+(?:and\s+)?(?:then\s+)?"
    r"(?:search|look\s+up|lookup|find|google)\s+"
    r"(?:for\s+)?(.+)$",
    re.IGNORECASE,
)

# "close <site> and search <query>" (context may glue them together)
_CLOSE_SITE_RE = re.compile(
    r"^(?:close|quit|exit|close\s+down|exit\s+out\s+of)\s+"
    r"(?:the\s+)?(.+?)"
    r"\s*(?:and\s+)?(?:then\s+)?"
    r"(?:search|look\s+up|lookup|find|google)\s+"
    r"(?:for\s+)?.*$",
    re.IGNORECASE,
)

# "search <query>" / "look up <query>" / "find <query>" / "google <query>"
_SEARCH_RE = re.compile(
    r"^(?:search|look\s+up|lookup|find|google)\s+"
    r"(?:the\s+web\s+)?(?:for\s+)?(.+?)\s*$",
    re.IGNORECASE,
)

# Search endpoints for well-known sites.
_SEARCH_TEMPLATES = {
    "youtube": "https://www.youtube.com/results?search_query={q}",
    "you tube": "https://www.youtube.com/results?search_query={q}",
    "utube": "https://www.youtube.com/results?search_query={q}",
    "google": "https://www.google.com/search?q={q}",
    "bing": "https://www.bing.com/search?q={q}",
    "x": "https://twitter.com/search?q={q}",
    "twitter": "https://twitter.com/search?q={q}",
    "reddit": "https://www.reddit.com/search/?q={q}",
    "wikipedia": "https://en.wikipedia.org/wiki/Special:Search?search={q}",
    "wiki": "https://en.wikipedia.org/wiki/Special:Search?search={q}",
    "amazon": "https://www.amazon.com/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "github": "https://github.com/search?q={q}",
    "stack overflow": "https://stackoverflow.com/search?q={q}",
    "stackoverflow": "https://stackoverflow.com/search?q={q}",
}


def _build_search_url(site: str | None, query: str) -> str:
    """Return a search URL for a site + query, or a plain web search."""

    q = urllib.parse.quote_plus(query)

    canonical = _resolve_canonical(site).strip() if site else ""

    template = _SEARCH_TEMPLATES.get(canonical)

    if template:
        return template.format(q=q)

    # Search inside an arbitrary known website (site: operator in Google).
    base = _WEBSITES.get(canonical) if canonical else None

    if base:
        domain = urllib.parse.urlparse(base).netloc
        if domain.startswith("www."):
            domain = domain[4:]
        site_q = urllib.parse.quote(f"site:{domain}")
        return f"https://www.google.com/search?q={site_q}+{q}"

    return f"https://www.google.com/search?q={q}"


def _open_url(url: str) -> bool:
    try:
        os.startfile(url)
        return True
    except Exception:
        return False


def _ack(language: str, site: str | None = None) -> str:
    if language == "te":
        return "బ్రౌజర్ లో తెరుస్తున్నాను బాస్."

    if language == "hi":
        return "ब्राउज़र में खोल रही हूँ बॉस।"

    if site:
        return f"Searching {site} for you, Boss."

    return "Searching the web, Boss."


def handle_browser_command(
    command: str,
    language: str = "en",
) -> str | None:
    """
    Handle a browser or web-search command.

    Returns a spoken response, or None when this command is not a
    browser request (the plain open/close path stays in the app launcher).
    """

    if not command or not command.strip():
        return None

    text = _WAKE_WORD.sub(
        "",
        command.strip(),
    ).strip()

    if not text:
        return None

    # "close youtube and search minecraft" -> close the youtube site/tab.
    match = _CLOSE_SITE_RE.match(text)

    if match:
        site = match.group(1).strip().strip(" -")

        if site:
            return handle_app_command(
                f"close {site}",
                language,
            )

    # "open <site> and search <query>"
    match = _OPEN_SEARCH_RE.match(text)

    if match:
        site = match.group(1).strip()
        query = match.group(2).strip()

        if site and query:
            url = _build_search_url(site, query)

            if _open_url(url):
                label = (
                    _resolve_canonical(site)
                    if site not in {"browser", "the browser"}
                    else "the web"
                )
                return _ack(language, label or site)

            return "Sorry Boss, I couldn't open the browser."

    # "search for <query>"
    match = _SEARCH_RE.match(text)

    if match:
        query = match.group(1).strip().strip(" .")

        if query:
            url = _build_search_url(None, query)

            if _open_url(url):
                return _ack(language)

            return "Sorry Boss, I couldn't open the browser."

    # Everything else (open/close) still goes through the app launcher.
    return handle_app_command(text, language)