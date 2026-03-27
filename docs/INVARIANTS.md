# INVARIANTS.md — Incident War Room

> Invariants are non-negotiable constraints that must hold true at all times across the entire system.  
> A violation of any invariant is a **critical bug**, regardless of whether the output looks correct.  
> These are the ground rules that all agent nodes, routing functions, and API handlers must respect.

**Legend**
- `ADDED` — not in the original submission; introduced after architecture review
- `MODIFIED` — original invariant updated for correctness or precision
- `UNCHANGED` — original invariant accepted as written

---

## 1. State & Data Invariants

### INV-001 — Single Source of Truth `UNCHANGED`
All decisions must be derived exclusively from `IncidentState`. No agent, node, or routing function may use data sourced from outside the state object (e.g., module-level globals, external caches, in-memory singletons) to influence a routing or resolution decision.

### INV-002 — Typed State Only `UNCHANGED`
All state values must conform to their declared schemas: `IncidentState`, `AgentFinding`, `CommsDraft`, and `AlertPayload`. No raw dicts, bare strings, or `Any`-typed fields may be written to state.

### INV-003 — No Free-form Data `UNCHANGED`
No agent or system component may emit unstructured or free-text outputs as a state value. All LLM responses must be parsed and validated against the target schema before being written to state. An LLM response that fails schema validation is treated as `status: "error"`, not silently truncated or stored raw.

### INV-004 — Agent Ownership Boundaries `UNCHANGED`
Each agent writes only to its designated state key:

| Agent | Owned Key |
|-------|-----------|
| `log_analyst` | `state["log_analysis"]` |
| `runbook` | `state["runbook_result"]` |
| `blast_radius` | `state["blast_radius"]` |
| `comms` | `state["comms_drafts"]` |
| `coordinator_arbiter` | `conflict_detected`, `conflict_reason`, `loop_count`, `final_decision`, `incident_brief`, `resolution_plan` |

### INV-005 — No Cross-Agent Mutation `UNCHANGED`
Agents must never overwrite or modify the output of another agent. LangGraph's partial-return merge pattern enforces this structurally — no agent node should return a key it does not own.

### INV-006 — Schema Validation Before State Write `ADDED`
Every agent output must be validated against its Pydantic schema before being merged into `IncidentState`. If Vertex AI returns a response that fails validation (malformed JSON, missing required fields, out-of-range values), the node must catch the error and write a well-formed `AgentFinding` with `status: "error"` rather than propagating the invalid data.

```python
# Pattern every agent node must follow
try:
    result = AgentFindingModel.model_validate(raw_llm_output)
except ValidationError:
    result = AgentFinding(agent_id=AGENT_ID, status="error",
                          confidence=0.0, justification="Schema validation failed", ...)
return {STATE_KEY: result}
```

---

## 2. Execution & Orchestration Invariants

### INV-007 — Fixed Execution Order `MODIFIED`
*(was INV-006)*  
The execution order must always be:

```
parse_alert → log_analyst → [runbook ‖ blast_radius ‖ comms] → coordinator_arbiter → (auto_resolve | escalate)
```

No node may execute out of this sequence. The `log_analyst` pre-step is mandatory before the parallel fan-out regardless of severity level or alert content.

### INV-008 — Log Analyst Precedence `UNCHANGED`
*(was INV-007)*  
The `runbook` agent must not begin execution before `log_analyst` has written a valid `AgentFinding` to `state["log_analysis"]`. The `runbook` agent's query is derived from `state["log_analysis"]["root_cause"]` — executing it before this value exists produces meaningless semantic search results.

### INV-009 — Parallel Fan-out Guarantee `UNCHANGED`
*(was INV-008)*  
`runbook`, `blast_radius`, and `comms` must execute concurrently using LangGraph's `Send` primitive. No sequential chaining between these three is permitted. A failure or timeout in one must not delay the start or completion of the others.

### INV-010 — No Direct Agent Communication `UNCHANGED`
*(was INV-009)*  
Agents must communicate only via shared `IncidentState`. No agent may call another agent's function directly, import another agent's module, or read from a shared in-process queue. All inter-agent data flow is mediated by the LangGraph state graph.

### INV-011 — No Credentials in Code `ADDED`
No agent node, utility function, or configuration file may contain hardcoded API keys, service account JSON, or authentication tokens. All GCP authentication must use Application Default Credentials (ADC) exclusively. Any file committed to version control that contains a credential string is an unconditional violation.

---

## 3. Agent Output Contract Invariants

### INV-012 — Structured Output Enforcement `MODIFIED`
*(was INV-010)*  
Every agent node must return a valid `AgentFinding` for its state key. This applies without exception — including timeout paths, error paths, and cases where the LLM returns an unexpected response. There is no path through any agent node that writes `None`, an empty dict, or a raw string to its owned state key.

### INV-013 — Confidence Bounds `UNCHANGED`
*(was INV-011)*  
`confidence` must always be a float in `[0.0, 1.0]` inclusive. A confidence of exactly `0.0` is valid and required when `status == "no_match"` or `status == "error"`. The coordinator must reject (treat as error) any finding where `confidence` is outside this range.

### INV-014 — Valid Status Enum `UNCHANGED`
*(was INV-012)*  
`status` must be exactly one of: `"success"` | `"no_match"` | `"timeout"` | `"error"`. No other string is valid. The LLM prompt for each agent must constrain this field to the enum explicitly.

### INV-015 — Mandatory Justification `UNCHANGED`
*(was INV-013)*  
Every `AgentFinding` must include a non-empty `justification` string. This field must explain *why* the agent assigned the specific confidence score — not merely restate the root cause. An empty string or whitespace-only string is invalid.

### INV-016 — Timestamp Required `UNCHANGED`
*(was INV-014)*  
Every `AgentFinding` must include a `timestamp` in ISO 8601 format, set to when the agent completed its LLM call. The timestamp is set by the agent node in Python (`datetime.utcnow().isoformat()`), not by the LLM.

---

## 4. Coordinator & Decision Invariants

### INV-017 — Single Decision Authority `UNCHANGED`
*(was INV-015)*  
Only `coordinator_arbiter_node` may set `final_decision`, `conflict_detected`, or `incident_brief`. No agent node, routing function, or API handler may write to these fields.

### INV-018 — Valid Final Decision `UNCHANGED`
*(was INV-016)*  
`final_decision` must be exactly one of: `"auto_resolve"` | `"escalate"` | `"loop"`. The value `"loop"` is a transient intermediate state — it must never appear in the final output delivered to an engineer or status page. By the time the graph reaches `END`, `final_decision` must be either `"auto_resolve"` or `"escalate"`.

### INV-019 — Terminal State Guarantee `UNCHANGED`
*(was INV-017)*  
Every incident graph execution must terminate in either `auto_resolve` or `escalate`. The graph must never deadlock, hang indefinitely, or terminate without setting `final_decision`. The loop cap (INV-026) and agent timeout (INV-029) together guarantee this.

### INV-020 — Low-confidence Escalation Without Conflict `ADDED`
If no conflict is detected but `mean(confidence scores) < AUTO_RESOLVE_THRESHOLD (0.75)`, the coordinator must escalate. This is a distinct decision path from conflict-triggered escalation and must be explicitly modelled — it is not a fallback or an error condition.

```python
# Explicit path — not an implicit else
if not conflict and mean_conf < AUTO_RESOLVE_THRESHOLD:
    final_decision = "escalate"
    # incident_brief must still be fully assembled
```

---

## 5. Conflict Detection Invariants

### INV-021 — Deterministic Rule Order `UNCHANGED`
*(was INV-018)*  
Conflict rules must be evaluated in a fixed, documented order. First matching rule wins — no rule below a triggered rule is evaluated. The canonical order is:

1. Log confidence ≥ 0.7 AND runbook `no_match`
2. Confidence spread between log and blast radius > 0.4
3. Any agent `error` or `timeout` on P0 incident *(see INV-022)*
4. Mean confidence across all agents < 0.5

### INV-022 — Conflict Transparency `UNCHANGED`
*(was INV-019)*  
If conflict is detected, `conflict_detected` must be set to `True` and `conflict_reason` must be set to a non-empty string naming the specific rule that triggered. It must not be a generic message — it must identify the agent(s) involved and the specific values that triggered the rule.

```python
# Correct
"Log Analyst confident (0.82) in 'oom' but Runbook Agent returned no_match."

# Wrong — too generic
"Conflict detected between agents."
```

### INV-023 — Log vs Runbook Conflict Rule `UNCHANGED`
*(was INV-020)*  
If `log_analysis.confidence >= 0.7` AND `runbook_result.status == "no_match"`, conflict must be triggered. This rule may not be suppressed by any configuration flag or runtime condition.

### INV-024 — P0 Error/Timeout Rule `MODIFIED`
*(was INV-021 — expanded to include timeout)*  
On P0 incidents, if any agent returns `status == "error"` **or** `status == "timeout"`, conflict must be triggered. A timed-out agent on P0 is treated identically to an errored agent — the absence of a finding is itself an unsafe signal. This check occurs in the coordinator *before* calling `detect_conflict()` on the findings.

```python
if state["alert"]["severity"] == "P0":
    if any(f["status"] in ("error", "timeout")
           for f in [log, rb, br] if f is not None):
        return conflict_result("P0 incident with agent error/timeout.")
```

---

## 6. Loop & Retry Invariants

### INV-025 — Loop Cap Enforcement `UNCHANGED`
*(was INV-022)*  
`loop_count` must never exceed `MAX_LOOPS` (default: 2). The routing function must check this bound before returning `"log_analyst"` as the next node. `loop_count` is incremented only by `coordinator_arbiter_node` and only when `final_decision == "loop"`.

### INV-026 — Loop Entry Condition `UNCHANGED`
*(was INV-023)*  
A loop may only be entered when both conditions hold simultaneously:
1. `conflict_detected == True`
2. `loop_count < MAX_LOOPS`

Neither condition alone is sufficient. A non-conflicted low-confidence result (covered by INV-020) must escalate directly — it must not trigger a loop.

### INV-027 — Forced Escalation After Max Loops `UNCHANGED`
*(was INV-024)*  
When `loop_count >= MAX_LOOPS` and a conflict is still detected, the coordinator must set `final_decision = "escalate"` unconditionally. No additional conflict evaluation or confidence check is performed at this point.

### INV-028 — Context Enrichment Per Loop `MODIFIED`
*(was INV-025 — made concrete)*  
Each loop pass must inject new context that was not present in the previous pass. Specifically: the `log_analyst_node` prompt must include the prior `runbook_result` (even if `status == "no_match"`) as explicit context so the LLM can reconsider its diagnosis knowing the standard runbook did not match. A loop that submits an identical prompt to the LLM as the previous pass is a violation of this invariant.

```python
# On loop_count > 0, this context block must be non-empty
runbook_context = state.get("runbook_result") if state.get("loop_count", 0) > 0 else None
# runbook_context must be included in the prompt even if status == "no_match"
```

---

## 7. Timing & Performance Invariants

### INV-029 — Agent Timeout Handling `UNCHANGED`
*(was INV-027)*  
Any agent node that does not complete within 30 seconds must be interrupted and must return an `AgentFinding` with `status: "timeout"`, `confidence: 0.0`, and a `justification` stating the timeout duration. The node must not raise an unhandled exception — it must return a valid finding.

```python
async def log_analyst_node(state):
    try:
        result = await asyncio.wait_for(run_llm_call(state), timeout=30.0)
    except asyncio.TimeoutError:
        result = AgentFinding(status="timeout", confidence=0.0,
                              justification="Agent exceeded 30s timeout.", ...)
    return {"log_analysis": result}
```

### INV-030 — Non-blocking Execution `UNCHANGED`
*(was INV-028)*  
A timeout or error in one parallel agent must not block or cancel the other parallel agents. LangGraph's parallel `Send` execution handles this structurally — no `asyncio.gather` with `return_exceptions=False` or similar patterns that propagate exceptions across parallel branches.

### INV-031 — End-to-End SLA `MODIFIED`
*(was INV-026 — repositioned after timeout invariants for logical flow)*  
The entire incident lifecycle — from alert ingestion to `final_decision` being set — must complete within 60 seconds under normal operating conditions. This SLA is validated against the three demo scenarios. The combination of the 30s agent timeout (INV-029) and `MAX_LOOPS = 2` makes a worst-case bound of approximately 90s theoretically possible; the 60s SLA applies to non-degenerate executions only.

---

## 8. Resolution Logic Invariants

### INV-032 — Auto-resolve Condition `MODIFIED`
*(was INV-029 — strengthened with runbook dependency)*  
Auto-resolve is permitted only when **all** of the following hold simultaneously:
1. `conflict_detected == False`
2. `mean(log_analysis.confidence, runbook_result.confidence, blast_radius.confidence) >= 0.75`
3. `runbook_result.status == "success"`
4. `len(runbook_result.resolution_steps) > 0`

Conditions 3 and 4 are additions to the original. Auto-resolve without a valid runbook match would deliver an escalation brief with no actionable steps — which is operationally indistinguishable from an escalation. The coordinator must check all four conditions.

### INV-033 — Escalation Completeness `UNCHANGED`
*(was INV-030)*  
Every escalation must produce a fully assembled `incident_brief` containing: the triggering alert, each agent's finding with confidence and justification, the conflict rule that fired (if applicable), `loop_count`, blast radius summary, and the comms draft. An escalation with a `None` or empty `incident_brief` is invalid.

### INV-034 — Runbook Dependency for Auto-resolve `MODIFIED`
*(was INV-031 — merged with INV-032 above; retained as standalone for emphasis)*  
`resolution_plan` (the ordered step-by-step fix delivered on auto-resolve) must be derived exclusively from `runbook_result.resolution_steps`. It must not be synthesised by the coordinator's LLM call. If `resolution_steps` is empty, auto-resolve is not permitted regardless of confidence scores.

---

## 9. Data & Input Invariants

### INV-035 — Payload Validation `UNCHANGED`
*(was INV-032)*  
All incoming alert payloads must be validated against the `AlertPayload` schema before the graph is invoked. Required fields: `alert_id`, `service_name`, `severity`, `error_type`, `log_snippet`, `timestamp`. A payload missing any required field must be rejected with HTTP 422 at the API layer — the graph must never receive an incomplete alert.

### INV-036 — Deduplication Rule `MODIFIED`
*(was INV-033 — deduplication key made explicit)*  
Duplicate alerts within a 5-minute rolling window must be suppressed. Deduplication is keyed on the composite `(service_name, error_type)` tuple — not on `alert_id`, which is unique per alert even for the same underlying incident. A deduplicated alert must return the existing `incident_id` for the active incident, not create a new graph execution.

### INV-037 — Severity Routing Rule `UNCHANGED`
*(was INV-034)*  
Alert severity determines pipeline scope:
- `P0` / `P1` → full pipeline: all four agents + coordinator
- `P2` / `P3` → limited pipeline: `log_analyst` only; findings returned without coordinator arbitration

The limited pipeline for P2/P3 must still produce a valid `AgentFinding` — it is not a no-op.

---

## 10. Communication Invariants

### INV-038 — Two-pass Comms `UNCHANGED`
*(was INV-035)*  
The `comms` agent must produce two drafts:
1. **First pass** (during parallel fan-out): drafted from alert metadata only — `service_name`, `severity`, `error_type`, and `timestamp`. No findings from other agents are available or used at this point.
2. **Second pass** (called by `coordinator_arbiter` after synthesis): revised to incorporate confirmed `root_cause`, `blast_radius` summary, and `final_decision`. The revised draft must replace the first-pass draft in state.

### INV-039 — Comms Agent Input Isolation `ADDED`
The `comms` agent's first pass must receive **only** `state["alert"]` — not the full `IncidentState`. This is enforced by the `Send` primitive's input scoping:

```python
Send("comms", {"alert": state["alert"]})  # correct — alert only
Send("comms", state)                       # wrong — exposes other agents' outputs
```

Passing full state to the comms agent on first pass could cause it to hallucinate findings from keys that are not yet populated.

### INV-040 — Non-blocking Communication `UNCHANGED`
*(was INV-036)*  
The `comms` agent must not be on the critical path of the routing decision. `coordinator_arbiter_node` must not wait for comms revision before computing `final_decision`. The revision call is part of output assembly, not decision logic.

---

## 11. Safety & Reliability Invariants

### INV-041 — No Silent Failures `UNCHANGED`
*(was INV-037)*  
All failures must be explicitly surfaced in state. An agent that encounters an exception must not swallow it silently — it must write `status: "error"` with a `justification` describing the failure. The coordinator must then treat this as a signal, not as absence of data.

### INV-042 — Graceful Degradation `UNCHANGED`
*(was INV-038)*  
The coordinator must be capable of making a routing decision even if one or more parallel agents fail or timeout. The system must never deadlock waiting for an agent that has already been marked `timeout` or `error`. Missing agent outputs are treated as low-confidence findings, not as blocking conditions.

---

## 12. System Boundary Invariants

### INV-043 — No External Side Effects `UNCHANGED`
*(was INV-039)*  
The system must not execute real remediation commands, call live production APIs, post to real Slack workspaces, or trigger real PagerDuty pages. All external integrations (metrics API, paging endpoint, status page) must target mock endpoints or fixture files. This invariant applies equally to demo and test executions.

### INV-044 — Deterministic Demo Behaviour `MODIFIED`
*(was INV-040 — mechanism made explicit)*  
Pre-built demo scenarios must produce consistent, predictable outcomes across repeated executions. Determinism is achieved through two mechanisms:
1. **Fixture-based inputs** — each scenario uses a fixed JSON alert payload from `fixtures/alerts/`
2. **Seeded vectorstore** — ChromaDB is populated from the same set of 15 runbook documents at every startup

The LLM itself is non-deterministic (`temperature=0.1`, not 0). Demo scenarios must not rely on exact LLM output text — only on the structured fields (`status`, `confidence` within a tolerance band, `final_decision`) for correctness assertions.

---

## Change Log

| INV ID | Original ID | Status | Change Summary |
|--------|-------------|--------|----------------|
| INV-001 to INV-005 | INV-001 to INV-005 | UNCHANGED | — |
| INV-006 | — | ADDED | Schema validation before state write |
| INV-007 to INV-010 | INV-006 to INV-009 | UNCHANGED | Renumbered |
| INV-011 | — | ADDED | No credentials in code (ADC enforcement) |
| INV-012 to INV-016 | INV-010 to INV-014 | UNCHANGED | Renumbered |
| INV-017 to INV-019 | INV-015 to INV-017 | UNCHANGED | Renumbered |
| INV-020 | — | ADDED | Low-confidence escalation path without conflict |
| INV-021 to INV-023 | INV-018 to INV-020 | UNCHANGED | Renumbered |
| INV-024 | INV-021 | MODIFIED | Expanded P0 rule to include `timeout` in addition to `error` |
| INV-025 to INV-027 | INV-022 to INV-024 | UNCHANGED | Renumbered |
| INV-028 | INV-025 | MODIFIED | Concrete specification of what "new context" means per loop |
| INV-029 to INV-030 | INV-027 to INV-028 | UNCHANGED | Renumbered |
| INV-031 | INV-026 | MODIFIED | Repositioned; added worst-case bound note |
| INV-032 | INV-029 | MODIFIED | Added `runbook.status == success` and non-empty `resolution_steps` as required conditions |
| INV-033 | INV-030 | UNCHANGED | Renumbered |
| INV-034 | INV-031 | MODIFIED | Clarified: resolution steps must come from runbook, not coordinator LLM synthesis |
| INV-035 to INV-037 | INV-032 to INV-034 | UNCHANGED | Renumbered; INV-036 dedup key made explicit |
| INV-038 to INV-040 | INV-035 to INV-036 | UNCHANGED | Renumbered |
| INV-039 | — | ADDED | Comms agent input isolation via Send scoping |
| INV-041 to INV-043 | INV-037 to INV-039 | UNCHANGED | Renumbered |
| INV-044 | INV-040 | MODIFIED | Determinism mechanism made explicit; note that LLM temp=0.1 not 0 |

---

*44 invariants total — 30 unchanged, 7 modified, 7 added*  
*Last reviewed: March 2026 against ARCHITECTURE.md v1.0 (Architecture A — Centralised Supervisor, Vertex AI)*
