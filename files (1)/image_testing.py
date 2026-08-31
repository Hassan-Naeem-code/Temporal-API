
import asyncio


async def process_text_batch(batch_text, batch_number, total_batches, validation_plan, testing_evidence_field):
    """Process a chunk of extracted text to extract brief findings.

    Args:
        batch_text: Text content for this chunk
        batch_number: Current batch number (1-indexed)
        total_batches: Total number of batches
        validation_plan: Validation plan text
        testing_evidence_field: Testing evidence statement

    Returns:
        BatchValidationFindings object with brief findings from this batch
    """
    logger.info(f'**** Processing text batch {batch_number}/{total_batches} with {len(batch_text)} chars')

    llm = get_ally_llm()

    intro_text = (
        f"Please analyze this section of a document (batch {batch_number} of {total_batches}) "
        f"and identify any testing evidence relevant to the validation plan. "
        f"Provide a brief summary of what you find."
    )
    user_content = [{"type": "text", "text": intro_text}, {"type": "text", "text": batch_text}]

    messages = [{
        "role": "system",
        "content": [{
            "type": "text",
            "text": f"""You are analyzing a subset of testing evidence text for a change request.

Your task is to quickly scan this text and identify relevant testing evidence based on the validation plan.

VALIDATION PLAN:
{validation_plan}

TESTING EVIDENCE STATEMENT:
{testing_evidence_field}

INSTRUCTIONS:
1. Look for test execution records, results, logs, configurations, or data
2. Identify specific evidence of functional testing or performance testing
3. Note any test results, environment indicators, timestamps, or pass/fail statuses
4. Note any approvals, sign-offs, or reviewer names
5. Be concise - this is a preliminary scan to extract key findings
6. If this section contains nothing relevant, say so plainly rather than inventing detail

RESPONSE FORMAT:
 - "has_relevant_evidence": true if you find testing-related content
 - "evidence_summary": 2-3 sentences describing what evidence you found
 - "key_findings": List 3-5 specific observations (e.g., "Test passed in DEV environment", "Performance metrics show 200ms response time")"""
        }]
    }, {
        "role": "user",
        "content": user_content
    }]

    try:
        structured_llm = llm.with_structured_output(BatchValidationFindings)
        return await structured_llm.ainvoke(messages)
    except Exception as e:
        logger.error(f'**** Text batch {batch_number}/{total_batches} failed: {e}')
        return BatchValidationFindings(
            has_relevant_evidence=False,
            evidence_summary=f"Batch {batch_number} could not be analyzed: {e}",
            key_findings=[],
        )


async def process_large_text(text_content, validation_plan, testing_evidence_field, evidence_type_label="TEXT"):
    """Chunk oversized text and map-reduce it into a findings summary.

    Returns (findings_summary, was_truncated). Callers MUST surface
    was_truncated - a verdict built on a partially read document has to
    say so.
    """
    text_batches = [
        text_content[i:i + MAX_TEXT_CHUNK]
        for i in range(0, len(text_content), MAX_TEXT_CHUNK)
    ]

    was_truncated = False
    if len(text_batches) > MAX_TEXT_BATCHES:
        logger.warning(
            f'**** Text has {len(text_batches)} batches, capping at {MAX_TEXT_BATCHES}'
        )
        text_batches = text_batches[:MAX_TEXT_BATCHES]
        was_truncated = True

    total_batches = len(text_batches)
    logger.info(f'**** Split {len(text_content)} chars into {total_batches} batches')

    # Concurrent, unlike the image path which runs serially. 40 sequential
    # LLM calls would take minutes; this keeps it to roughly total/4.
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_TEXT_BATCHES)

    async def run_batch(batch_num, batch_text):
        async with semaphore:
            return await process_text_batch(
                batch_text,
                batch_num,
                total_batches,
                validation_plan,
                testing_evidence_field,
            )

    all_batch_findings = await asyncio.gather(*[
        run_batch(num, chunk) for num, chunk in enumerate(text_batches, 1)
    ])

    # Aggregate findings from all batches
    findings_summary = f"\n\n=== {evidence_type_label} FINDINGS FROM TEXT ANALYSIS ===\n"
    findings_summary += f"Analyzed {len(text_content)} characters across {total_batches} batches.\n\n"

    if was_truncated:
        findings_summary += (
            f"WARNING: document exceeded the processing limit. Only the first "
            f"{MAX_TEXT_BATCHES * MAX_TEXT_CHUNK} characters were analyzed.\n\n"
        )

    relevant_count = 0
    for idx, findings in enumerate(all_batch_findings, 1):
        if findings.has_relevant_evidence:
            relevant_count += 1
            findings_summary += f"**Batch {idx}:** {findings.evidence_summary}\n"
            if findings.key_findings:
                findings_summary += "Key findings:\n"
                for finding in findings.key_findings:
                    findings_summary += f"   - {finding}\n"
            findings_summary += "\n"

    if relevant_count == 0:
        findings_summary += "No testing evidence was found in any section of this document.\n"

    logger.info(f'**** {relevant_count}/{total_batches} text batches contained relevant evidence')

    return findings_summary, was_truncated
