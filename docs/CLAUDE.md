# Claude.md — v1.0 · FROZEN · March 2026

---

## 1. System Intent

Incident War Room is a multi-agent AI system that automates the first-response investigation phase of production incidents. Four specialist agents (Log Analyst, Runbook, Blast Radius, Comms) run in parallel under a central LangGraph Coordinator that detects conflicts between agent findings, loops for re-investigation when needed, and delivers either an auto-resolved fix plan or a fully assembled escalation brief. It does not execute remediation commands, call live production APIs, or post to real external services.

Success looks like: a demo alert fires, four agent tiles animate simultaneously on screen, a conflict is detected and surfaced with a reason, and the system reaches a terminal decision (`auto_resolve` or `escalate`) within 60 seconds — all without a human touching a terminal.

---

## 2. Hard Invariants

INVARIANT: All decisions must be derived exclusively from `IncidentState`. No globals, caches, or singletons may influence routing. This is never negotiable.

INVARIANT: All state values must conform to `IncidentState`, `AgentFinding`, `CommsDraft`, `AlertPayload` TypedDicts. No raw dicts, bare strings, or `Any`-typed fields may be written to state. This is never negotiable.

INVARIANT: No agent or system component may emit unstructured output as a state value. LLM responses failing schema validation must be written as `status:"error"` findings — never stored raw. This is never negotiable.

INVARIANT: Each agent writes only to its designated state key. `log_analyst`→`log_analysis`, `runbook`→`runbook_result`, `blast_radius`→`blast_radius`, `comms`→`comms_drafts`, `coordinator_arbiter`→`conflict_detected/conflict_reason/loop_count/final_decision/incident_brief/resolution_plan`. This is never negotiable.

INVARIANT: Agents must never overwrite or modify another agent's state key. This is never negotiable.

INVARIANT: Every agent output must be validated against its Pydantic schema before being merged into `IncidentState`. Validation failure → `status:"error"` finding. This is never negotiable.

INVARIANT: Execution order must always be: `parse_alert → log_analyst → [runbook ‖ blast_radius ‖ comms] → coordinator_arbiter → (auto_resolve|escalate)`. No deviation. This is never negotiable.

INVARIANT: `runbook` must not execute before `log_analyst` has written a valid `AgentFinding` to `state["log_analysis"]`. This is never negotiable.

INVARIANT: `runbook`, `blast_radius`, and `comms` must execute concurrently via LangGraph `Send`. No sequential chaining between these three. This is never negotiable.

INVARIANT: Agents must communicate only via shared `IncidentState`. No agent may call another agent's function directly. This is never negotiable.

INVARIANT: No agent node, utility function, config file, or Dockerfile may contain hardcoded API keys, service account JSON, or authentication tokens. All GCP auth uses ADC exclusively. This is never negotiable.

INVARIANT: Every agent node must return a valid `AgentFinding` dict on all paths — including timeout, error, and validation failure. No path through any agent node may return `None`, `{}`, or a raw string. This is never negotiable.

INVARIANT: `confidence` must be a float in `[0.0, 1.0]` inclusive. This is never negotiable.

INVARIANT: `status` must be exactly one of `"success"` | `"no_match"` | `"timeout"` | `"error"`. This is never negotiable.

INVARIANT: Every `AgentFinding` must include a non-empty, non-whitespace `justification` string. This is never negotiable.

INVARIANT: Every `AgentFinding` must include an ISO 8601 `timestamp` set by Python, not by the LLM. This is never negotiable.

INVARIANT: Only `coordinator_arbiter_node` may set `final_decision`, `conflict_detected`, or `incident_brief`. This is never negotiable.

INVARIANT: `final_decision` must be exactly one of `"auto_resolve"` | `"escalate"` | `"loop"`. `"loop"` is transient — it must never appear in the terminal state at `END`. This is never negotiable.

INVARIANT: Every incident graph execution must terminate in `auto_resolve` or `escalate`. No deadlocks, no hanging, no termination without `final_decision` set. This is never negotiable.

INVARIANT: If no conflict detected and `mean(confidences) < 0.75`, coordinator must escalate. This path is explicit, not a fallback. This is never negotiable.

INVARIANT: Conflict rules must be evaluated in fixed order, first match wins: (1) log conf ≥ 0.7 AND runbook `no_match`, (2) confidence spread > 0.4, (3) P0 + any agent `error`/`timeout`, (4) mean conf < 0.5. This is never negotiable.

INVARIANT: If conflict detected, `conflict_detected=True` and `conflict_reason` must be set to a non-empty string naming the specific rule and agents involved. This is never negotiable.

INVARIANT: If `log.confidence >= 0.7` AND `runbook.status == "no_match"`, conflict must trigger. This rule may not be suppressed. This is never negotiable.

INVARIANT: On P0 incidents, any agent returning `status=="error"` OR `status=="timeout"` must trigger conflict. This is never negotiable.

INVARIANT: `loop_count` must never exceed `MAX_LOOPS` (default 2). This is never negotiable.

INVARIANT: A loop may only be entered when `conflict_detected==True` AND `loop_count < MAX_LOOPS`. This is never negotiable.

INVARIANT: When `loop_count >= MAX_LOOPS` and conflict detected, coordinator must escalate unconditionally. This is never negotiable.

INVARIANT: Each loop pass must inject the prior `runbook_result` (including `no_match`) into the Log Analyst prompt. An identical prompt to the previous pass is a violation. This is never negotiable.

INVARIANT: Any agent exceeding 30 seconds must be interrupted and return `status:"timeout"`, `confidence:0.0`. No unhandled exceptions from timeouts. This is never negotiable.

INVARIANT: A timeout or error in one parallel agent must not block or cancel the other parallel agents. This is never negotiable.

INVARIANT: The incident lifecycle must complete within 60 seconds under normal conditions. This is never negotiable.

INVARIANT: Auto-resolve requires ALL FOUR: `conflict_detected==False`, `runbook.status=="success"`, `len(resolution_steps) > 0`, `mean(confidences) >= 0.75`. This is never negotiable.

INVARIANT: Every escalation must produce a fully assembled `incident_brief`. `None` or empty brief on escalation is invalid. This is never negotiable.

INVARIANT: `resolution_plan` must be derived from `runbook_result.resolution_steps` only — never synthesised by the coordinator's LLM call. This is never negotiable.

INVARIANT: All alerts must be validated against `AlertPayload` schema before the graph is invoked. Missing required fields → HTTP 422. This is never negotiable.

INVARIANT: Deduplication is keyed on `(service_name, error_type)`. Duplicate alerts within 5 minutes must return the existing `incident_id`. This is never negotiable.

INVARIANT: P0/P1 → full pipeline. P2/P3 → log_analyst only. This is never negotiable.

INVARIANT: Comms agent must produce two passes: (1) from alert metadata only during fan-out, (2) revised with confirmed findings after coordinator synthesis. This is never negotiable.

INVARIANT: `Send("comms", {"alert": state["alert"]})` — comms receives only `state["alert"]` on first pass. Passing full state to comms is a violation. This is never negotiable.

INVARIANT: `coordinator_arbiter_node` must not wait for comms revision before computing `final_decision`. This is never negotiable.

INVARIANT: All failures must be explicitly written to state as `status:"error"` or `status:"timeout"`. Silent swallowing of exceptions is a violation. This is never negotiable.

INVARIANT: The system must continue and reach a terminal decision even if one or more parallel agents fail or timeout. This is never negotiable.

INVARIANT: The system must not execute real remediation commands, call live production APIs, post to real Slack, or trigger real PagerDuty. All external integrations target mock endpoints or fixture files. This is never negotiable.

INVARIANT: Pre-built demo scenarios must produce consistent outcomes. Determinism is achieved via fixture-based alert inputs and a seeded vectorstore — not by relying on exact LLM output text. This is never negotiable.

---

## 3. Scope Boundary

**Files CC may create or modify:**

```
backend/graph/state.py
backend/graph/models.py
backend/graph/graph.py
backend/graph/routing.py
backend/graph/nodes/parse_alert.py
backend/graph/nodes/log_analyst.py
backend/graph/nodes/runbook.py
backend/graph/nodes/blast_radius.py
backend/graph/nodes/comms.py
backend/graph/nodes/coordinator_arbiter.py
backend/graph/nodes/_stub.py
backend/prompts/log_analyst.py
backend/prompts/runbook.py
backend/prompts/blast_radius.py
backend/prompts/comms.py
backend/tools/vectorstore.py
backend/tools/auth_check.py
backend/tools/metrics.py
backend/config.py
backend/store.py
backend/sse.py
backend/main.py
backend/requirements.txt
backend/.env.example
backend/tests/test_schemas.py
backend/tests/test_graph_skeleton.py
backend/tests/test_agents.py
backend/tests/test_coordinator.py
backend/tests/test_integration.py
backend/tests/test_api.py
backend/tests/test_scenarios.py
backend/tests/conftest.py
backend/fixtures/alerts/scenario_a_db_pool.json
backend/fixtures/alerts/scenario_b_oom.json
backend/fixtures/alerts/scenario_c_auth_dns.json
backend/fixtures/metrics/metrics_mock.json
backend/fixtures/runbooks/*.md  (15 files, never OOM-related content)
frontend/src/types/incident.ts
frontend/src/hooks/useIncidentStream.ts
frontend/src/components/AgentStatusPanel.tsx
frontend/src/components/ConfidenceBar.tsx
frontend/src/components/TimelineView.tsx
frontend/src/components/BriefPanel.tsx
frontend/src/components/CommsPanel.tsx
frontend/src/components/DemoTrigger.tsx
frontend/src/components/IncidentFeed.tsx
frontend/src/App.tsx
frontend/package.json
frontend/tailwind.config.ts
deploy/Dockerfile.backend
deploy/Dockerfile.frontend
deploy/nginx.conf
```

**CC must not:**
- Create files outside this list without explicit instruction
- Add a second agent that communicates directly with another agent
- Replace LangGraph `Send` parallel fan-out with sequential `add_edge` calls
- Write `resolution_plan` content by calling the LLM from `coordinator_arbiter_node`
- Add `--workers` > 1 to any uvicorn invocation
- Store any credential, token, or key in any file
- Create a runbook document containing OOM, GC overhead, Java heap, or OutOfMemoryError content
- Add real Slack, PagerDuty, or external API calls
- Use `asyncio.gather(return_exceptions=False)` across parallel agent calls
- Call `vectorstore.seed()` or `vectorstore.add_documents()` inside an agent node

**If a task prompt conflicts with an invariant: the invariant wins. Flag the conflict immediately. Never resolve it silently.**

---

## 4. Fixed Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Agent orchestration | `langgraph` | `>=0.2.0` |
| LLM | `langchain-google-vertexai` `ChatVertexAI` | `>=1.0.0` |
| LLM model | `gemini-2.5-flash-lite` on Vertex AI | — |
| Embeddings | `VertexAIEmbeddings` `text-embedding-004` | — |
| GCP auth | Application Default Credentials (ADC) | — |
| Vector store | `chromadb` + `langchain-community` `Chroma` | `>=0.5.0` |
| API framework | `fastapi` + `uvicorn[standard]` | `>=0.111.0` / `>=0.30.0` |
| SSE | `sse-starlette` | `>=2.0.0` |
| Schema validation | `pydantic` v2 | `>=2.0.0` |
| HTTP client | `httpx` | `>=0.27.0` |
| Frontend | React + TailwindCSS | Node 20 |
| Deployment | Google Cloud Run | `--workers 1` |
| Image registry | Artifact Registry | `us-central1` |
| Python | 3.11 | `python:3.11-slim` (Docker) |

**Environment variables (all non-secret):**

| Variable | Default |
|----------|---------|
| `GCP_PROJECT_ID` | *(required — no default)* |
| `GCP_LOCATION` | `us-central1` |
| `GEMINI_MODEL` | `gemini-2.5-flash-lite` |
| `EMBEDDING_MODEL` | `text-embedding-004` |
| `AUTO_RESOLVE_THRESHOLD` | `0.75` |
| `CONFIDENCE_THRESHOLD` | `0.7` |
| `SPREAD_THRESHOLD` | `0.4` |
| `MEAN_FLOOR` | `0.5` |
| `SIMILARITY_THRESHOLD` | `0.65` |
| `MAX_LOOPS` | `2` |

If a technology, package, or environment variable is not listed here, CC must not introduce it without explicit instruction.
