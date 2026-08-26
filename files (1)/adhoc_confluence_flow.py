#!/usr/bin/env python
"""Ad-hoc test harness for the Confluence evidence flow.

Four modes, cheapest first. Start at the top and only move down once the
level above is green.

    uv run python test_scripts/adhoc_confluence_flow.py offline
    uv run python test_scripts/adhoc_confluence_flow.py page <page-id-or-url>
    uv run python test_scripts/adhoc_confluence_flow.py subagent
    uv run python test_scripts/adhoc_confluence_flow.py graph --cr CHG0012345

offline    parsing and validation only, no network, no credentials.
           This is the one that works today.
page       resolve one real page. First thing that touches the network,
           so it is where auth problems surface.
subagent   run the compiled Confluence subagent against a synthetic CR.
graph      run the whole eta_cab_v2 graph against a real CR number.

Run from the agent root:
    cd cab-ai-api/agents/eta_cab_v2
"""

import argparse
import asyncio
import json
import os
import sys
import traceback
from pathlib import Path

# Make `src.` importable when this is run directly from test_scripts/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Deliberately messy. Real CR descriptions are pasted from email and Teams,
# so links arrive wrapped in punctuation, inside angle brackets, duplicated,
# and mixed with non-Confluence URLs that must NOT match.
SAMPLE_CR_TEXT = """
Change request for the Q3 payments migration.

Design doc: https://confluence.example.com/display/CAB/Payments+Migration+Design
Runbook (see <https://confluence.example.com/pages/viewpage.action?pageId=884213>).
Cloud-style link for comparison: https://ally.atlassian.net/wiki/spaces/CAB/pages/99110/Rollback+Plan

Duplicate of the design doc:
https://confluence.example.com/display/CAB/Payments+Migration+Design

Not Confluence and must be ignored:
  https://gitlab.example.com/team/repo/-/merge_requests/42
  https://jira.example.com/browse/TR-459
  https://confluence.example.com/spacedirectory/view.action
"""

# What normalise_page() produces, so validation can be exercised without a
# live instance. One page passes, three fail for different reasons.
SAMPLE_PAGES = [
    {
        "page_id": "884213",
        "title": "Payments Migration Runbook",
        "status": "current",
        "space_key": "CAB",
        "version": 7,
        "last_updated": "2026-08-01T14:22:00.000Z",
        "last_updated_by": "Some Engineer",
        "labels": ["runbook", "cab-approved"],
        "url": "https://confluence.example.com/pages/viewpage.action?pageId=884213",
    },
    {
        "page_id": "771002",
        "title": "Stale Architecture Notes",
        "status": "current",
        "space_key": "CAB",
        "version": 2,
        "last_updated": "2023-01-09T09:00:00.000Z",  # older than MAX_PAGE_AGE_DAYS
        "last_updated_by": "Someone Else",
        "labels": [],
        "url": "https://confluence.example.com/pages/viewpage.action?pageId=771002",
    },
    {
        "page_id": "551900",
        "title": "Archived Design",
        "status": "archived",  # fails the status check
        "space_key": "CAB",
        "version": 11,
        "last_updated": "2026-08-10T10:00:00.000Z",
        "last_updated_by": "Someone Else",
        "labels": ["design"],
        "url": "https://confluence.example.com/pages/viewpage.action?pageId=551900",
    },
    {
        "page_id": "440111",
        "title": "No Timestamp Page",
        "status": "current",
        "space_key": "CAB",
        "version": 1,
        "last_updated": "",  # missing timestamp
        "labels": [],
        "url": "https://confluence.example.com/pages/viewpage.action?pageId=440111",
    },
]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def header(text):
    print(f"\n{'=' * 70}\n{text}\n{'=' * 70}")


def dump(obj):
    print(json.dumps(obj, indent=2, default=str))


def ok(text):
    print(f"  PASS  {text}")


def fail(text):
    print(f"  FAIL  {text}")


# ---------------------------------------------------------------------------
# Mode: offline
# ---------------------------------------------------------------------------

def run_offline():
    """Parsing and validation. No network, no credentials, no excuses."""
    from src.utils_v2 import confluence_utils as cu

    failures = 0

    header("1. URL extraction")
    urls = cu.extract_confluence_urls(SAMPLE_CR_TEXT)
    for url in urls:
        print(f"    {url}")

    checks = [
        ("finds the display-style link", any("/display/CAB/" in u for u in urls)),
        ("finds the viewpage link", any("pageId=884213" in u for u in urls)),
        ("finds the cloud-style link", any("/wiki/spaces/CAB/" in u for u in urls)),
        ("ignores the GitLab link", not any("gitlab" in u for u in urls)),
        ("ignores the Jira link", not any("/browse/" in u for u in urls)),
        ("ignores the space directory link", not any("spacedirectory" in u for u in urls)),
        ("strips trailing punctuation", not any(u.endswith((".", ")", ",")) for u in urls)),
    ]
    for label, passed in checks:
        (ok if passed else fail)(label)
        failures += 0 if passed else 1

    header("2. Reference parsing and dedup")
    refs = cu.extract_page_refs(SAMPLE_CR_TEXT)
    dump(refs)

    design_refs = [r for r in refs if r.get("title", "").startswith("Payments Migration")]
    checks = [
        ("dedups the repeated design doc", len(design_refs) == 1),
        (
            "decodes + into spaces in the title",
            any(r.get("title") == "Payments Migration Design" for r in refs),
        ),
        ("pulls page_id off the viewpage URL", any(r.get("page_id") == "884213" for r in refs)),
        ("pulls page_id off the cloud URL", any(r.get("page_id") == "99110" for r in refs)),
        ("keeps source_url on every ref", all(r.get("source_url") for r in refs)),
    ]
    for label, passed in checks:
        (ok if passed else fail)(label)
        failures += 0 if passed else 1

    header("3. Per-page validation")
    for page in SAMPLE_PAGES:
        passed, reasons = cu.validate_page(page, cr_number="CHG0012345")
        verdict = "PASS" if passed else "FAIL"
        print(f"  [{verdict}] {page['title']}")
        for reason in reasons:
            print(f"           - {reason}")

    header("4. Aggregate verdict")
    result = cu.validate_confluence_evidence(SAMPLE_PAGES, cr_number="CHG0012345")
    dump({k: v for k, v in result.items() if k != "pages"})

    checks = [
        ("counts all four pages", result["pages_found"] == 4),
        ("passes exactly one", result["pages_passing"] == 1),
        ("overall verdict is True when any page passes", result["validation_passed"] is True),
    ]
    for label, passed in checks:
        (ok if passed else fail)(label)
        failures += 0 if passed else 1

    header("5. Empty input")
    empty = cu.validate_confluence_evidence([], cr_number="CHG0012345")
    print(f"  summary: {empty['summary']}")
    passed = empty["validation_passed"] is False and empty["pages_found"] == 0
    (ok if passed else fail)("no pages means no evidence, not a silent pass")
    failures += 0 if passed else 1

    print()
    if failures:
        print(f"{failures} check(s) failed.")
    else:
        print("All offline checks passed.")
        print(
            "\nNOTE: these assert the criteria currently in confluence_utils.py,\n"
            "which are placeholders. When the CAB owners confirm the real rules,\n"
            "the fixtures above need updating too or this file will happily\n"
            "certify the wrong behaviour."
        )
    return 1 if failures else 0


# ---------------------------------------------------------------------------
# Mode: page
# ---------------------------------------------------------------------------

async def _resolve_one(target):
    from src.utils_v2.confluence import ConfluenceAPI, PagesAPI
    from src.utils_v2.confluence_utils import parse_page_ref, validate_page

    ref = parse_page_ref(target) if target.startswith("http") else {"page_id": target}
    if not ref:
        print(f"Could not parse {target!r} as a Confluence reference.")
        return 1

    print(f"Resolved reference: {ref}")
    async with ConfluenceAPI() as api:
        client = PagesAPI(api)
        page = await client.resolve(ref)

    header("Normalised page")
    dump(page)

    header("Validation")
    passed, reasons = validate_page(page)
    print(f"  verdict: {'PASS' if passed else 'FAIL'}")
    for reason in reasons:
        print(f"    - {reason}")
    return 0


def run_page(target):
    """First mode that touches the network. Auth problems land here."""
    if not os.getenv("CONFLUENCE_BASE_URL") or not os.getenv("CONFLUENCE_TOKEN"):
        print(
            "CONFLUENCE_BASE_URL and CONFLUENCE_TOKEN must be set.\n"
            "Both are still unresolved for this project. If CAB traffic has to\n"
            "go through Apigee, direct tokens will not work at all."
        )
        return 2
    return asyncio.run(_resolve_one(target))


# ---------------------------------------------------------------------------
# Mode: subagent
# ---------------------------------------------------------------------------

def run_subagent(cr_number):
    """Run the compiled subgraph against a synthetic CR."""
    from src.subagents.confluence_evidence_subagent import confluence_evidence_subagent

    state = {
        "cr_number": cr_number,
        "cr_data": {
            "number": cr_number,
            "short_description": "Q3 payments migration",
            "description": SAMPLE_CR_TEXT,
        },
    }

    header(f"Invoking confluence_evidence_subagent for {cr_number}")
    result = asyncio.run(confluence_evidence_subagent.ainvoke(state))

    header("confluence_refs")
    dump(result.get("confluence_refs"))

    header("confluence_evidence_data")
    dump(result.get("confluence_evidence_data"))

    if result.get("errors"):
        header("errors")
        dump(result["errors"])

    data = result.get("confluence_evidence_data") or {}
    if data.get("configuration_error"):
        print(
            "\nCredentials are not configured, so the subagent correctly reported\n"
            "that it could not check rather than reporting no evidence found.\n"
            "Extraction and graph wiring are still exercised above."
        )
    return 0


# ---------------------------------------------------------------------------
# Mode: graph
# ---------------------------------------------------------------------------

def run_graph(cr_number):
    """Full eta_cab_v2 run. Proves the router actually dispatches."""
    from src.graph import graph

    header(f"Full graph run for {cr_number}")
    result = asyncio.run(graph.ainvoke({"cr_number": cr_number}))

    for key in (
        "gitlab_evidence_data",
        "jira_evidence_data",
        "confluence_evidence_data",
    ):
        header(key)
        value = result.get(key)
        if value is None:
            print("  (absent from state)")
            print(
                "  If this subagent should have run, check that\n"
                "  evidence_subagent_router can return its node name. A node with\n"
                "  no inbound route compiles fine and never executes."
            )
        else:
            dump(value)

    header("summary")
    dump(result.get("summary") or result.get("final_summary"))
    return 0


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)

    sub.add_parser("offline", help="parsing and validation only, no network")

    p_page = sub.add_parser("page", help="resolve one real Confluence page")
    p_page.add_argument("target", help="page id or full page URL")

    p_sub = sub.add_parser("subagent", help="run the compiled Confluence subagent")
    p_sub.add_argument("--cr", default="CHG0012345")

    p_graph = sub.add_parser("graph", help="run the whole eta_cab_v2 graph")
    p_graph.add_argument("--cr", required=True)

    args = parser.parse_args()

    try:
        if args.mode == "offline":
            return run_offline()
        if args.mode == "page":
            return run_page(args.target)
        if args.mode == "subagent":
            return run_subagent(args.cr)
        if args.mode == "graph":
            return run_graph(args.cr)
    except ImportError as exc:
        print(f"\nImport failed: {exc}\n")
        print(
            "Run this from the agent root so `src.` resolves:\n"
            "    cd cab-ai-api/agents/eta_cab_v2\n"
            "    uv run python test_scripts/adhoc_confluence_flow.py offline"
        )
        return 2
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
