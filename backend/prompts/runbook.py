STEP_EXTRACT_PROMPT = """\
Extract all ordered resolution steps from the following runbook document.

Document:
{document_text}

Return ONLY a JSON array of strings — no preamble, no explanation, no markdown fences.
Example format: ["Step 1: ...", "Step 2: ...", "Step 3: ..."]
"""
