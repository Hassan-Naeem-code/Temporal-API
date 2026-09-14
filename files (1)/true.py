CHUNK_SIZE = 40000
CHUNK_OVERLAP = 500

async def _extract_relevant(text: str, validation_plan: str) -> str:
    """Map a large document down to only the spans bearing on the validation plan."""
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i:i + CHUNK_SIZE])
        i += CHUNK_SIZE - CHUNK_OVERLAP

    llm = get_ally_llm()

    async def _one(idx, chunk):
        prompt = (
            "You are extracting evidence. Below is a validation plan, then a fragment "
            "of a larger evidence file.\n\n"
            f"VALIDATION PLAN:\n{validation_plan}\n\n"
            f"FRAGMENT:\n{chunk}\n\n"
            "Return ONLY lines from the fragment that bear on the validation plan "
            "(command outputs, version strings, test results, errors, timestamps). "
            "Copy them verbatim. If nothing in this fragment is relevant, return "
            "exactly: NONE"
        )
        async with _batch_sem:
            try:
                resp = await llm.ainvoke(prompt)
                out = getattr(resp, "content", str(resp)).strip()
                return "" if out.upper().startswith("NONE") else out
            except Exception as e:
                logger.error(f"extraction failed on chunk {idx}: {e}")
                return ""

    results = await asyncio.gather(*[_one(i, c) for i, c in enumerate(chunks)])
    kept = [r for r in results if r]
    logger.info(f"extraction: {len(chunks)} chunks -> {len(kept)} with content, "
                f"{len(text)} chars -> {sum(len(k) for k in kept)} chars")
    return "\n\n".join(kept)