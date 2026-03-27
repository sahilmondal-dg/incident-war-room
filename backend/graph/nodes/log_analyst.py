import asyncio
import json
from datetime import datetime, timezone

from langchain_google_vertexai import ChatVertexAI
from pydantic import ValidationError

from config import GCP_PROJECT_ID, GCP_LOCATION, GEMINI_MODEL
from graph.models import AgentFindingModel
from prompts.log_analyst import LOG_ANALYST_PROMPT

llm = ChatVertexAI(
    model=GEMINI_MODEL,
    project=GCP_PROJECT_ID,
    location=GCP_LOCATION,
    temperature=0.1,
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def timeout_finding(agent_id: str) -> dict:
    return AgentFindingModel(
        agent_id=agent_id,
        status="timeout",
        root_cause=None,
        confidence=0.0,
        justification="Agent exceeded 30s timeout",
        resolution_steps=[],
        evidence=[],
        timestamp=now_iso(),
    ).model_dump()


def error_finding(agent_id: str, reason: str) -> dict:
    return AgentFindingModel(
        agent_id=agent_id,
        status="error",
        root_cause=None,
        confidence=0.0,
        justification=reason,
        resolution_steps=[],
        evidence=[],
        timestamp=now_iso(),
    ).model_dump()


async def log_analyst_node(state: dict) -> dict:
    loop_count: int = state.get("loop_count", 0)
    runbook_result = state.get("runbook_result")

    if loop_count > 0 and runbook_result:
        rb_status = runbook_result.get("status", "unknown")
        rb_root_cause = runbook_result.get("root_cause") or "none"
        extra_context = (
            f"\nPRIOR RUNBOOK SEARCH: status={rb_status}, match={rb_root_cause}. "
            "Reconsider your diagnosis.\n"
        )
    else:
        extra_context = ""

    alert = state["alert"]
    prompt = LOG_ANALYST_PROMPT.format(
        service=alert["service_name"],
        logs=alert["log_snippet"],
        extra_context=extra_context,
    )

    try:
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=30.0)
    except asyncio.TimeoutError:
        return {"log_analysis": timeout_finding("log_analyst")}

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError as e:
        return {"log_analysis": error_finding("log_analyst", str(e))}

    try:
        result = AgentFindingModel.model_validate(parsed)
    except ValidationError as e:
        return {"log_analysis": error_finding("log_analyst", str(e))}

    result.timestamp = now_iso()
    return {"log_analysis": result.model_dump()}
