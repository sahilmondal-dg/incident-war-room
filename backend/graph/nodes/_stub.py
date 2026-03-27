from datetime import datetime, timezone
from graph.models import AgentFindingModel


def make_stub_node(agent_id: str, state_key: str, status: str = "success", confidence: float = 0.9):
    async def stub_node(state: dict) -> dict:
        finding = AgentFindingModel(
            agent_id=agent_id,
            status=status,
            root_cause="stub",
            confidence=confidence,
            justification="Stub node",
            resolution_steps=["stub step"],
            evidence=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        return {state_key: finding.model_dump()}

    return stub_node
