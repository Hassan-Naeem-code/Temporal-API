"""Extract Confluence references from a change request and validate them.

Same two jobs as jira_utils.py: pull references out of free text, then
decide whether what came back counts as evidence.
"""

import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, unquote, urlparse

from src.utils_v2.logger import shared_logger

logger = shared_logger(__name__)


# ---------------------------------------------------------------------------
# PLACEHOLDER CRITERIA - NOT CONFIRMED WITH THE TEAM
#
# Everything in this block is a guess at what makes a Confluence page count
# as evidence for a CR. Confirm with the CAB owners before this ships, and
# delete this comment once it is settled. Whatever they say, keep the rules
# as data up here rather than as ifs buried in validate_confluence_evidence.
# ---------------------------------------------------------------------------
VALID_PAGE_STATUSES = {"current"}
REQUIRED_LABELS = set()          # e.g. {"cab-approved"} if sign-off is label driven
MAX_PAGE_AGE_DAYS = 180          # None disables the staleness check
REQUIRE_CR_REFERENCE = False     # True = page must mention the CR number
# ---------------------------------------------------------------------------


# https://confluence.host/pages/viewpage.action?pageId=12345
_VIEWPAGE_URL = re.compile(r"/pages/viewpage\.action\?[^\s\"'<>]*pageId=(\d+)", re.IGNORECASE)

# Cloud: https://x.atlassian.net/wiki/spaces/CAB/pages/12345/Some+Title
_CLOUD_PAGE_URL = re.compile(r"/wiki/spaces/([A-Za-z0-9_~]+)/pages/(\d+)", re.IGNORECASE)

# Server/DC: https://confluence.host/display/CAB/Some+Page+Title
_DISPLAY_URL = re.compile(r"/display/([A-Za-z0-9_~]+)/([^\s\"'<>#?]+)", re.IGNORECASE)

_URL_IN_TEXT = re.compile(r"https?://[^\s\"'<>\]\)]+", re.IGNORECASE)


def extract_confluence_urls(text, host_hint=None):
    """Return every Confluence-looking URL in a blob of text.

    host_hint narrows results to one instance. Pass CONFLUENCE_BASE_URL's
    host when you have it, otherwise anything with a Confluence-shaped path
    is accepted.
    """
    if not text:
        return []

    found = []
    for url in _URL_IN_TEXT.findall(str(text)):
        url = url.rstrip(".,;:)")
        if host_hint and host_hint.lower() not in url.lower():
            continue
        if (
            _VIEWPAGE_URL.search(url)
            or _CLOUD_PAGE_URL.search(url)
            or _DISPLAY_URL.search(url)
        ):
            found.append(url)

    seen = set()
    deduped = []
    for url in found:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def parse_page_ref(url):
    """Turn one Confluence URL into a reference PagesAPI.resolve() understands.

    Returns {"page_id": ...} or {"space_key": ..., "title": ...}, or None if
    the URL is Confluence-shaped but unparseable.
    """
    if not url:
        return None

    match = _VIEWPAGE_URL.search(url)
    if match:
        return {"page_id": match.group(1), "source_url": url}

    match = _CLOUD_PAGE_URL.search(url)
    if match:
        return {"space_key": match.group(1), "page_id": match.group(2), "source_url": url}

    match = _DISPLAY_URL.search(url)
    if match:
        space_key = match.group(1)
        title = unquote(match.group(2)).replace("+", " ").strip("/")
        return {"space_key": space_key, "title": title, "source_url": url}

    # Fall back to a pageId hiding in the query string.
    parsed = urlparse(url)
    page_id = (parse_qs(parsed.query).get("pageId") or [None])[0]
    if page_id:
        return {"page_id": page_id, "source_url": url}

    logger.warning(f"Confluence URL matched but did not parse: {url}")
    return None


def extract_page_refs(text, host_hint=None):
    """extract_confluence_urls + parse_page_ref, deduplicated."""
    refs = []
    seen = set()
    for url in extract_confluence_urls(text, host_hint=host_hint):
        ref = parse_page_ref(url)
        if not ref:
            continue
        key = ref.get("page_id") or f"{ref.get('space_key')}::{ref.get('title')}"
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _parse_timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        logger.warning(f"Unparseable Confluence timestamp: {value!r}")
        return None


def validate_page(page, cr_number=None):
    """Check one normalised page against the criteria above.

    Returns (passed, [reasons]). Reasons are only populated on failure and
    are written to be readable in the CAB summary output.
    """
    reasons = []

    status = (page.get("status") or "").lower()
    if VALID_PAGE_STATUSES and status not in VALID_PAGE_STATUSES:
        reasons.append(f"page status is {status or 'unknown'}, expected one of {sorted(VALID_PAGE_STATUSES)}")

    if REQUIRED_LABELS:
        missing = REQUIRED_LABELS - set(page.get("labels") or [])
        if missing:
            reasons.append(f"missing required label(s): {sorted(missing)}")

    if MAX_PAGE_AGE_DAYS is not None:
        updated = _parse_timestamp(page.get("last_updated"))
        if updated is None:
            reasons.append("no last-updated timestamp on the page")
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_PAGE_AGE_DAYS)
            if updated < cutoff:
                reasons.append(
                    f"last updated {updated.date()}, older than the {MAX_PAGE_AGE_DAYS} day limit"
                )

    if REQUIRE_CR_REFERENCE and cr_number:
        haystack = f"{page.get('title', '')} {' '.join(page.get('labels') or [])}"
        if cr_number.lower() not in haystack.lower():
            reasons.append(f"page does not reference {cr_number}")

    return (not reasons), reasons


def validate_confluence_evidence(pages, cr_number=None):
    """Roll per-page results into the verdict the subagent puts on state."""
    results = []
    for page in pages:
        passed, reasons = validate_page(page, cr_number=cr_number)
        results.append(
            {
                "page_id": page.get("page_id"),
                "title": page.get("title"),
                "url": page.get("url"),
                "space_key": page.get("space_key"),
                "last_updated": page.get("last_updated"),
                "validation_passed": passed,
                "failure_reasons": reasons,
            }
        )

    passing = [r for r in results if r["validation_passed"]]
    return {
        "pages": results,
        "pages_found": len(results),
        "pages_passing": len(passing),
        "validation_passed": bool(passing),
        "summary": (
            f"{len(passing)} of {len(results)} linked Confluence page(s) met the evidence criteria"
            if results
            else "No Confluence pages were linked on this change request"
        ),
    }
