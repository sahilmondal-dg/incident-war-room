# ARCHITECTURE.md — Incident War Room

> Multi-agent production incident response system  
> Architecture: **A — Centralised Supervisor**  
> Orchestration: **LangGraph `StateGraph`**  
> LLM: **Gemini 2.5 Flash Lite via Vertex AI (ADC — no API keys)**  
> Deployment: **Google Cloud Platform (Cloud Run + Artifact Registry)**

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [LLM & Infrastructure](#2-llm--infrastructure)
3. [Architecture Decision](#3-architecture-decision)
4. [LangGraph Graph Design](#4-langgraph-graph-design)
5. [Shared State Schema](#5-shared-state-schema)
6. [Agent Specifications](#6-agent-specifications)
7. [Execution Flow](#7-execution-flow)
8. [Conflict Detection & Loop Logic](#8-conflict-detection--loop-logic)
9. [API Layer](#9-api-layer)
10. [Frontend & Real-time Updates](#10-frontend--real-time-updates)
11. [Data & Storage](#11-data--storage)
12. [Project Structure](#12-project-structure)
13. [Key Design Decisions & Trade-offs](#13-key-design-decisions--trade-offs)
14. [GCP Deployment](#14-gcp-deployment)
15. [Local Setup](#15-local-setup)

---

## 1. System Overview

Incident War Room is a **multi-agent AI system** that automates the first-response investigation phase of production incidents. When an alert fires, the system spins up four specialist agents that run in parallel, coordinated by a central Coordinator. The agents report back with structured findings and confidence scores. The Coordinator arbitrates, detects conflicts, and either auto-resolves the incident or escalates to an on-call engineer with a fully assembled brief.

```
Alert → Coordinator → [Log Analyst ‖ Runbook ‖ Blast Radius ‖ Comms]
                    → Coordinator (arbiter) → Auto-resolve | Escalate
```

The key value over a simple LLM chain:
- **Parallel execution** — four agents run simultaneously, not sequentially
- **Typed state** — agents communicate via a shared `TypedDict`, not free-form strings
- **Conflict arbitration** — the Coordinator detects disagreement between agents and can trigger a re-investigation loop before deciding
- **Agentic loop** — the graph is cyclic; a second pass is a real second LLM call with enriched context, not a retry

---

## 2. LLM & Infrastructure

### 2.1 LLM — Gemini 2.5 Flash Lite on Vertex AI

All agent LLM calls use **Gemini 2.5 Flash Lite** served through Google Cloud Vertex AI. This model is chosen for three reasons specific to this project:

- **Speed** — Flash Lite is optimised for low-latency inference, critical when 3 agents fire in parallel and the total wall-clock time must stay under 60s
- **Structured output** — native JSON mode via `response_mime_type="application/json"` with a schema, replacing `response_format` from OpenAI-style APIs
- **No API key required** — authentication uses Application Default Credentials (ADC). Anyone with `gcloud auth application-default login` and the right IAM role can run the system immediately

**LangChain integration:**

```python
from langchain_google_vertexai import ChatVertexAI

llm = ChatVertexAI(
    model="gemini-2.5-flash-lite",   # model ID on Vertex AI
    project=GCP_PROJECT_ID,
    location="us-central1",
    temperature=0.1,                  # low temp for consistent structured output
    max_output_tokens=2048,
)
```

No `credentials` parameter needed when running locally with ADC or on Cloud Run with a service account. LangChain's `ChatVertexAI` picks up credentials automatically from the environment.

**Structured output per agent call:**

```python
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

parser = JsonOutputParser(pydantic_object=AgentFindingModel)

chain = (
    ChatPromptTemplate.from_template(LOG_ANALYST_PROMPT)
    | llm.bind(
        response_mime_type="application/json",
        response_schema=AgentFindingModel.model_json_schema()
      )
    | parser
)

result: AgentFinding = await chain.ainvoke({"logs": log_snippet, ...})
```

### 2.2 Embeddings — Vertex AI Text Embeddings

The Runbook agent's vector search uses **Vertex AI text embeddings** (`text-embedding-004`), keeping all AI calls within GCP — no OpenAI dependency.

```python
from langchain_google_vertexai import VertexAIEmbeddings

embeddings = VertexAIEmbeddings(
    model_name="text-embedding-004",
    project=GCP_PROJECT_ID,
    location="us-central1",
)

vectorstore = Chroma(
    collection_name="runbooks",
    embedding_function=embeddings,
    persist_directory="./chroma_db"   # local during dev, mounted volume on Cloud Run
)
```

### 2.3 Authentication — Application Default Credentials (ADC)

ADC means the code never touches a credential string. The auth chain is:

```
Local dev   →  gcloud auth application-default login  →  ~/.config/gcloud/adc.json
Cloud Run   →  attached service account               →  metadata server auto-provides token
CI/CD       →  Workload Identity Federation           →  keyless, no JSON key files
```

**Required IAM roles** for the service account (or your personal account for local dev):

| Role | Why |
|------|-----|
| `roles/aiplatform.user` | Call Vertex AI inference endpoints (Gemini + embeddings) |
| `roles/run.invoker` | Allow Cloud Run services to call each other (if split into microservices later) |
| `roles/storage.objectViewer` | Read runbook fixtures from GCS (optional — local files used for hackathon) |
| `roles/logging.logWriter` | Write structured logs to Cloud Logging |

**One-time local setup:**
```bash
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID
```

After this, all Vertex AI calls in the codebase work with zero credential config.

---

## 3. Architecture Decision

**Chosen: Architecture A — Centralised Supervisor**

The Coordinator owns all state. Agents are pure functions: they receive a slice of state as input and return an updated slice as output. No agent talks directly to another. All routing decisions live in the Coordinator nodes.

```
                    ┌─────────────────────────────────────┐
                    │           LANGGRAPH GRAPH           │
                    │                                     │
  Alert ──────► [parse_alert]                             │
                    │                                     │
                    ▼                                     │
            [log_analyst_node]  ← runs first (pre-step)  │
                    │                                     │
        ┌───────────┼───────────┐                         │
        ▼           ▼           ▼                         │
  [runbook]  [blast_radius]  [comms]  ← parallel fan-out │
        └───────────┼───────────┘                         │
                    ▼                                     │
            [coordinator_arbiter]                         │
                    │                                     │
          ┌─────────┴──────────┐                          │
          ▼                    ▼                          │
    [auto_resolve]      [escalate]                        │
                    │         ↑                           │
                    │    loop back if conflict            │
                    └─────────────────────────────────────┘
```

**Why Log Analyst runs as a pre-step (not fully parallel):**  
The Runbook agent needs a structured `root_cause` string to run semantic search against the vector store. Running it on raw logs produces poor similarity results. Log Analyst runs first (~3–5s), then Runbook, Blast Radius, and Comms all fan out simultaneously. This costs ~4 seconds but dramatically improves Runbook accuracy.

**Trade-offs accepted:**
- Coordinator is a single point of failure → acceptable for hackathon, mitigated by timeout guards
- Log Analyst is on the critical path → fast model call, not a bottleneck in practice
- Not the most scalable architecture → post-hackathon migration to Architecture B (message bus) is straightforward

---

## 4. LangGraph Graph Design

### 3.1 Graph skeleton

```python
from langgraph.graph import StateGraph, END
from langgraph.constants import Send

builder = StateGraph(IncidentState)

# Nodes
builder.add_node("parse_alert",         parse_alert_node)
builder.add_node("log_analyst",         log_analyst_node)
builder.add_node("runbook",             runbook_node)
builder.add_node("blast_radius",        blast_radius_node)
builder.add_node("comms",               comms_node)
builder.add_node("coordinator_arbiter", coordinator_arbiter_node)
builder.add_node("auto_resolve",        auto_resolve_node)
builder.add_node("escalate",            escalate_node)

# Edges — sequential pre-step
builder.set_entry_point("parse_alert")
builder.add_edge("parse_alert", "log_analyst")

# Fan-out: after log_analyst, run three agents in parallel
builder.add_conditional_edges(
    "log_analyst",
    fan_out_after_log,          # returns list of Send() objects
    ["runbook", "blast_radius", "comms"]
)

# Fan-in: all three report to coordinator
builder.add_edge("runbook",      "coordinator_arbiter")
builder.add_edge("blast_radius", "coordinator_arbiter")
builder.add_edge("comms",        "coordinator_arbiter")

# Coordinator routes to resolve, escalate, or loop
builder.add_conditional_edges(
    "coordinator_arbiter",
    route_after_arbitration,    # returns "auto_resolve" | "escalate" | "log_analyst"
    ["auto_resolve", "escalate", "log_analyst"]
)

builder.add_edge("auto_resolve", END)
builder.add_edge("escalate",     END)

graph = builder.compile()
```

### 3.2 Fan-out function

```python
def fan_out_after_log(state: IncidentState) -> list[Send]:
    """
    After log_analyst completes, dispatch runbook, blast_radius,
    and comms in parallel using LangGraph's Send primitive.
    """
    return [
        Send("runbook",      {"log_finding": state["log_analysis"]}),
        Send("blast_radius", {"alert": state["alert"]}),
        Send("comms",        {"alert": state["alert"]}),
    ]
```

### 3.3 Routing function

```python
def route_after_arbitration(state: IncidentState) -> str:
    if state["final_decision"] == "auto_resolve":
        return "auto_resolve"
    elif state["final_decision"] == "escalate":
        return "escalate"
    else:  # "loop"
        return "log_analyst"  # re-enters graph with enriched context
```

---

## 5. Shared State Schema

All agents read from and write to a single `IncidentState` `TypedDict`. No agent holds private state between calls.

```python
from typing import TypedDict, Literal, Optional
from datetime import datetime

class AgentFinding(TypedDict):
    agent_id:         str               # e.g. "log_analyst"
    status:           Literal["success", "no_match", "timeout", "error"]
    root_cause:       Optional[str]     # None if agent could not determine
    confidence:       float             # 0.0 – 1.0
    justification:    str               # one sentence explaining the confidence
    resolution_steps: list[str]         # ordered remediation actions
    evidence:         list[str]         # supporting log lines / excerpts
    timestamp:        str               # ISO 8601

class CommsDraft(TypedDict):
    status_page:  str                   # formatted status page update
    slack_message: str                  # internal #incidents message
    revised:      bool                  # True if updated post-synthesis

class AlertPayload(TypedDict):
    alert_id:     str
    service_name: str
    severity:     Literal["P0", "P1", "P2", "P3"]
    error_type:   str
    log_snippet:  str
    timestamp:    str

class IncidentState(TypedDict):
    # Input
    alert:             AlertPayload

    # Agent outputs (populated progressively)
    log_analysis:      Optional[AgentFinding]
    runbook_result:    Optional[AgentFinding]
    blast_radius:      Optional[AgentFinding]
    comms_drafts:      Optional[CommsDraft]

    # Coordinator control fields
    conflict_detected: bool
    conflict_reason:   Optional[str]    # human-readable explanation
    loop_count:        int              # max 2, enforced in routing function
    final_decision:    Optional[Literal["auto_resolve", "escalate", "loop"]]

    # Output
    incident_brief:    Optional[str]    # assembled markdown brief for engineers
    resolution_plan:   Optional[str]    # step-by-step fix plan (auto-resolve only)
```

**State mutation rules:**
- Each agent node receives the full `IncidentState` and returns a partial dict — only the keys it owns
- LangGraph merges the partial return into the shared state automatically
- No agent mutates another agent's keys
- `loop_count` is incremented exclusively by `coordinator_arbiter_node`

---

## 6. Agent Specifications

### 5.1 Log Analyst Agent

**Purpose:** Identify the root cause from raw log data.

**Input from state:** `state["alert"]["log_snippet"]`, `state["alert"]["service_name"]`  
**Writes to state:** `state["log_analysis"]`

**LLM call pattern:**
```python
async def log_analyst_node(state: IncidentState) -> dict:
    prompt = LOG_ANALYST_PROMPT.format(
        service=state["alert"]["service_name"],
        logs=state["alert"]["log_snippet"],
        loop_count=state.get("loop_count", 0),
        # On loop >0, inject runbook null result as additional context
        runbook_context=state.get("runbook_result") if state.get("loop_count", 0) > 0 else None
    )
    response = await llm.ainvoke(prompt, response_format=AgentFinding)
    return {"log_analysis": response}
```

**Output schema:** `AgentFinding` with `root_cause` as a taxonomy string:  
`"db_timeout" | "oom" | "network" | "auth" | "upstream" | "unknown"`

**Confidence heuristics the prompt enforces:**
- `> 0.85` — clear repeated error pattern with stack trace
- `0.6–0.85` — pattern present but ambiguous (e.g. multiple error types)
- `< 0.6` — insufficient log data or novel error pattern

---

### 5.2 Runbook Agent

**Purpose:** Find a matching runbook or past incident for the diagnosed root cause.

**Input from state:** `state["log_analysis"]["root_cause"]`, `state["log_analysis"]["evidence"]`  
**Writes to state:** `state["runbook_result"]`

**Tool used:** ChromaDB semantic search

```python
async def runbook_node(state: IncidentState) -> dict:
    query = build_runbook_query(state["log_analysis"])
    results = await vectorstore.asimilarity_search_with_score(query, k=3)

    if not results or results[0][1] < SIMILARITY_THRESHOLD:  # threshold: 0.65
        return {"runbook_result": AgentFinding(
            agent_id="runbook",
            status="no_match",
            root_cause=None,
            confidence=0.0,
            justification=f"No runbook matched above threshold {SIMILARITY_THRESHOLD}",
            resolution_steps=[],
            evidence=[],
            timestamp=now_iso()
        )}

    doc, score = results[0]
    steps = extract_steps(doc.page_content)
    return {"runbook_result": AgentFinding(
        agent_id="runbook",
        status="success",
        root_cause=doc.metadata["title"],
        confidence=float(score),
        justification=f"Matched '{doc.metadata['title']}' with similarity {score:.2f}",
        resolution_steps=steps,
        evidence=[doc.page_content[:400]],
        timestamp=now_iso()
    )}
```

**Vector store:** ChromaDB in-memory, pre-populated with 15 runbook documents at startup.  
Each document has metadata: `{ title, category, service_tags[], last_updated }`.

---

### 5.3 Blast Radius Agent

**Purpose:** Estimate the user and service impact of the incident.

**Input from state:** `state["alert"]`  
**Writes to state:** `state["blast_radius"]`

**Data source:** Mocked metrics fixture (`fixtures/metrics.json`) — simulates a Datadog/CloudWatch API response.

```python
async def blast_radius_node(state: IncidentState) -> dict:
    metrics = await fetch_metrics(
        service=state["alert"]["service_name"],
        window_minutes=10
    )
    # LLM interprets raw metrics into a structured finding
    prompt = BLAST_RADIUS_PROMPT.format(
        alert=state["alert"],
        metrics=metrics
    )
    finding = await llm.ainvoke(prompt, response_format=AgentFinding)
    return {"blast_radius": finding}
```

**Output includes:** `affected_users` (int), `regions` (list), `downstream_services` (list), `severity_tier` (`"low" | "medium" | "high" | "critical"`), `revenue_per_minute` (float) — embedded in the `evidence` list as a JSON string for UI rendering.

---

### 5.4 Communications Agent

**Purpose:** Draft the status page update and internal Slack message.

**Input from state:** `state["alert"]` (initial draft), then `state` (full, for revision)  
**Writes to state:** `state["comms_drafts"]`

**Two-pass design:**  
The Comms agent runs in the parallel fan-out using only the alert metadata. Once the Coordinator has synthesized all findings, it calls a lightweight revision step that updates the drafts with the confirmed root cause and blast radius. This means comms are never delayed waiting for diagnosis.

```python
async def comms_node(state: IncidentState) -> dict:
    # First pass: alert metadata only
    drafts = await llm.ainvoke(
        COMMS_PROMPT_INITIAL.format(alert=state["alert"]),
        response_format=CommsDraft
    )
    return {"comms_drafts": {**drafts, "revised": False}}

async def revise_comms(state: IncidentState) -> dict:
    # Called by coordinator_arbiter after synthesis
    revised = await llm.ainvoke(
        COMMS_PROMPT_REVISE.format(
            draft=state["comms_drafts"],
            log_finding=state["log_analysis"],
            blast_radius=state["blast_radius"]
        ),
        response_format=CommsDraft
    )
    return {"comms_drafts": {**revised, "revised": True}}
```

---

### 5.5 Coordinator Arbiter Node

**Purpose:** Synthesize all agent findings, detect conflicts, increment loop counter, and make the final routing decision.

**Input:** Full `IncidentState` after all parallel agents complete  
**Writes:** `conflict_detected`, `conflict_reason`, `loop_count`, `final_decision`, `incident_brief`

```python
async def coordinator_arbiter_node(state: IncidentState) -> dict:
    log   = state["log_analysis"]
    rb    = state["runbook_result"]
    br    = state["blast_radius"]
    loop  = state.get("loop_count", 0)

    # ── Conflict detection rules (applied in order) ──────────────────────────
    conflict, reason = detect_conflict(log, rb, br)

    if conflict and loop < MAX_LOOPS:           # MAX_LOOPS = 2
        return {
            "conflict_detected": True,
            "conflict_reason":   reason,
            "loop_count":        loop + 1,
            "final_decision":    "loop"
        }

    if conflict and loop >= MAX_LOOPS:
        brief = await build_incident_brief(state, decision="escalate")
        return {
            "conflict_detected": True,
            "conflict_reason":   reason,
            "loop_count":        loop,
            "final_decision":    "escalate",
            "incident_brief":    brief
        }

    # No conflict — check mean confidence
    mean_conf = mean([log["confidence"], rb["confidence"], br["confidence"]])
    if mean_conf >= AUTO_RESOLVE_THRESHOLD:     # AUTO_RESOLVE_THRESHOLD = 0.75
        plan = build_resolution_plan(rb["resolution_steps"])
        return {
            "conflict_detected": False,
            "final_decision":    "auto_resolve",
            "resolution_plan":   plan,
            "incident_brief":    await build_incident_brief(state, decision="auto_resolve")
        }
    else:
        # Confidence too low — escalate
        brief = await build_incident_brief(state, decision="escalate")
        return {
            "conflict_detected": False,
            "final_decision":    "escalate",
            "incident_brief":    brief
        }
```

---

## 7. Execution Flow

### Happy path (auto-resolve, ~15–25s total)

```
t=0s    Alert webhook received → parse_alert node
t=1s    log_analyst_node fires → LLM call with log snippet
t=5s    log_analyst completes (confidence: 0.91, root_cause: "db_timeout")
t=5s    Fan-out: runbook, blast_radius, comms all start simultaneously
t=8s    comms completes (first-pass draft from alert metadata)
t=11s   blast_radius completes (1,200 users, EU-West, high severity)
t=13s   runbook completes (match: "DB Pool Recovery Runbook", score: 0.88)
t=13s   All parallel nodes done → coordinator_arbiter fires
t=13s   No conflict detected. mean_confidence = 0.89 > 0.75 → "auto_resolve"
t=14s   comms revision pass runs
t=14s   auto_resolve node builds resolution plan → END
```

### Conflict path (escalate after loop, ~30–45s total)

```
t=0s    Alert webhook received → parse_alert
t=1s    log_analyst fires
t=5s    log_analyst completes (confidence: 0.82, root_cause: "oom")
t=5s    Fan-out fires
t=12s   runbook completes (status: "no_match", confidence: 0.0)
t=12s   coordinator_arbiter fires — CONFLICT: log confident, runbook null
        loop_count = 0 < 2 → decision: "loop", loop_count → 1
t=12s   log_analyst fires AGAIN with runbook null result injected as context
t=16s   log_analyst re-runs (confidence: 0.79, root_cause: "oom" confirmed)
t=16s   Fan-out fires again (runbook with enriched query, blast_radius, comms)
t=24s   runbook: still no_match (confidence: 0.0)
        coordinator_arbiter fires — CONFLICT again, loop_count = 1 < 2 → loop
        loop_count → 2
t=24s   log_analyst fires third time
t=28s   coordinator_arbiter: loop_count = 2 >= MAX_LOOPS → "escalate"
t=29s   escalate node assembles brief → POST to mock pager endpoint → END
```

---

## 8. Conflict Detection & Loop Logic

### Conflict detection rules

Applied in order inside `coordinator_arbiter_node`. First matching rule wins.

```python
def detect_conflict(
    log: AgentFinding,
    rb:  AgentFinding,
    br:  AgentFinding
) -> tuple[bool, Optional[str]]:

    # Rule 1: Log confident but no runbook match
    if log["confidence"] >= 0.7 and rb["status"] == "no_match":
        return True, (
            f"Log Analyst confident ({log['confidence']:.2f}) in "
            f"'{log['root_cause']}' but Runbook Agent found no matching document."
        )

    # Rule 2: High confidence spread between log and blast radius
    if abs(log["confidence"] - br["confidence"]) > 0.4:
        return True, (
            f"Confidence spread too high: Log={log['confidence']:.2f}, "
            f"BlastRadius={br['confidence']:.2f}. Findings may be inconsistent."
        )

    # Rule 3: Any error status on P0
    # (state["alert"]["severity"] checked by caller before calling this fn)

    # Rule 4: Mean confidence below floor even without explicit conflict
    mean_conf = mean([log["confidence"], rb["confidence"], br["confidence"]])
    if mean_conf < 0.5:
        return True, f"Mean confidence {mean_conf:.2f} below minimum floor 0.5."

    return False, None
```

### Loop guard

```python
MAX_LOOPS = 2

# Inside coordinator_arbiter_node:
if conflict and state["loop_count"] >= MAX_LOOPS:
    # Do not loop again — force escalate
    final_decision = "escalate"
```

On each loop, `log_analyst_node` receives the prior `runbook_result` (even if `no_match`) injected into its prompt context window. This gives the LLM a chance to re-examine the logs with the knowledge that the standard runbook didn't match — sometimes shifting its hypothesis.

---

## 9. API Layer

**Framework:** FastAPI (Python 3.11+)

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook/alert` | Ingest alert, trigger graph, return `incident_id` |
| `GET`  | `/incidents` | List all incidents (active + resolved) |
| `GET`  | `/incidents/{id}` | Full incident detail with all agent findings |
| `GET`  | `/incidents/{id}/stream` | SSE stream of live agent status updates |
| `POST` | `/demo/trigger/{scenario}` | Fire pre-built demo scenario (A, B, or C) |
| `GET`  | `/health` | Liveness check |

### Webhook payload

```json
{
  "alert_id":     "pd-abc123",
  "service_name": "payments-api",
  "severity":     "P1",
  "error_type":   "high_error_rate",
  "log_snippet":  "ERROR: connection pool timeout after 30000ms...",
  "timestamp":    "2026-03-23T14:32:00Z"
}
```

### SSE event stream

The frontend subscribes to `/incidents/{id}/stream` and receives events as each agent node completes:

```
data: {"event": "node_start",    "node": "log_analyst",   "timestamp": "..."}
data: {"event": "node_complete", "node": "log_analyst",   "confidence": 0.91, "timestamp": "..."}
data: {"event": "node_start",    "node": "runbook",        "timestamp": "..."}
data: {"event": "node_start",    "node": "blast_radius",   "timestamp": "..."}
data: {"event": "node_start",    "node": "comms",          "timestamp": "..."}
data: {"event": "node_complete", "node": "comms",          "confidence": null, "timestamp": "..."}
data: {"event": "node_complete", "node": "blast_radius",   "confidence": 0.88, "timestamp": "..."}
data: {"event": "node_complete", "node": "runbook",        "confidence": 0.0,  "status": "no_match", "timestamp": "..."}
data: {"event": "conflict",      "reason": "Log confident, no runbook match", "loop": 1}
data: {"event": "decision",      "decision": "escalate",   "timestamp": "..."}
```

### LangGraph ↔ FastAPI integration

```python
@app.post("/webhook/alert")
async def ingest_alert(payload: AlertPayload, background_tasks: BackgroundTasks):
    incident_id = str(uuid4())
    initial_state = IncidentState(
        alert=payload.dict(),
        log_analysis=None,
        runbook_result=None,
        blast_radius=None,
        comms_drafts=None,
        conflict_detected=False,
        conflict_reason=None,
        loop_count=0,
        final_decision=None,
        incident_brief=None,
        resolution_plan=None
    )
    # Store initial record
    await db.create_incident(incident_id, initial_state)

    # Run graph in background, stream events via SSE publisher
    background_tasks.add_task(run_graph, incident_id, initial_state)
    return {"incident_id": incident_id, "stream_url": f"/incidents/{incident_id}/stream"}


async def run_graph(incident_id: str, state: IncidentState):
    async for event in graph.astream_events(state, version="v2"):
        await sse_publisher.publish(incident_id, event)
        await db.update_incident(incident_id, event)
```

---

## 10. Frontend & Real-time Updates

**Framework:** React + TailwindCSS  
**Real-time:** Server-Sent Events via `EventSource` API

### Component tree

```
<App>
  <IncidentFeed />          ← list of active/resolved incidents
  <IncidentDetail>
    <AgentStatusPanel />    ← live tiles per agent, shows running/done/conflict
    <ConfidenceBar />       ← per-agent confidence score
    <TimelineView />        ← chronological event log
    <BriefPanel />          ← incident brief or resolution plan
    <CommsPanel />          ← status page + slack draft
  </IncidentDetail>
  <DemoTrigger />           ← one-click scenario buttons for demo
</App>
```

### Live agent status panel

Each agent tile transitions through states: `idle → running → done | conflict | timeout`.  
Transitions are driven by SSE events — no polling.

```typescript
useEffect(() => {
  const es = new EventSource(`/incidents/${incidentId}/stream`);
  es.onmessage = (e) => {
    const event = JSON.parse(e.data);
    dispatch({ type: event.event, payload: event });
  };
  return () => es.close();
}, [incidentId]);
```

---

## 11. Data & Storage

**For hackathon:** All storage is in-memory Python dicts — no database dependency.

```python
from langchain_google_vertexai import VertexAIEmbeddings
from langchain_community.vectorstores import Chroma

# In-memory incident store — sufficient for demo
incidents: dict[str, IncidentState] = {}

# Vertex AI embeddings — no API key, uses ADC
embeddings = VertexAIEmbeddings(
    model_name="text-embedding-004",
    project=GCP_PROJECT_ID,
    location="us-central1",
)

# Populated at startup from fixtures/runbooks/
vectorstore = Chroma(
    collection_name="runbooks",
    embedding_function=embeddings,
)
```

### Fixture files

```
fixtures/
  alerts/
    scenario_a_db_pool.json       # auto-resolve scenario
    scenario_b_oom.json           # conflict-escalate scenario
    scenario_c_auth_dns.json      # loop-then-resolve scenario
  metrics/
    metrics_mock.json             # simulated Datadog response
  runbooks/
    db_pool_recovery.md
    network_degradation.md
    auth_service_restart.md
    kubernetes_oom.md
    dns_resolution.md
    ... (15 total)
```

---

## 12. Project Structure

```
incident-war-room/
│
├── backend/
│   ├── main.py                  # FastAPI app, routes, SSE publisher
│   ├── graph/
│   │   ├── __init__.py
│   │   ├── state.py             # IncidentState TypedDict, AgentFinding
│   │   ├── graph.py             # StateGraph definition, compile()
│   │   ├── routing.py           # fan_out_after_log(), route_after_arbitration()
│   │   └── nodes/
│   │       ├── parse_alert.py
│   │       ├── log_analyst.py
│   │       ├── runbook.py
│   │       ├── blast_radius.py
│   │       ├── comms.py
│   │       └── coordinator_arbiter.py
│   ├── prompts/
│   │   ├── log_analyst.py
│   │   ├── runbook.py
│   │   ├── blast_radius.py
│   │   └── comms.py
│   ├── tools/
│   │   ├── vectorstore.py       # ChromaDB setup + Vertex AI embeddings seed
│   │   └── metrics.py           # mock metrics fetch from fixture
│   ├── fixtures/                # demo data (see §11)
│   ├── .env                     # GCP_PROJECT_ID, thresholds (no secrets)
│   └── requirements.txt         # see §15 for full list
│
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── IncidentFeed.tsx
│   │   │   ├── AgentStatusPanel.tsx
│   │   │   ├── ConfidenceBar.tsx
│   │   │   ├── TimelineView.tsx
│   │   │   ├── BriefPanel.tsx
│   │   │   ├── CommsPanel.tsx
│   │   │   └── DemoTrigger.tsx
│   │   ├── hooks/
│   │   │   └── useIncidentStream.ts
│   │   └── types/
│   │       └── incident.ts
│   ├── package.json
│   └── tailwind.config.ts
│
├── deploy/
│   ├── Dockerfile.backend       # Python 3.11-slim, seeds vectorstore at build
│   ├── Dockerfile.frontend      # Node build → Nginx static serve
│   ├── nginx.conf               # Proxies /api/* to backend Cloud Run URL
│   └── cloudbuild.yaml          # Optional: Cloud Build CI/CD pipeline
│
├── ARCHITECTURE.md              # this file
├── README.md
└── docker-compose.yml           # local dev: backend + frontend together
```

---

## 13. Key Design Decisions & Trade-offs

| Decision | Choice | Rationale |
|----------|--------|-----------|
| LLM provider | Vertex AI (Gemini 2.5 Flash Lite) | ADC auth = no API keys; fast enough for parallel agents; generous free tier on GCP |
| Embeddings | Vertex AI `text-embedding-004` | Same GCP project, same ADC auth — zero extra credential setup |
| Agent communication | Shared `TypedDict` state | No direct agent calls = clean LangGraph pattern, easy to inspect in LangSmith |
| Log Analyst as pre-step | Sequential before fan-out | Runbook needs structured `root_cause` — parallel execution gives poor semantic search results |
| Conflict detection location | `coordinator_arbiter_node` exclusively | Single place to audit, test, and tune thresholds |
| Loop cap | `MAX_LOOPS = 2` | Prevents runaway LLM calls; 2 loops = 3 total log analyst calls max |
| SSE over WebSockets | SSE (`EventSource`) | Unidirectional server → client is sufficient; simpler to implement and debug |
| In-memory storage | Python dicts | Zero config for hackathon; post-hackathon swap to Firestore is a one-file change |
| Structured LLM output | `response_mime_type="application/json"` + Pydantic schema | Vertex AI native JSON mode — eliminates parsing failures |
| Comms two-pass design | Initial draft + revision | Status page is never blocked by diagnosis; revision adds confirmed root cause post-arbitration |
| Deployment target | Cloud Run | Serverless, scales to zero, no cluster management — perfect for hackathon |

---

## 14. GCP Deployment

The entire system deploys to **Google Cloud Run** — two services: one for the FastAPI backend and one to serve the React frontend as a static build via Nginx. Both images are stored in **Artifact Registry**.

### 14.1 GCP services used

| Service | What it does |
|---------|-------------|
| **Cloud Run** | Runs the FastAPI backend container, serverless, scales to zero |
| **Cloud Run (frontend)** | Serves the React static build via Nginx container |
| **Artifact Registry** | Stores Docker images (`us-central1-docker.pkg.dev/PROJECT/war-room/`) |
| **Vertex AI** | Hosts Gemini 2.5 Flash Lite inference + text-embedding-004 |
| **Cloud Logging** | Receives structured JSON logs from both services automatically |
| **Secret Manager** | Optional — only needed for future non-GCP secrets (nothing required for hackathon) |

### 14.2 Architecture on GCP

```
Internet
    │
    ├──► Cloud Run (frontend) :80
    │         Nginx serves React build
    │         Proxies /api/* → backend
    │
    └──► Cloud Run (backend) :8000
              FastAPI + LangGraph
                    │
                    ├──► Vertex AI  (Gemini 2.5 Flash Lite — same project, ADC)
                    └──► Vertex AI  (text-embedding-004 — same project, ADC)
```

### 14.3 Dockerfile — backend

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ .

# Seed the vector store at build time so it's baked into the image
RUN python tools/vectorstore.py --seed

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 14.4 Dockerfile — frontend

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
# Inject the backend Cloud Run URL at build time
ARG VITE_API_URL
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### 14.5 Deploy commands

```bash
# 1. Set project variables
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
export REPO=war-room

# 2. Create Artifact Registry repo (one-time)
gcloud artifacts repositories create $REPO \
  --repository-format=docker \
  --location=$REGION

# 3. Configure Docker auth
gcloud auth configure-docker $REGION-docker.pkg.dev

# 4. Build and push backend
docker build -t $REGION-docker.pkg.dev/$PROJECT_ID/$REPO/backend:latest \
  -f Dockerfile.backend .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/$REPO/backend:latest

# 5. Deploy backend to Cloud Run
gcloud run deploy incident-war-room-backend \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/backend:latest \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID,GCP_LOCATION=$REGION" \
  --service-account=war-room-sa@$PROJECT_ID.iam.gserviceaccount.com \
  --memory=1Gi \
  --cpu=2 \
  --concurrency=10 \
  --timeout=120

# 6. Get backend URL
BACKEND_URL=$(gcloud run services describe incident-war-room-backend \
  --region=$REGION --format='value(status.url)')

# 7. Build and push frontend (inject backend URL)
docker build \
  --build-arg VITE_API_URL=$BACKEND_URL \
  -t $REGION-docker.pkg.dev/$PROJECT_ID/$REPO/frontend:latest \
  -f Dockerfile.frontend .
docker push $REGION-docker.pkg.dev/$PROJECT_ID/$REPO/frontend:latest

# 8. Deploy frontend to Cloud Run
gcloud run deploy incident-war-room-frontend \
  --image=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/frontend:latest \
  --region=$REGION \
  --platform=managed \
  --allow-unauthenticated \
  --memory=256Mi \
  --cpu=1
```

### 14.6 Service account setup (one-time)

```bash
# Create dedicated service account
gcloud iam service-accounts create war-room-sa \
  --display-name="Incident War Room Service Account"

# Grant only required roles
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:war-room-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:war-room-sa@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```

Cloud Run automatically injects ADC credentials for the attached service account — no key files, no environment variables for auth.

### 14.7 SSE and Cloud Run

Cloud Run supports SSE natively but has a **60-second request timeout** by default. The `--timeout=120` flag above extends this. For the demo, each incident completes in under 60 seconds, so the default would work too — but 120s gives headroom for the conflict-loop scenario.

Cloud Run also automatically handles the HTTP/1.1 chunked transfer encoding that SSE requires. No special Nginx config needed on the backend service.

---

## 15. Local Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) (`gcloud` CLI)
- A GCP project with the Vertex AI API enabled

```bash
# Enable Vertex AI API on your project (one-time)
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

### Step-by-step

```bash
# 1. Authenticate with GCP — this is all you need, no API keys
gcloud auth application-default login
gcloud config set project YOUR_PROJECT_ID

# 2. Clone the repo
git clone https://github.com/your-org/incident-war-room
cd incident-war-room

# 3. Install backend dependencies
cd backend
pip install -r requirements.txt

# 4. Create a .env file with GCP config (no secrets — just project metadata)
cat > .env << EOF
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1
AUTO_RESOLVE_THRESHOLD=0.75
MAX_LOOPS=2
SIMILARITY_THRESHOLD=0.65
EOF

# 5. Seed the vector store with runbook fixtures
python tools/vectorstore.py --seed
# Output: "Seeded 15 runbook documents into ChromaDB"

# 6. Start the backend
uvicorn main:app --reload --port 8000

# 7. In a new terminal — start the frontend
cd ../frontend
npm install
npm run dev
# Running on http://localhost:5173

# 8. Trigger a demo scenario
curl -X POST http://localhost:8000/demo/trigger/scenario_a
# Returns: {"incident_id": "...", "stream_url": "/incidents/.../stream"}
```

### Environment variables

All variables are non-sensitive project configuration — no secrets or API keys.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GCP_PROJECT_ID` | Yes | — | Your GCP project ID |
| `GCP_LOCATION` | No | `us-central1` | Vertex AI region |
| `GEMINI_MODEL` | No | `gemini-2.5-flash-lite` | Vertex AI model ID |
| `EMBEDDING_MODEL` | No | `text-embedding-004` | Vertex AI embedding model |
| `AUTO_RESOLVE_THRESHOLD` | No | `0.75` | Confidence floor for auto-resolve decision |
| `MAX_LOOPS` | No | `2` | Maximum re-investigation cycles per incident |
| `SIMILARITY_THRESHOLD` | No | `0.65` | Minimum ChromaDB score for runbook match |

### requirements.txt

```txt
fastapi>=0.111.0
uvicorn[standard]>=0.30.0
langgraph>=0.2.0
langchain>=0.2.0
langchain-google-vertexai>=1.0.0    # ChatVertexAI + VertexAIEmbeddings
langchain-community>=0.2.0          # Chroma integration
chromadb>=0.5.0
pydantic>=2.0.0
python-dotenv>=1.0.0
sse-starlette>=2.0.0               # SSE support for FastAPI
httpx>=0.27.0
```

> **No `ANTHROPIC_API_KEY`, no `OPENAI_API_KEY`.** The only credential required is your GCP identity via `gcloud auth application-default login`.

---

*Last updated: March 2026 — Architecture A (Centralised Supervisor) · GCP Vertex AI · Cloud Run*
