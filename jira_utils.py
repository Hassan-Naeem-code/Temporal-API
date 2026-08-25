"""
Jira evidence validation utilities.

Mirrors the shape of ``gitlab_utils.validate_gitlab_evidence``: takes a list of
Jira URLs (or bare issue keys), resolves each one against the Jira REST API and
returns a (status, explanation, details) tuple.
"""

import logging
import os
import re
from typing import Any

from src.utils_v2.jira.exceptions import JiraException, handle_jira_exception
from src.utils_v2.jira.jira import JiraAuth
from src.utils_v2.jira.tickets import TicketsAPI

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Status categories that count as "the work is finished".
# Jira exposes statusCategory.key as one of: "new", "indeterminate", "done".
ACCEPTED_STATUS_CATEGORIES = {"done"}

# Explicit status names that count as complete, checked case-insensitively.
# Adjust to match the workflow used by the Jira project CAB AI validates against.
ACCEPTED_STATUS_NAMES = {
    "done",
    "closed",
    "resolved",
    "complete",
    "completed",
}

# Matches /browse/TR-459 and also a bare TR-459 passed without a URL.
_ISSUE_KEY_IN_URL = re.compile(r"/browse/([A-Za-z][A-Za-z0-9_]*-\d+)")
_BARE_ISSUE_KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_]*-\d+)$")


def _build_tickets_client() -> TicketsAPI:
    """
    Build a TicketsAPI client from environment configuration.

    Environment variables:
        JIRA_BASE_URL: e.g. https://jira.int.ally.com
        JIRA_TOKEN:    API token (Cloud) or personal access token (Server/DC)
        JIRA_EMAIL:    account email; only set this for Jira Cloud
    """
    base_url = os.getenv("JIRA_BASE_URL")
    token = os.getenv("JIRA_TOKEN")
    email = os.getenv("JIRA_EMAIL") or None

    if not base_url:
        raise JiraException("JIRA_BASE_URL is not configured")
    if not token:
        raise JiraException("JIRA_TOKEN is not configured")

    auth = JiraAuth(base_url=base_url, token=token, email=email)
    return TicketsAPI(auth)


def extract_issue_key(value: str) -> str | None:
    """
    Pull a Jira issue key out of a URL or return it directly if already a key.

    Args:
        value: A Jira browse URL or a bare issue key

    Returns:
        The uppercased issue key, or None if nothing could be extracted
    """
    if not value:
        return None

    candidate = str(value).strip()

    match = _ISSUE_KEY_IN_URL.search(candidate)
    if match:
        return match.group(1).upper()

    match = _BARE_ISSUE_KEY.match(candidate)
    if match:
        return match.group(1).upper()

    logger.warning(f"Could not extract a Jira issue key from: {candidate}")
    return None


def _summarise_ticket(issue_key: str, raw: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten a raw Jira issue payload into the fields the subagent reports on.
    """
    fields = raw.get("fields") or {}

    status = fields.get("status") or {}
    status_category = status.get("statusCategory") or {}
    issue_type = fields.get("issuetype") or {}
    assignee = fields.get("assignee") or {}
    reporter = fields.get("reporter") or {}
    priority = fields.get("priority") or {}
    resolution = fields.get("resolution") or {}

    return {
        "key": raw.get("key") or issue_key,
        "summary": fields.get("summary") or "N/A",
        "status": status.get("name") or "Unknown",
        "status_category": (status_category.get("key") or "unknown").lower(),
        "issue_type": issue_type.get("name") or "Unknown",
        "assignee": assignee.get("displayName") or "Unassigned",
        "reporter": reporter.get("displayName") or "Unknown",
        "priority": priority.get("name") or "N/A",
        "resolution": resolution.get("name") or "Unresolved",
        "labels": fields.get("labels") or [],
        "created": fields.get("created") or "N/A",
        "updated": fields.get("updated") or "N/A",
        "web_url": raw.get("_web_url") or "N/A",
    }


def _is_ticket_complete(ticket: dict[str, Any]) -> bool:
    """A ticket passes when its status category or status name says it's done."""
    if ticket.get("status_category") in ACCEPTED_STATUS_CATEGORIES:
        return True
    return str(ticket.get("status", "")).strip().lower() in ACCEPTED_STATUS_NAMES


def validate_jira_evidence(
    jira_urls: list[str],
) -> tuple[str, str, list[dict[str, Any]]]:
    """
    Validate Jira evidence by resolving each URL and inspecting the ticket.

    Args:
        jira_urls: Jira browse URLs (or bare issue keys) extracted from the CR

    Returns:
        (status, explanation, ticket_details) where status is one of
        "PASS", "PARTIAL", "FAIL" or "UNABLE TO PROCESS".
    """
    if not jira_urls:
        return "FAIL", "No Jira URLs were supplied for validation.", []

    try:
        client = _build_tickets_client()
    except JiraException as exc:
        message = handle_jira_exception(exc)
        logger.error(f"Could not build Jira client: {message}")
        return "UNABLE TO PROCESS", message, []

    ticket_details: list[dict[str, Any]] = []
    unresolved: list[str] = []

    for url in jira_urls:
        issue_key = extract_issue_key(url)

        if not issue_key:
            unresolved.append(f"{url} (no issue key found)")
            continue

        try:
            logger.info(f"Fetching Jira ticket {issue_key}")
            response = client.get_ticket(issue_key)
            raw = response.get("data") or {}

            if not raw:
                unresolved.append(f"{issue_key} (empty response body)")
                continue

            # Preserve the browse URL so the report can link back to it.
            raw["_web_url"] = url if "/browse/" in str(url) else f"{client.auth.base_url}/browse/{issue_key}"

            ticket_details.append(_summarise_ticket(issue_key, raw))

        except JiraException as exc:
            message = handle_jira_exception(exc)
            logger.error(f"Failed to fetch {issue_key}: {message}")
            unresolved.append(f"{issue_key} ({message})")

        except Exception as exc:  # noqa: BLE001 - surfaced in the explanation
            logger.error(f"Unexpected error fetching {issue_key}: {exc}")
            unresolved.append(f"{issue_key} ({exc})")

    # ---- Decide the overall outcome -------------------------------------
    if not ticket_details:
        explanation = "No Jira tickets could be retrieved from the provided URLs."
        if unresolved:
            explanation += " Failures: " + "; ".join(unresolved)
        return "FAIL", explanation, []

    complete = [t for t in ticket_details if _is_ticket_complete(t)]
    incomplete = [t for t in ticket_details if not _is_ticket_complete(t)]

    if not incomplete and not unresolved:
        explanation = (
            f"All {len(complete)} Jira ticket(s) were retrieved and are in a "
            f"completed status."
        )
        return "PASS", explanation, ticket_details

    if complete and (incomplete or unresolved):
        parts = []
        if incomplete:
            names = ", ".join(f"{t['key']} ({t['status']})" for t in incomplete)
            parts.append(f"{len(incomplete)} ticket(s) not yet complete: {names}")
        if unresolved:
            parts.append(f"{len(unresolved)} URL(s) could not be resolved: " + "; ".join(unresolved))
        explanation = (
            f"{len(complete)} of {len(ticket_details)} ticket(s) are complete. "
            + " ".join(parts)
        )
        return "PARTIAL", explanation, ticket_details

    names = ", ".join(f"{t['key']} ({t['status']})" for t in incomplete)
    explanation = f"No Jira tickets are in a completed status. Current: {names}"
    if unresolved:
        explanation += " Unresolved: " + "; ".join(unresolved)
    return "FAIL", explanation, ticket_details
