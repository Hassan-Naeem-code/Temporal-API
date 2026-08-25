import logging
import operator
from typing_extensions import TypedDict, List, Annotated

from langgraph.graph import StateGraph, END, START

from src.utils_v2.state_logger import format_state_for_pprint
from src.utils_v2.jira_utils import validate_jira_evidence

# Import type definitions from shared types module
from src.state_types import (
    ValidationResult,
    CRData,
    JiraTicketData,
)

logger = logging.getLogger(__name__)


def log_subagent_state(state):
    logger.info("=" * 70)
    logger.info("JIRA EVIDENCE SUBAGENT - FINAL STATE BEFORE RETURN")
    logger.info("=" * 70)
    # logger.info(format_state_for_pprint(dict(state)))
    logger.info("=" * 70)
    return {}


# JIRA Evidence Subagent State
class JIRAEvidenceSubagentState(TypedDict):
    # Input from parent
    main_cr_data: CRData
    evidence_types: List[str]          # Will be set to ["JIRA"]
    jira_urls: List[str]               # Jira URLs extracted from evidence_link
    router_messages: Annotated[list[str], operator.add]

    # Written by nodes (internal state)
    evidence_validation_results: Annotated[List[ValidationResult], operator.add]
    jira_evidence_data: Annotated[List[JiraTicketData], operator.add]
    errors: Annotated[List[str], operator.add]


def validate_jira_evidence_node(state):
    """
    Validate Jira evidence by resolving each ticket referenced in the CR.
    Main objective: verify every referenced ticket exists and is complete.
    """

    logger.info("**** STARTING validate_jira_evidence ****")

    jira_urls = state.get('jira_urls', [])
    evidence_link = state['main_cr_data'].get('evidence_link', '')

    logger.info(f"**** Jira URLs received: {jira_urls}")
    logger.info(f"**** Jira URLs type: {type(jira_urls)}")

    if not jira_urls:
        logger.warning("No Jira URLs found in state")
        evidence_validation_result = {
            'overall_validation': "FAIL",
            'overall_score': 0,
            'conclusion': "**No Jira URLs Provided**\n\nNo Jira evidence URLs were found to validate.",
            'evidence_subagent': "JIRA",
            'peer_reviewed': "N/A",
            'peer_reviewer_name': "N/A"
        }
        return {
            'evidence_validation_results': [evidence_validation_result],
            'router_messages': [{'next_action': 'fin'}]
        }

    try:
        # Ensure jira_urls is a list and all items are strings
        if not isinstance(jira_urls, list):
            jira_urls = [jira_urls]

        # Strip whitespace from each URL
        cleaned_urls = [str(url).strip() for url in jira_urls if url]

        logger.info(f"**** Cleaned Jira URLs: {cleaned_urls}")

        if not cleaned_urls:
            logger.warning("No valid Jira URLs after cleaning")
            evidence_validation_result = {
                'overall_validation': "FAIL",
                'overall_score': 0,
                'conclusion': "**No Valid Jira URLs**\n\nNo valid Jira URLs could be extracted from the evidence.",
                'evidence_subagent': "JIRA",
                'peer_reviewed': "N/A",
                'peer_reviewer_name': "N/A"
            }
            return {
                'evidence_validation_results': [evidence_validation_result],
                'router_messages': [{'next_action': 'fin'}]
            }

        # Call the jira validation function with list of URLs
        status, explanation, jira_details = validate_jira_evidence(cleaned_urls)

        logger.info(f"Jira validation status: {status}")
        logger.info(f"Jira explanation: {explanation}")
        logger.info(f"Jira details count: {len(jira_details)}")

        # Format the conclusion in markdown
        conclusion_parts = ["## Jira Ticket Validation\n"]

        for idx, ticket in enumerate(jira_details, 1):
            issue_key = ticket.get('key', 'Unknown')
            status_name = ticket.get('status', 'Unknown')
            status_category = ticket.get('status_category', 'unknown')
            summary = ticket.get('summary', 'N/A')
            issue_type = ticket.get('issue_type', 'Unknown')
            assignee = ticket.get('assignee', 'Unassigned')
            reporter = ticket.get('reporter', 'Unknown')
            priority = ticket.get('priority', 'N/A')
            resolution = ticket.get('resolution', 'Unresolved')
            labels = ticket.get('labels', [])
            updated_at = ticket.get('updated', 'N/A')
            web_url = ticket.get('web_url', 'N/A')

            status_emoji = "✅" if status_category == "done" else "❌"
            conclusion_parts.append(
                f"{idx}. {status_emoji} **[{issue_key}]({web_url})** - {summary}  \n"
                f"      - **Status:** {status_name}  \n"
                f"      - **Type:** {issue_type}  \n"
                f"      - **Resolution:** {resolution}  \n"
                f"      - **Assignee:** {assignee}  \n"
                f"      - **Reporter:** {reporter}  \n"
                f"      - **Priority:** {priority}  \n"
                f"      - **Labels:** {', '.join(labels) if labels else 'None'}  \n"
                f"      - **Last Update:** {updated_at}  \n"
            )

        conclusion_parts.append(f"\n### Summary\n{explanation}")

        # Guard: if no ticket data was retrieved, fail immediately - do NOT use
        # all() on an empty list which is vacuously True and would produce a false PASS.
        if not jira_details:
            overall_validation = "FAIL"
            overall_score = 0
            conclusion_parts.append(
                "\n**Validation Result**: No ticket data could be retrieved from the provided URLs."
            )
        else:
            total_tickets = len(jira_details)
            complete_tickets = sum(
                1 for t in jira_details if t.get('status_category') == 'done'
            )
            incomplete_tickets = total_tickets - complete_tickets

            if incomplete_tickets == 0:
                overall_validation = "PASS"
                overall_score = 100
                conclusion_parts.append(
                    f"\n**Validation Result**: All {total_tickets} ticket(s) are in a completed status."
                )
            elif complete_tickets > 0:
                overall_validation = "PARTIAL"
                overall_score = 50
                conclusion_parts.append(
                    f"\n**Validation Result**: {complete_tickets} of {total_tickets} ticket(s) complete "
                    f"({incomplete_tickets} still open)."
                )
            else:
                overall_validation = "FAIL"
                overall_score = 0
                conclusion_parts.append(
                    f"\n**Validation Result**: None of the {total_tickets} ticket(s) are complete."
                )

        conclusion = '\n'.join(conclusion_parts)

        evidence_validation_result = {
            'overall_validation': overall_validation,
            'overall_score': overall_score,
            'conclusion': conclusion,
            'evidence_subagent': "JIRA",
        }

    except Exception as e:
        logger.error(f"Jira validation error: {e}")
        jira_details = []  # Empty list for exception case
        evidence_validation_result = {
            'overall_validation': "UNABLE TO PROCESS",
            'overall_score': 0,
            'conclusion': f"**Jira Validation Error**\n\nAn error occurred while validating Jira evidence: {str(e)}",
            'evidence_subagent': "JIRA",
        }

    return {
        'evidence_validation_results': [evidence_validation_result],
        'jira_evidence_data': jira_details,
        'router_messages': [{'next_action': 'fin'}]
    }


# Build Jira Evidence Subagent workflow
jira_evidence_workflow = StateGraph(JIRAEvidenceSubagentState)

# Add nodes
jira_evidence_workflow.add_node("validate_jira_evidence", validate_jira_evidence_node)
jira_evidence_workflow.add_node("log_subagent_state", log_subagent_state)

# Define subagent routing
jira_evidence_workflow.add_edge(START, "validate_jira_evidence")
jira_evidence_workflow.add_edge("validate_jira_evidence", "log_subagent_state")
jira_evidence_workflow.add_edge("log_subagent_state", END)

# Compile Jira Evidence Subagent
jira_evidence_subagent = jira_evidence_workflow.compile()
