import asyncio
import json
import os

from langchain_google_vertexai import ChatVertexAI
from pydantic import ValidationError

from config import GCP_PROJECT_ID, GCP_LOCATION, GEMINI_MODEL
from graph.models import AgentFindingModel
from graph.nodes.log_analyst import now_iso, timeout_finding, error_finding
from prompts.blast_radius import BLAST_RADIUS_PROMPT

llm = ChatVertexAI(
    model=GEMINI_MODEL,
    project=GCP_PROJECT_ID,
    location=GCP_LOCATION,
    temperature=0.1,
)

_DEFAULT_METRICS = {
    "error_rate": 0.0,
    "latency_p99_ms": 0,
    "active_users": 0,
    "requests_per_second": 0,
    "revenue_per_minute": 0.0,
    "regions": [],
    "downstream_services": [],
}

_METRICS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "fixtures", "metrics", "metrics_mock.json",
)


def load_metrics(service_name: str) -> dict:
    try:
        with open(_METRICS_PATH, "r") as f:
            data = json.load(f)
        return data.get(service_name, _DEFAULT_METRICS)
    except (FileNotFoundError, json.JSONDecodeError):
        return _DEFAULT_METRICS


async def blast_radius_node(state: dict) -> dict:
    alert = state["alert"]
    metrics = load_metrics(alert["service_name"])

    prompt = BLAST_RADIUS_PROMPT.format(
        service_name=alert["service_name"],
        metrics_json=json.dumps(metrics, indent=2),
    )

    try:
        response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=30.0)
    except asyncio.TimeoutError:
        return {"blast_radius": timeout_finding("blast_radius")}

    try:
        parsed = json.loads(response.content)
    except json.JSONDecodeError as e:
        return {"blast_radius": error_finding("blast_radius", str(e))}

    try:
        result = AgentFindingModel.model_validate(parsed)
    except ValidationError as e:
        return {"blast_radius": error_finding("blast_radius", str(e))}

    result.timestamp = now_iso()
    return {"blast_radius": result.model_dump()}
