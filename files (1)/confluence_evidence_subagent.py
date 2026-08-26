"""Confluence evidence subagent.

Extracts Confluence page references from the change request, resolves them
through the Confluence client, validates them, and writes the verdict back
to state.

NOTE: the state keys and the log_subagent_state call below are written to
match the GitLab and Jira subagents. Open one of those side by side and
line up the names before wiring this in. If they use a different state
container or a different logging helper, follow theirs, not this.
"""

import asyncio
import os
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph

from src.utils_v2.confluence import (
    ConfluenceAPI,
    ConfluenceConfigError,
    PagesAPI,
    handle_confluence_exception,
)
from src.utils_v2.confluence_utils import extract_page_refs, validate_confluence_evidence
from src.utils_v2.logger import shared_logger
from src.utils_v2.state_logger import log_subagent_state

logger = shared_logger(__name__)

SUBAGENT_NAME = "CONFLUENCE"
_MAX_CONCURRENT_PAGES = 5


class ConfluenceSubagentState(TypedDict, total=False):
    cr_number: str
    cr_data: dict[str, Any]
    confluence_refs: list[dict[str, Any]]
    confluence_evidence_data: dict[str, Any]
    evidence_subagent: str
    errors: Annotated[list[dict[str, Any]], lambda a, b: (a or []) + (b or [])]


def _cr_text(state):
    """Everything on the CR that might contain a Confluence link.

    Adjust the keys here to match what get_cr_data actually puts on state.
    """
    cr = state.get("cr_data") or {}
    fields = [
        cr.get("description"),
        cr.get("short_description"),
        cr.get("justification"),
        cr.get("implementation_plan"),
        cr.get("test_plan"),
        cr.get("backout_plan"),
        cr.get("work_notes"),
        cr.get("comments"),
    ]
    return "\n".join(str(f) for f in fields if f)


def extract_refs(state):
    """Find every Confluence page the CR points at."""
    host_hint = None
    base_url = os.getenv("CONFLUENCE_BASE_URL", "")
    if base_url:
        host_hint = base_url.split("//")[-1].split("/")[0]

    refs = extract_page_refs(_cr_text(state), host_hint=host_hint)
    logger.info(f"{SUBAGENT_NAME}: found {len(refs)} Confluence reference(s) on {state.get('cr_number')}")
    return {"confluence_refs": refs, "evidence_subagent": SUBAGENT_NAME}


async def fetch_pages(state):
    """Resolve each reference. One bad page does not fail the whole run."""
    refs = state.get("confluence_refs") or []
    if not refs:
        return {"confluence_evidence_data": {"pages": [], "pages_found": 0}}

    pages, errors = [], []

    try:
        async with ConfluenceAPI() as api:
            client = PagesAPI(api)
            semaphore = asyncio.Semaphore(_MAX_CONCURRENT_PAGES)

            async def resolve_one(ref):
                async with semaphore:
                    try:
                        return await client.resolve(ref)
                    except Exception as exc:
                        errors.append(
                            handle_confluence_exception(exc, context=f"resolve {ref.get('source_url')}")
                        )
                        return None

            resolved = await asyncio.gather(*(resolve_one(ref) for ref in refs))
            pages = [page for page in resolved if page]

    except ConfluenceConfigError as exc:
        # Credentials are not configured. Surface it rather than reporting
        # a clean "no evidence found", which would be a lie.
        logger.error(f"{SUBAGENT_NAME}: {exc}")
        return {
            "confluence_evidence_data": {
                "pages": [],
                "pages_found": 0,
                "validation_passed": False,
                "summary": "Confluence is not configured; evidence could not be checked",
                "configuration_error": True,
            },
            "errors": [handle_confluence_exception(exc, context="client init")],
        }

    logger.info(f"{SUBAGENT_NAME}: resolved {len(pages)}/{len(refs)} page(s)")
    return {
        "confluence_evidence_data": {"pages": pages, "pages_found": len(pages)},
        "errors": errors,
    }


def validate_evidence(state):
    """Apply the criteria in confluence_utils and write the verdict."""
    data = state.get("confluence_evidence_data") or {}
    if data.get("configuration_error"):
        return {}

    result = validate_confluence_evidence(
        data.get("pages") or [],
        cr_number=state.get("cr_number"),
    )
    logger.info(f"{SUBAGENT_NAME}: {result['summary']}")
    return {"confluence_evidence_data": result}


def log_state(state):
    log_subagent_state(SUBAGENT_NAME, state)
    return {}


def _build_confluence_subagent():
    workflow = StateGraph(ConfluenceSubagentState)

    workflow.add_node("extract_refs", extract_refs)
    workflow.add_node("fetch_pages", fetch_pages)
    workflow.add_node("validate_evidence", validate_evidence)
    workflow.add_node("log_state", log_state)

    workflow.add_edge(START, "extract_refs")
    workflow.add_edge("extract_refs", "fetch_pages")
    workflow.add_edge("fetch_pages", "validate_evidence")
    workflow.add_edge("validate_evidence", "log_state")
    workflow.add_edge("log_state", END)

    return workflow.compile()


confluence_evidence_subagent = _build_confluence_subagent()
