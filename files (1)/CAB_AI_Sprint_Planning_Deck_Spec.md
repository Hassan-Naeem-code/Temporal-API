# CAB AI Sprint Planning Deck: Build Spec

## Instructions for building the deck

- Update the existing deck `CABAI_Deployment_Plan.pptx` (Ally template). Keep the existing theme, fonts, colors, title slide layout, and agenda slide layout (blue left panel with numbered items).
- Do not invent content. Use only what is written below.
- Every Jira reference is written as `CABAI-XXX`. Leave these placeholders exactly as written; they will be replaced with real ticket numbers afterward.
- Tables should use the template's table styling. Keep text concise; do not add extra bullets.
- No em dashes anywhere in the deck.
- Mark the file Ally Proprietary, as the original is.

---

## Slide 1: Title

**Title:** CAB AI - Sprint Planning
**Date:** Sep 22, 2026

---

## Slide 2: Agenda

Use the existing numbered agenda layout.

01. Last Meeting Takeaways
02. Sprint Progress: Completed Tickets
03. Current Sprint: In Progress
04. Open Questions and Decisions Needed
05. Next Steps

---

## Slide 3: Last Meeting Takeaways

**Subtitle:** Jira Evidence Validation, discussed with Beverly (Sep 15, 2026)

Base version agreed; it will be enhanced based on feedback. The agent triggers when a CR's evidence link contains a Jira ticket number or link:

1. **Jira relevance:** The agent verifies the Jira ticket relates to the CR. If the Jira title and acceptance criteria align with the CR, processing continues.
2. **Acceptance criteria validation:** If no acceptance criteria exist in the Description or Acceptance Criteria field, the CR fails (current default, pending confirmation). If acceptance criteria exist, processing continues.
3. **Evidence analysis:** The agent validates text, images, and attachments from both the ticket body and the comments section.

---

## Slide 4: Sprint Progress: Completed Tickets

**Subtitle:** Deployed to QA Sep 8; all items tested and confirmed by Beverly

| Jira | Item | Status |
|---|---|---|
| CABAI-XXX | Confluence integration with CAB AI Evidence Analysis | Done, in QA |
| CABAI-XXX | Feedback applied to Similarity Analysis | Done, in QA |
| CABAI-XXX | Performance evidence requirements surfaced during evidence analysis | Done, in QA |
| CABAI-XXX (INC3935322) | Bug fix: performance evidence showed "exception" fields when not required | Done, in QA |

Detail for the bug fix row (small text under the table or as a sub-note):
- Performance evidence checker now skips LLM analysis when the field is absent or set to "No"
- Added two performance testing exceptions: Application IRR (Inherent Risk Rating) medium-low or low, and Prod A/B flip

---

## Slide 5: Current Sprint: In Progress

| Jira | Item | Status |
|---|---|---|
| CABAI-XXX | Jira evidence validation subagent (relevance, acceptance criteria, evidence analysis) | In progress |
| CABAI-XXX | Evidence analysis performance: heavy CR runtime reduced from ~640s to ~45s | Dev complete, testing |
| CABAI-XXX | Attachment processing: .log/.txt read directly as text, .docx extraction fixed, Processing Errors section added to UI | Dev complete, testing |

---

## Slide 6: Open Questions and Decisions Needed

**From the Jira validation discussion:**
1. **Large attachments:** For attachments over 100 pages, stop and flag the CR for manual review, or analyze the document in parts?
2. **Match strictness:** Is a clear topical match between the Jira and the CR sufficient, or must the Jira reference the CR number directly?
3. **Missing acceptance criteria:** Confirm the result: FAIL, PARTIAL, or flagged for reviewer attention?
4. **Nested evidence:** If a Jira links to GitLab, Confluence, etc., how should the agent check those nested evidence items?

**Technical decisions:**
5. **Confluence access:** Allowlist the NAT gateway IP per environment with the Atlassian admin, or route Confluence through Apigee?
6. **Verdict on processing failures:** Should any attachment that fails processing cap the verdict at PARTIAL?

---

## Slide 7: Next Steps

- Finalize Jira evidence validation based on answers to the open questions
- Implement verdict cap when an attachment fails processing
- Test PDF and XLSX attachments end to end
- Add chunked processing for large PDFs
- Resolve Confluence access approach for higher environments

---

## Checklist before presenting (for Hassan, not for the deck)

- [ ] Replace every `CABAI-XXX` with the real Jira key (open the links in the Sep 8 "CAB AI New Feature Testing" email)
- [ ] Verify the incident number INC3935322
- [ ] Only keep Slide 5 rows that have real tickets; create tickets for untracked work or remove those rows
- [ ] Confirm the existing slides "CAB AI Plan" and "How to Access" should stay, and place them after Slide 7 if so
