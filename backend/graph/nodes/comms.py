import asyncio
import json

from langchain_google_vertexai import ChatVertexAI

from config import GCP_PROJECT_ID, GCP_LOCATION, GEMINI_MODEL
from graph.nodes.log_analyst import now_iso, extract_json
from prompts.comms import COMMS_INITIAL_PROMPT, COMMS_REVISE_PROMPT

llm = ChatVertexAI(
    model=GEMINI_MODEL,
    project=GCP_PROJECT_ID,
    location=GCP_LOCATION,
    temperature=0.2,
)

_DRAFT_UNAVAILABLE = {
    "status_page": "Draft unavailable",
    "slack_message": "Draft unavailable",
    "revised": False,
}


async def comms_node(state: dict) -> dict:
    alert = state["alert"]

    prompt = COMMS_INITIAL_PROMPT.format(alert_json=json.dumps(alert, indent=2))

    try:
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=30.0)
        parsed = json.loads(extract_json(response.content))
        return {
            "comms_drafts": {
                "status_page": parsed["status_page"],
                "slack_message": parsed["slack_message"],
                "revised": False,
            }
        }
    except Exception:
        return {"comms_drafts": _DRAFT_UNAVAILABLE}


async def revise_comms(state: dict) -> dict:
    current_draft = state.get("comms_drafts") or {}
    root_cause = state["log_analysis"]["root_cause"]
    blast_evidence = state["blast_radius"]["evidence"][0]
    final_decision = state["final_decision"]

    current_draft_json = json.dumps(
        {
            "status_page": current_draft.get("status_page", ""),
            "slack_message": current_draft.get("slack_message", ""),
        },
        indent=2,
    )

    prompt = COMMS_REVISE_PROMPT.format(
        current_draft=current_draft_json,
        root_cause=root_cause,
        blast_summary=blast_evidence,
        final_decision=final_decision,
    )

    try:
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=30.0)
        parsed = json.loads(extract_json(response.content))
        return {
            "comms_drafts": {
                "status_page": parsed["status_page"],
                "slack_message": parsed["slack_message"],
                "revised": True,
            }
        }
    except Exception:
        return {
            "comms_drafts": {
                "status_page": current_draft.get("status_page", "Draft unavailable"),
                "slack_message": current_draft.get("slack_message", "Draft unavailable"),
                "revised": True,
            }
        }
