# Confluence capability: wiring

## 1. Drop the files in

```
src/utils_v2/confluence/__init__.py
src/utils_v2/confluence/confluence.py
src/utils_v2/confluence/exceptions.py
src/utils_v2/confluence/pages.py
src/utils_v2/confluence_utils.py
src/subagents/confluence_evidence_subagent.py
```

## 2. state_types.py

```python
class ConfluencePageData(TypedDict, total=False):
    page_id: str
    title: str
    url: str
    space_key: str
    version: int
    last_updated: str
    last_updated_by: str
    labels: list[str]
    validation_passed: bool
    failure_reasons: list[str]


class ConfluenceEvidenceData(TypedDict, total=False):
    pages: list[ConfluencePageData]
    pages_found: int
    pages_passing: int
    validation_passed: bool
    summary: str
    configuration_error: bool
```

Then add `confluence_evidence_data: ConfluenceEvidenceData` to the main
CAB state class, next to `gitlab_evidence_data` and the Jira one.

## 3. graph.py

Import, next to line 49:

```python
from src.subagents.confluence_evidence_subagent import confluence_evidence_subagent
```

Node, next to the other subagent registrations around line 490:

```python
workflow.add_node("confluence_evidence_subagent_node", confluence_evidence_subagent)
```

Edge, after line 505:

```python
workflow.add_edge("confluence_evidence_subagent_node", "summarize_results")
```

Router: `evidence_subagent_router` has to be able to return
`"confluence_evidence_subagent_node"`, or the node compiles and never runs.
This is the step that got missed on Jira, so check it there too while you
are in the file.

## 4. .env

```
CONFLUENCE_BASE_URL=
CONFLUENCE_TOKEN=
CONFLUENCE_AUTH_MODE=bearer     # or basic, for Cloud
CONFLUENCE_EMAIL=               # only when AUTH_MODE=basic
```

Line 31 of the current .env does not parse. Fix that at the same time or
these will not load either.

## 5. Run

```
cd cab-ai-api/agents/eta_cab_v2
uv run langgraph dev
```

## Still open

1. **Cloud or Server/DC.** The client targets Server/DC `/rest/api/content`.
   The header comment in confluence.py lists the three changes for Cloud.
   The base URL answers it: `*.atlassian.net` means Cloud.
2. **Auth.** Same unresolved question as Jira. If CAB has to go through
   Apigee, none of the direct-token config above is right.
3. **What counts as evidence.** The criteria block in confluence_utils.py
   is a placeholder. Page status, required labels, max age, and whether the
   page must reference the CR are all guesses. Get these from the CAB owners
   before this goes anywhere near a real change request. A validator that
   passes everything is worse than no validator, because it makes the
   summary look authoritative.
