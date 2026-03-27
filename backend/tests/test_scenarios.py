"""
End-to-end scenario tests using real Vertex AI calls.
Requires GCP ADC and a seeded vectorstore.
Run with: python -m pytest tests/test_scenarios.py --slow -v
"""
import json
from pathlib import Path

import pytest

from graph.graph import graph
from graph.state import IncidentState

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "alerts"


def load_fixture(name: str) -> IncidentState:
    """Load an alert fixture and return a fully-initialised IncidentState dict."""
    path = _FIXTURES_DIR / f"{name}.json"
    with open(path, "r", encoding="utf-8") as f:
        alert = json.load(f)
    return IncidentState(
        alert=alert,
        log_analysis=None,
        runbook_result=None,
        blast_radius=None,
        comms_drafts=None,
        conflict_detected=False,
        conflict_reason=None,
        loop_count=0,
        final_decision=None,
        incident_brief=None,
        resolution_plan=None,
    )


# ---------------------------------------------------------------------------
# Scenario A — DB connection pool timeout → expected: auto_resolve
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.asyncio
async def test_scenario_a():
    """
    Scenario A: payments-api connection_pool_timeout.
    Log analyst should detect db_timeout with high confidence.
    Runbook should match db_pool_recovery with score >= SIMILARITY_THRESHOLD.
    Expected outcome: auto_resolve with resolution_plan set.
    """
    state = load_fixture("scenario_a_db_pool")
    result = await graph.ainvoke(state)

    assert result["final_decision"] == "auto_resolve", (
        f"Expected auto_resolve, got {result['final_decision']}. "
        f"conflict_reason={result.get('conflict_reason')}, "
        f"loop_count={result.get('loop_count')}, "
        f"log_confidence={result.get('log_analysis', {}).get('confidence')}, "
        f"runbook_status={result.get('runbook_result', {}).get('status')}"
    )
    assert result["loop_count"] == 0, (
        f"Expected loop_count=0, got {result['loop_count']}"
    )
    assert result["resolution_plan"] is not None, "resolution_plan must be set on auto_resolve"


# ---------------------------------------------------------------------------
# Scenario B — OOM (no runbook match) → expected: escalate with conflict
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.asyncio
async def test_scenario_b():
    """
    Scenario B: user-service out_of_memory.
    No OOM runbook exists in the vectorstore (intentional — see CLAUDE.md).
    Log analyst detects OOM with confidence >= 0.7.
    Rule 1 fires: log confident + runbook no_match → conflict detected.
    After MAX_LOOPS exhausted, final outcome is escalate.
    """
    state = load_fixture("scenario_b_oom")
    result = await graph.ainvoke(state)

    assert result["final_decision"] == "escalate", (
        f"Expected escalate, got {result['final_decision']}. "
        f"conflict_detected={result.get('conflict_detected')}, "
        f"runbook_status={result.get('runbook_result', {}).get('status')}, "
        f"log_confidence={result.get('log_analysis', {}).get('confidence')}"
    )
    assert result["conflict_detected"] is True, (
        "Expected conflict_detected=True for scenario_b (no runbook match for OOM)"
    )
    assert result["conflict_reason"] is not None and len(result["conflict_reason"]) > 0, (
        "conflict_reason must be a non-empty string when conflict_detected=True"
    )


# ---------------------------------------------------------------------------
# All three scenarios — verify no scenario terminates with "loop"
# ---------------------------------------------------------------------------

@pytest.mark.slow
@pytest.mark.asyncio
async def test_all_no_loop_terminal():
    """
    INV-026: 'loop' must never appear in terminal state.
    Runs all three demo scenarios and asserts final_decision is never 'loop'.
    """
    scenarios = ["scenario_a_db_pool", "scenario_b_oom", "scenario_c_auth_dns"]
    for scenario in scenarios:
        state = load_fixture(scenario)
        result = await graph.ainvoke(state)
        assert result["final_decision"] != "loop", (
            f"Scenario '{scenario}' terminated with final_decision='loop' — "
            "this violates INV-026. loop_count={result.get('loop_count')}"
        )
        assert result["final_decision"] in ("auto_resolve", "escalate"), (
            f"Scenario '{scenario}' has unexpected final_decision={result['final_decision']!r}"
        )
