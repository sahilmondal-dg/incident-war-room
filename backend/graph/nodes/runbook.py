import asyncio
import json

from langchain_google_vertexai import ChatVertexAI

from config import (
    GCP_PROJECT_ID,
    GCP_LOCATION,
    GEMINI_MODEL,
    SIMILARITY_THRESHOLD,
)
from graph.models import AgentFindingModel
from graph.nodes.log_analyst import now_iso, timeout_finding, error_finding, extract_json
from prompts.runbook import STEP_EXTRACT_PROMPT
from tools.vectorstore import get_vectorstore

llm = ChatVertexAI(
    model=GEMINI_MODEL,
    project=GCP_PROJECT_ID,
    location=GCP_LOCATION,
    temperature=0.1,
)


def no_match_finding(reason: str) -> dict:
    return AgentFindingModel(
        agent_id="runbook",
        status="no_match",
        root_cause=None,
        confidence=0.0,
        justification=reason,
        resolution_steps=[],
        evidence=[],
        timestamp=now_iso(),
    ).model_dump()


async def runbook_node(state: dict) -> dict:
    log = state.get("log_analysis")

    if log is None or log["status"] != "success":
        return {"runbook_result": no_match_finding("Log analysis not successful")}

    query = f"{log['root_cause']} {' '.join(log['evidence'][:3])}"

    vectorstore = get_vectorstore()
    results = vectorstore.similarity_search_with_score(query, k=3)

    if not results or results[0][1] > SIMILARITY_THRESHOLD:
        return {"runbook_result": no_match_finding(f"No match within distance {SIMILARITY_THRESHOLD}")}

    doc, score = results[0]

    prompt = STEP_EXTRACT_PROMPT.format(document_text=doc.page_content)

    try:
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=30.0)
    except asyncio.TimeoutError:
        return {"runbook_result": timeout_finding("runbook")}

    try:
        steps = json.loads(extract_json(response.content))
        if not isinstance(steps, list):
            raise ValueError("Expected a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        return {"runbook_result": error_finding("runbook", str(e))}

    # Convert L2 distance to confidence: halve the distance before inverting so
    # good matches (score ~0.4-0.6) map to 70-80% rather than 40-60%.
    similarity = max(0.0, 1.0 - float(score) / 2.0)
    finding = AgentFindingModel(
        agent_id="runbook",
        status="success",
        root_cause=doc.metadata.get("title"),
        confidence=similarity,
        justification=f"Matched runbook at L2={score:.3f} (confidence {similarity:.2f})",
        resolution_steps=steps,
        evidence=[doc.page_content[:500]],
        timestamp=now_iso(),
    )

    return {"runbook_result": finding.model_dump()}
