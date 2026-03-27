# EXECUTION_PLAN.md — Incident War Room
> PBVI Phase 3 · Architecture A (Centralised Supervisor) · Vertex AI Gemini 2.5 Flash Lite

---

## Resolved Decisions

All open questions from ARCHITECTURE.md resolved before this plan was produced.

| Question | Decision | Rationale |
|----------|----------|-----------|
| Embeddings model | Vertex AI `text-embedding-004` | Same GCP project, same ADC — zero extra credential setup |
| LangGraph graph in UI | SSE event stream only — no graph visualisation in demo | Adds build time with no judging value; the agent status panel conveys the same information |
| Frontend framework | React + TailwindCSS | Faster than Next.js for a single-page demo; no SSR needed |
| Conflict thresholds | Hardcoded in `config.py` — `CONFIDENCE_THRESHOLD=0.7`, `SPREAD_THRESHOLD=0.4`, `AUTO_RESOLVE_THRESHOLD=0.75`, `MEAN_FLOOR=0.5` | Config file allows tuning without code change; UI sliders are out of scope |
| Demo trigger mechanism | Both: UI button AND `curl` command | Buttons for the live demo; curl for judges who want to inspect the API |
| `--workers` on Cloud Run | 1 worker only | Multiple workers fragment the in-memory incidents store and break SSE routing |

---

## Session Overview

| Session | Name | Goal | Tasks | Est. Duration |
|---------|------|------|-------|---------------|
| S1 | Scaffold & State | Runnable repo, GCP auth confirmed, shared schemas defined | 4 | 1.5 hrs |
| S2 | Graph Skeleton | Compilable LangGraph graph with stub nodes, end-to-end traversal verified | 3 | 1.5 hrs |
| S3 | Agent Nodes | All five agent nodes with real Vertex AI calls and full error handling | 5 | 3 hrs |
| S4 | Coordinator | Conflict detection, loop logic, all four decision paths, end-to-end integration | 4 | 2 hrs |
| S5 | API & SSE | FastAPI endpoints, SSE streaming, deduplication, demo trigger routes | 4 | 2 hrs |
| S6 | Vector Store & Fixtures | ChromaDB seeded with 15 runbooks, 3 demo scenario fixtures, thresholds calibrated | 3 | 2 hrs |
| S7 | Frontend | React dashboard with live agent panel, timeline, brief panel, demo trigger buttons | 5 | 3 hrs |
| S8 | GCP Deployment | Both services on Cloud Run, full demo verified on live URLs | 3 | 2 hrs |

---

## Session 1 — Scaffold & State

**Goal:** A committed, runnable repository with correct structure, GCP ADC confirmed working, and all shared schemas defined and validated. No agent code, no graph. The session ends with a passing auth check and a Pydantic validation test.

**Integration check:**
```bash
cd backend && python tools/auth_check.py && python -m pytest tests/test_schemas.py -v
```
Must print `GCP auth: OK` and all schema tests green. Any failure here blocks Session 2.

---

### Task 1.1 — Repository scaffold

**Description:** Create the full directory structure, initialise Python and Node environments, create `.env.example`, add `.gitignore`. No code logic — structure only.

**CC prompt:**
```
Create the following directory and file structure for the Incident War Room project.
Create all directories. Create empty __init__.py files in every Python package directory.
Create a .gitignore that excludes .env, __pycache__, .chroma/, node_modules, dist.
Do not write any logic — empty files only except where specified.

Structure:
backend/
  graph/__init__.py  graph/nodes/__init__.py
  prompts/__init__.py  tools/__init__.py  tests/__init__.py
  fixtures/alerts/  fixtures/metrics/  fixtures/runbooks/
  main.py  config.py  store.py  requirements.txt
frontend/
  src/components/  src/hooks/  src/types/
deploy/

Create backend/requirements.txt with exactly these packages:
fastapi>=0.111.0, uvicorn[standard]>=0.30.0, langgraph>=0.2.0, langchain>=0.2.0,
langchain-google-vertexai>=1.0.0, langchain-community>=0.2.0, chromadb>=0.5.0,
pydantic>=2.0.0, python-dotenv>=1.0.0, sse-starlette>=2.0.0, httpx>=0.27.0,
pytest>=8.0.0, pytest-asyncio>=0.23.0

Create backend/.env.example with keys and placeholder values:
GCP_PROJECT_ID=your-project-id, GCP_LOCATION=us-central1,
GEMINI_MODEL=gemini-2.5-flash-lite, EMBEDDING_MODEL=text-embedding-004,
AUTO_RESOLVE_THRESHOLD=0.75, CONFIDENCE_THRESHOLD=0.7, SPREAD_THRESHOLD=0.4,
MEAN_FLOOR=0.5, SIMILARITY_THRESHOLD=0.65, MAX_LOOPS=2
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | All directories exist | `ls backend/graph/nodes/` exits 0 |
| TC-2 | requirements.txt present | `cat backend/requirements.txt` shows all 13 packages |
| TC-3 | .env.example present | All 10 keys present |
| TC-4 | .env excluded from git | `git check-ignore backend/.env` exits 0 |

**Verification command:**
```bash
ls backend/graph/nodes/__init__.py && \
grep "langgraph" backend/requirements.txt && \
grep "GCP_PROJECT_ID" backend/.env.example && \
git check-ignore backend/.env && \
echo "TASK 1.1 PASS"
```

**Invariant flags:** INV-011 (no credentials in .env.example — placeholder values only)

---

### Task 1.2 — Config and shared schemas

**Description:** Implement `config.py` (typed constants from `.env`), `backend/graph/state.py` (TypedDict schemas), and `backend/graph/models.py` (Pydantic v2 models with validators).

**CC prompt:**
```
Implement three files in backend/. Do not create any other files.

backend/config.py:
Load .env using python-dotenv. Expose these typed module-level constants:
  GCP_PROJECT_ID: str, GCP_LOCATION: str (default "us-central1"),
  GEMINI_MODEL: str (default "gemini-2.5-flash-lite"),
  EMBEDDING_MODEL: str (default "text-embedding-004"),
  AUTO_RESOLVE_THRESHOLD: float (default 0.75), CONFIDENCE_THRESHOLD: float (default 0.7),
  SPREAD_THRESHOLD: float (default 0.4), MEAN_FLOOR: float (default 0.5),
  SIMILARITY_THRESHOLD: float (default 0.65), MAX_LOOPS: int (default 2)

backend/graph/state.py:
Define using typing.TypedDict:
  AgentFinding: agent_id(str), status(Literal["success","no_match","timeout","error"]),
    root_cause(Optional[str]), confidence(float), justification(str),
    resolution_steps(list[str]), evidence(list[str]), timestamp(str)
  CommsDraft: status_page(str), slack_message(str), revised(bool)
  AlertPayload: alert_id(str), service_name(str), severity(Literal["P0","P1","P2","P3"]),
    error_type(str), log_snippet(str), timestamp(str)
  IncidentState: alert(AlertPayload), log_analysis(Optional[AgentFinding]),
    runbook_result(Optional[AgentFinding]), blast_radius(Optional[AgentFinding]),
    comms_drafts(Optional[CommsDraft]), conflict_detected(bool),
    conflict_reason(Optional[str]), loop_count(int),
    final_decision(Optional[Literal["auto_resolve","escalate","loop"]]),
    incident_brief(Optional[str]), resolution_plan(Optional[str])

backend/graph/models.py:
Define AgentFindingModel as Pydantic BaseModel mirroring AgentFinding TypedDict.
Add two field validators using @field_validator:
  confidence: raise ValueError if outside [0.0, 1.0]
  justification: raise ValueError if empty or whitespace-only
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Valid AgentFindingModel | No error raised |
| TC-2 | confidence = 1.5 | `ValidationError` raised |
| TC-3 | confidence = -0.1 | `ValidationError` raised |
| TC-4 | justification = "  " | `ValidationError` raised |
| TC-5 | justification = "" | `ValidationError` raised |

**Verification command:**
```bash
cd backend && python -c "
from graph.models import AgentFindingModel
from pydantic import ValidationError
m = AgentFindingModel(agent_id='x',status='success',confidence=0.9,justification='reason',resolution_steps=[],evidence=[],timestamp='t')
assert m.confidence == 0.9
for bad in [1.5, -0.1]:
    try: AgentFindingModel(agent_id='x',status='success',confidence=bad,justification='x',resolution_steps=[],evidence=[],timestamp='t'); assert False
    except ValidationError: pass
for bad_j in ['','   ']:
    try: AgentFindingModel(agent_id='x',status='success',confidence=0.5,justification=bad_j,resolution_steps=[],evidence=[],timestamp='t'); assert False
    except ValidationError: pass
print('TASK 1.2 PASS')
"
```

**Invariant flags:** INV-002 (typed state), INV-006 (Pydantic validators), INV-013 (confidence bounds), INV-015 (non-empty justification)

---

### Task 1.3 — GCP auth check script

**Description:** Implement `backend/tools/auth_check.py`. Makes a minimal Vertex AI call and asserts the response. Gate confirmation that ADC works before any agent code is written.

**CC prompt:**
```
Implement backend/tools/auth_check.py. Do not create any other files.
Import ChatVertexAI from langchain_google_vertexai and config values from config.
Initialise LLM with model=GEMINI_MODEL, project=GCP_PROJECT_ID, location=GCP_LOCATION.
Invoke with prompt "Reply with the single word: READY".
Assert "READY" in response.content (case-insensitive).
On failure: print actual response and exit code 1.
On success: print "GCP auth: OK" and exit code 0.
Do not use try/except — let auth errors surface naturally. Do not create other files.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Valid ADC credentials | Prints `GCP auth: OK`, exit 0 |
| TC-2 | GCP_PROJECT_ID missing | `KeyError` or `ValueError` surfaces — not silent hang |

**Verification command:**
```bash
cd backend && python tools/auth_check.py
```
Must print `GCP auth: OK`. If this fails, Session 1 is incomplete — do not proceed to Session 2.

**Invariant flags:** INV-011 (no credentials in code — ADC only)

---

### Task 1.4 — Schema tests

**Description:** Implement `backend/tests/test_schemas.py` with pytest tests covering all TypedDict structures and Pydantic validators.

**CC prompt:**
```
Implement backend/tests/test_schemas.py using pytest. Do not create other files.
All cases must be explicit test functions — not parametrised loops.

From graph.models import AgentFindingModel:
  test_valid_finding: confidence=0.85, asserts no error
  test_confidence_upper_bound: 1.0 passes; 1.001 raises ValidationError
  test_confidence_lower_bound: 0.0 passes; -0.001 raises ValidationError
  test_empty_justification: "" raises ValidationError
  test_whitespace_justification: "   " raises ValidationError
  test_no_match_zero_confidence: status="no_match", confidence=0.0 passes

From graph.state import IncidentState:
  test_incident_state_has_required_keys: assert all 11 expected keys present in TypedDict __annotations__
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | All 7 test functions | 0 failures |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_schemas.py -v && echo "TASK 1.4 PASS"
```

**Invariant flags:** INV-002, INV-006, INV-013, INV-015

---

## Session 2 — Graph Skeleton

**Goal:** A compilable, end-to-end runnable `StateGraph` with stub nodes. Every edge, fan-out, and routing function wired. Graph traverses from `parse_alert` to `END` without any real LLM call.

**Integration check:**
```bash
cd backend && python graph/graph.py && python -m pytest tests/test_graph_skeleton.py -v
```

---

### Task 2.1 — Stub node factory and routing functions

**Description:** Implement `backend/graph/nodes/_stub.py` (stub factory) and `backend/graph/routing.py` (both routing functions).

**CC prompt:**
```
Implement two files. Do not create any other files.

backend/graph/nodes/_stub.py:
Implement make_stub_node(agent_id, state_key, status="success", confidence=0.9).
Returns an async function that accepts a state dict and returns:
  {state_key: AgentFindingModel(agent_id=agent_id, status=status, root_cause="stub",
    confidence=confidence, justification="Stub node", resolution_steps=["stub step"],
    evidence=[], timestamp=datetime.now(timezone.utc).isoformat()).model_dump()}
Import AgentFindingModel from graph.models.

backend/graph/routing.py:
Implement fan_out_after_log(state) -> list[Send]:
  Import Send from langgraph.constants.
  Return exactly three Send objects:
    Send("runbook", {"log_finding": state["log_analysis"]})
    Send("blast_radius", {"alert": state["alert"]})
    Send("comms", {"alert": state["alert"]})    ← comms receives ONLY alert, not full state
  This is non-negotiable per INV-039.

Implement route_after_arbitration(state) -> str:
  Read state["final_decision"]:
    "auto_resolve" → return "auto_resolve"
    "escalate"     → return "escalate"
    "loop"         → return "log_analyst"
    anything else  → raise ValueError(f"Invalid final_decision: {state['final_decision']}")
  No business logic here — routing only.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `make_stub_node` called | Returns dict with correct state key |
| TC-2 | `fan_out_after_log` | Returns list of exactly 3 Send objects |
| TC-3 | comms Send arg | Contains only `"alert"` key — not full state |
| TC-4 | `route_after_arbitration("auto_resolve")` | Returns `"auto_resolve"` |
| TC-5 | `route_after_arbitration("loop")` | Returns `"log_analyst"` |
| TC-6 | `route_after_arbitration("invalid")` | Raises `ValueError` |

**Verification command:**
```bash
cd backend && python -c "
import asyncio
from graph.nodes._stub import make_stub_node
from graph.routing import fan_out_after_log, route_after_arbitration
node = make_stub_node('test','log_analysis')
r = asyncio.run(node({'alert':{},'log_analysis':None}))
assert 'log_analysis' in r
sends = fan_out_after_log({'log_analysis':{'root_cause':'x'},'alert':{'alert_id':'1'}})
assert len(sends) == 3
comms = next(s for s in sends if s.node == 'comms')
assert list(comms.arg.keys()) == ['alert'], f'Got: {comms.arg.keys()}'
assert route_after_arbitration({'final_decision':'auto_resolve'}) == 'auto_resolve'
assert route_after_arbitration({'final_decision':'loop'}) == 'log_analyst'
try: route_after_arbitration({'final_decision':'invalid'}); assert False
except ValueError: pass
print('TASK 2.1 PASS')
"
```

**Invariant flags:** INV-007, INV-009, INV-039

---

### Task 2.2 — Graph assembly

**Description:** Implement `backend/graph/graph.py` — `StateGraph` with stub nodes, all edges, both conditional edges. Must compile.

**CC prompt:**
```
Implement backend/graph/graph.py. Do not create any other files.

Build StateGraph(IncidentState). Register stub nodes:
  "parse_alert" → make_stub_node("parse_alert", "alert")
  "log_analyst" → make_stub_node("log_analyst", "log_analysis")
  "runbook"     → make_stub_node("runbook", "runbook_result")
  "blast_radius"→ make_stub_node("blast_radius", "blast_radius")
  "comms"       → make_stub_node("comms", "comms_drafts")
  "coordinator_arbiter" → async node that returns {"final_decision": "auto_resolve"}
  "auto_resolve"→ make_stub_node("auto_resolve", "resolution_plan")
  "escalate"    → make_stub_node("escalate", "incident_brief")

Edges (exact — do not deviate):
  entry → "parse_alert"
  "parse_alert" → "log_analyst"
  "log_analyst" → conditional: fan_out_after_log → ["runbook","blast_radius","comms"]
  "runbook","blast_radius","comms" → "coordinator_arbiter"
  "coordinator_arbiter" → conditional: route_after_arbitration → ["auto_resolve","escalate","log_analyst"]
  "auto_resolve","escalate" → END

graph = builder.compile() at module level.
if __name__ == "__main__": print("Graph compile: OK")
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `python graph/graph.py` | Prints `Graph compile: OK` |
| TC-2 | `graph.get_graph().nodes` | All 8 node names present |

**Verification command:**
```bash
cd backend && python graph/graph.py && echo "TASK 2.2 PASS"
```

**Invariant flags:** INV-007, INV-008

---

### Task 2.3 — Graph skeleton tests

**Description:** Implement `backend/tests/test_graph_skeleton.py` — async tests that invoke the stub graph and assert traversal and terminal state.

**CC prompt:**
```
Implement backend/tests/test_graph_skeleton.py using pytest and pytest-asyncio. Do not create other files.

Helper build_test_state() returns a minimal valid IncidentState dict with a real alert and all other keys None/False/0.

Tests (all async, @pytest.mark.asyncio):
test_graph_reaches_terminal_state: result["final_decision"] in ("auto_resolve","escalate")
test_log_analysis_populated: result["log_analysis"] is not None, agent_id == "log_analyst"
test_all_parallel_agents_populated: runbook_result, blast_radius, comms_drafts all non-None
test_loop_never_in_terminal: result["final_decision"] != "loop"
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Full graph invocation | `final_decision` in `("auto_resolve", "escalate")` |
| TC-2 | All parallel agents | All three findings non-None |
| TC-3 | Terminal state | `final_decision != "loop"` |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_graph_skeleton.py -v && echo "TASK 2.3 PASS"
```

**Invariant flags:** INV-018, INV-019

---

## Session 3 — Agent Nodes

**Goal:** All five agent nodes implemented with real Vertex AI calls, full error/timeout handling, and Pydantic validation on every output path. Each node tested in isolation.

**Integration check:**
```bash
cd backend && python -m pytest tests/test_agents.py -v
```
All mocked tests pass. No real Vertex AI calls in this test run.

---

### Task 3.1 — Log Analyst agent

**Description:** Implement `backend/graph/nodes/log_analyst.py` and `backend/prompts/log_analyst.py`. Real Vertex AI call, structured output, timeout, context enrichment on loops.

**CC prompt:**
```
Implement two files. Do not create others.

backend/prompts/log_analyst.py:
LOG_ANALYST_PROMPT string template with placeholders: {service}, {logs}, {extra_context}.
Instruct model to: identify the most anomalous pattern, classify root_cause as exactly one of
db_timeout|oom|network|auth|upstream|unknown, assign confidence 0.0-1.0
(>0.85=clear repeated error, 0.6-0.85=ambiguous, <0.6=insufficient/novel),
return ONLY valid JSON matching AgentFinding schema with no preamble.
If {extra_context} is non-empty, include it before forming the diagnosis.

backend/graph/nodes/log_analyst.py:
Module-level helpers:
  now_iso() → datetime.now(timezone.utc).isoformat()
  timeout_finding(agent_id) → dict with status="timeout", confidence=0.0, justification="Agent exceeded 30s timeout", resolution_steps=[], evidence=[], timestamp=now_iso()
  error_finding(agent_id, reason) → dict with status="error", confidence=0.0, justification=reason, resolution_steps=[], evidence=[], timestamp=now_iso()

async log_analyst_node(state: dict) -> dict:
  1. Build extra_context: non-empty only if loop_count > 0 AND runbook_result present
     Content: "PRIOR RUNBOOK SEARCH: status={status}, match={root_cause or 'none'}. Reconsider your diagnosis."
  2. Build prompt string
  3. asyncio.wait_for(llm.ainvoke(prompt), timeout=30.0)
     asyncio.TimeoutError → return {"log_analysis": timeout_finding("log_analyst")}
  4. json.loads(response.content)
     json.JSONDecodeError → return {"log_analysis": error_finding("log_analyst", str(e))}
  5. AgentFindingModel.model_validate(parsed)
     ValidationError → return {"log_analysis": error_finding("log_analyst", str(e))}
  6. return {"log_analysis": result.model_dump()}

llm = ChatVertexAI(model=GEMINI_MODEL, project=GCP_PROJECT_ID, location=GCP_LOCATION, temperature=0.1)
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Timeout (mocked) | `status="timeout"`, `confidence=0.0` |
| TC-2 | Invalid JSON from LLM (mocked) | `status="error"`, `confidence=0.0` |
| TC-3 | ValidationError (mocked bad confidence) | `status="error"` |
| TC-4 | loop_count=1, runbook_result set | prompt contains "PRIOR RUNBOOK SEARCH" |
| TC-5 | loop_count=0 | prompt does NOT contain "PRIOR RUNBOOK SEARCH" |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_agents.py::test_log_analyst_timeout tests/test_agents.py::test_log_analyst_invalid_json tests/test_agents.py::test_log_analyst_loop_context tests/test_agents.py::test_log_analyst_no_loop_context -v && echo "TASK 3.1 PASS"
```

**Invariant flags:** INV-006, INV-012, INV-013, INV-016, INV-028, INV-029, INV-041

---

### Task 3.2 — Runbook agent

**Description:** Implement `backend/graph/nodes/runbook.py` and `backend/prompts/runbook.py`. Queries ChromaDB, uses LLM only for step extraction from matched document.

**CC prompt:**
```
Implement two files. Do not create others.

backend/prompts/runbook.py:
STEP_EXTRACT_PROMPT with placeholder {document_text}.
Instruct model to extract ordered resolution steps as JSON array: ["step 1", "step 2", ...].
Return ONLY the JSON array — no preamble, no markdown.

backend/graph/nodes/runbook.py:
Module-level singleton vectorstore (do not re-initialise per call):
  embeddings = VertexAIEmbeddings(model_name=EMBEDDING_MODEL, project=GCP_PROJECT_ID, location=GCP_LOCATION)
  vectorstore = Chroma(collection_name="runbooks", embedding_function=embeddings)

Implement no_match_finding(reason) → dict with status="no_match", confidence=0.0, agent_id="runbook".

async runbook_node(state: dict) -> dict:
  1. log = state["log_analysis"]
     If log is None or log["status"] != "success": return no_match_finding("Log analysis not successful")
  2. query = f"{log['root_cause']} {' '.join(log['evidence'][:3])}"
  3. results = vectorstore.similarity_search_with_score(query, k=3)
  4. If not results or results[0][1] < SIMILARITY_THRESHOLD: return no_match_finding(f"No match above {SIMILARITY_THRESHOLD}")
  5. doc, score = results[0]
  6. asyncio.wait_for(step extraction LLM call, timeout=30.0) → parse JSON array as steps
     TimeoutError → return timeout_finding("runbook") (import from log_analyst)
  7. return AgentFindingModel(agent_id="runbook", status="success", root_cause=doc.metadata.get("title"),
       confidence=float(score), justification=f"Matched at {score:.2f}",
       resolution_steps=steps, evidence=[doc.page_content[:500]], timestamp=now_iso()).model_dump()
   wrapped in {"runbook_result": ...}
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | log status != "success" | `status="no_match"`, vectorstore not called |
| TC-2 | No results above threshold | `status="no_match"`, `confidence=0.0` |
| TC-3 | Match above threshold (mocked) | `status="success"`, `resolution_steps` non-empty |
| TC-4 | Step extraction timeout | `status="timeout"` |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_agents.py::test_runbook_no_match tests/test_agents.py::test_runbook_skipped tests/test_agents.py::test_runbook_success tests/test_agents.py::test_runbook_timeout -v && echo "TASK 3.2 PASS"
```

**Invariant flags:** INV-006, INV-012, INV-023, INV-029

---

### Task 3.3 — Blast Radius and Comms agents

**Description:** Implement blast radius and comms nodes with prompt files. Comms has two functions: `comms_node` (first pass, alert-only) and `revise_comms` (second pass, full state).

**CC prompt:**
```
Implement four files. Do not create others.

backend/prompts/blast_radius.py:
BLAST_RADIUS_PROMPT with placeholders {service_name} and {metrics_json}.
Instruct model to return ONLY JSON matching AgentFinding schema where evidence[0]
is a JSON string with keys: affected_users, regions, downstream_services, severity_tier, revenue_per_minute.

backend/graph/nodes/blast_radius.py:
load_metrics(service_name) → reads fixtures/metrics/metrics_mock.json, returns entry or default zeros.
async blast_radius_node(state: dict) -> dict:
  metrics = load_metrics(state["alert"]["service_name"])
  LLM call with BLAST_RADIUS_PROMPT, asyncio.wait_for 30s, validate with AgentFindingModel.
  Return {"blast_radius": result.model_dump()} or timeout/error finding.

backend/prompts/comms.py:
COMMS_INITIAL_PROMPT with {alert_json} — draft from alert metadata only. No findings, no root cause.
COMMS_REVISE_PROMPT with {current_draft}, {root_cause}, {blast_summary}, {final_decision}.

backend/graph/nodes/comms.py:
async comms_node(state: dict) -> dict:
  state contains ONLY {"alert": AlertPayload} — access only state["alert"].
  LLM call returns JSON {"status_page": "...", "slack_message": "..."}.
  Return {"comms_drafts": {"status_page":..., "slack_message":..., "revised": False}}
  On any error: return {"comms_drafts": {"status_page":"Draft unavailable","slack_message":"Draft unavailable","revised":False}}

async revise_comms(state: dict) -> dict:
  Access state["log_analysis"]["root_cause"], state["blast_radius"]["evidence"][0], state["final_decision"].
  LLM call with COMMS_REVISE_PROMPT.
  Return {"comms_drafts": {updated draft, "revised": True}}
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `comms_node` with alert-only state | Returns `revised=False` |
| TC-2 | `revise_comms` called | Returns `revised=True` |
| TC-3 | `blast_radius_node` timeout | Returns `status="timeout"` |
| TC-4 | `blast_radius_node` success | `evidence[0]` is valid JSON string |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_agents.py::test_comms_initial tests/test_agents.py::test_comms_revised tests/test_agents.py::test_blast_radius_timeout tests/test_agents.py::test_blast_radius_success -v && echo "TASK 3.3 PASS"
```

**Invariant flags:** INV-029, INV-038, INV-039

---

### Task 3.4 — Parse alert node

**Description:** Implement `backend/graph/nodes/parse_alert.py`. No LLM call. Normalises severity, initialises all state fields.

**CC prompt:**
```
Implement backend/graph/nodes/parse_alert.py. Do not create other files.

async parse_alert_node(state: dict) -> dict:
  Return a dict setting:
  - "alert": copy of state["alert"] with severity uppercased
  - "loop_count": 0
  - "conflict_detected": False
  - "conflict_reason": None
  - "log_analysis","runbook_result","blast_radius","comms_drafts": None
  - "final_decision","incident_brief","resolution_plan": None
  No LLM calls. No payload validation (that is the API layer's job).
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | severity "p1" (lowercase input) | Returns "P1" |
| TC-2 | loop_count initialised | `result["loop_count"] == 0` |
| TC-3 | log_analysis initialised | `result["log_analysis"] is None` |

**Verification command:**
```bash
cd backend && python -c "
import asyncio
from graph.nodes.parse_alert import parse_alert_node
r = asyncio.run(parse_alert_node({'alert':{'alert_id':'x','service_name':'s','severity':'p1','error_type':'e','log_snippet':'l','timestamp':'t'}}))
assert r['alert']['severity']=='P1' and r['loop_count']==0 and r['log_analysis'] is None
print('TASK 3.4 PASS')
"
```

**Invariant flags:** INV-007

---

### Task 3.5 — Agent isolation tests

**Description:** Implement `backend/tests/test_agents.py` with mocked tests for all agent nodes covering happy path, timeout, and validation error paths.

**CC prompt:**
```
Implement backend/tests/test_agents.py using pytest and pytest-asyncio.
Use unittest.mock.patch and AsyncMock to mock LLM calls and vectorstore.
All tests use mocks — no real Vertex AI calls permitted.

test_log_analyst_timeout: patch llm.ainvoke to raise asyncio.TimeoutError → status="timeout", confidence=0.0
test_log_analyst_invalid_json: patch llm to return "not json" → status="error"
test_log_analyst_loop_context: call with loop_count=1, runbook_result set → captured prompt contains "PRIOR RUNBOOK SEARCH"
test_log_analyst_no_loop_context: call with loop_count=0 → prompt does NOT contain "PRIOR RUNBOOK SEARCH"
test_runbook_no_match: mock vectorstore empty results → status="no_match"
test_runbook_skipped: log_analysis.status="error" → status="no_match", vectorstore not called
test_runbook_success: mock vectorstore score=0.8, mock step LLM → status="success", resolution_steps non-empty
test_runbook_timeout: mock step LLM to TimeoutError → status="timeout"
test_blast_radius_timeout: mock LLM TimeoutError → status="timeout"
test_blast_radius_success: mock LLM valid response → status="success", evidence[0] valid JSON
test_comms_initial: call comms_node with only alert → revised=False
test_comms_revised: call revise_comms with full mocked state → revised=True
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | All 12 test functions | 0 failures, fast (no real API calls) |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_agents.py -v && echo "TASK 3.5 PASS"
```

**Invariant flags:** INV-004, INV-006, INV-012, INV-028, INV-029, INV-039, INV-041

---

## Session 4 — Coordinator Arbiter

**Goal:** Real `coordinator_arbiter_node` with all four conflict rules, loop logic, and all four decision paths. Full end-to-end integration with real nodes. All three demo scenario outcomes verifiable.

**Integration check:**
```bash
cd backend && python -m pytest tests/test_coordinator.py tests/test_integration.py -v
```

---

### Task 4.1 — Conflict detection and resolution helpers

**Description:** Implement helpers in `backend/graph/nodes/coordinator_arbiter.py`: `detect_conflict`, `can_auto_resolve`, `build_incident_brief`. Not the node itself — helpers only, tested in isolation first.

**CC prompt:**
```
Implement helper functions only in backend/graph/nodes/coordinator_arbiter.py.
Do not implement coordinator_arbiter_node yet. Do not create other files.

detect_conflict(log: dict, rb: dict, br: dict, severity: str) -> tuple[bool, Optional[str]]:
  Apply exactly four rules in this order (first match wins):
  Rule 1: log["confidence"] >= CONFIDENCE_THRESHOLD AND rb["status"] == "no_match"
    → True, "Log Analyst confident ({:.2f}) in '{}' but Runbook returned no_match."
  Rule 2: abs(log["confidence"] - br["confidence"]) > SPREAD_THRESHOLD
    → True, "Confidence spread too high: Log={:.2f}, BlastRadius={:.2f}."
  Rule 3: severity == "P0" AND any(f["status"] in ("error","timeout") for f in [log,rb,br])
    → True, "P0 incident with agent error or timeout."
  Rule 4: mean([log["conf"],rb["conf"],br["conf"]]) < MEAN_FLOOR
    → True, "Mean confidence {:.2f} below floor {}."
  else: return False, None

can_auto_resolve(log: dict, rb: dict, br: dict) -> bool:
  Return True only if ALL of:
  1. rb["status"] == "success"
  2. len(rb.get("resolution_steps",[])) > 0
  3. mean([log["confidence"],rb["confidence"],br["confidence"]]) >= AUTO_RESOLVE_THRESHOLD

build_incident_brief(state: dict, decision: str) -> str:
  Synchronous. No LLM call.
  Return formatted markdown string with: alert summary, decision, conflict reason,
  loop_count, log finding, runbook status, blast radius evidence, comms draft status_page.

Import CONFIDENCE_THRESHOLD, SPREAD_THRESHOLD, MEAN_FLOOR, AUTO_RESOLVE_THRESHOLD from config.
Import statistics.mean.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Rule 1: log conf 0.8, runbook no_match | `(True, reason)` mentioning log confidence |
| TC-2 | Rule 2: spread > 0.4 | `(True, reason)` |
| TC-3 | Rule 3: P0 + agent error | `(True, reason)` |
| TC-4 | Rule 4: mean < 0.5 | `(True, reason)` |
| TC-5 | No rules fire | `(False, None)` |
| TC-6 | `can_auto_resolve` runbook no_match | Returns `False` |
| TC-7 | `can_auto_resolve` empty steps | Returns `False` |
| TC-8 | `can_auto_resolve` all conditions met | Returns `True` |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_coordinator.py::test_conflict_rule_1 tests/test_coordinator.py::test_conflict_rule_2 tests/test_coordinator.py::test_conflict_rule_3 tests/test_coordinator.py::test_conflict_rule_4 tests/test_coordinator.py::test_no_conflict tests/test_coordinator.py::test_can_auto_resolve -v && echo "TASK 4.1 PASS"
```

**Invariant flags:** INV-020, INV-021, INV-022, INV-023, INV-024, INV-032, INV-033, INV-034

---

### Task 4.2 — Coordinator arbiter node

**Description:** Add `coordinator_arbiter_node` to the same file, implementing all four decision paths and calling `revise_comms`.

**CC prompt:**
```
Add coordinator_arbiter_node to backend/graph/nodes/coordinator_arbiter.py.
Do not modify helpers from Task 4.1. Do not create other files.

async coordinator_arbiter_node(state: dict) -> dict:
  log, rb, br = state["log_analysis"], state["runbook_result"], state["blast_radius"]
  loop, severity = state.get("loop_count", 0), state["alert"]["severity"]

  conflict, reason = detect_conflict(log, rb, br, severity)

  # Path 1: conflict + loops remaining
  if conflict and loop < MAX_LOOPS:
    return {"conflict_detected":True,"conflict_reason":reason,"loop_count":loop+1,"final_decision":"loop"}

  # Path 2: conflict + max loops exhausted
  if conflict and loop >= MAX_LOOPS:
    return {"conflict_detected":True,"conflict_reason":reason,"loop_count":loop,
            "final_decision":"escalate","incident_brief":build_incident_brief(state,"escalate")}

  # Path 3: no conflict + auto-resolve conditions met
  if can_auto_resolve(log, rb, br):
    revised = await revise_comms(state)
    return {"conflict_detected":False,"final_decision":"auto_resolve",
            "resolution_plan":"\n".join(f"{i+1}. {s}" for i,s in enumerate(rb["resolution_steps"])),
            "incident_brief":build_incident_brief(state,"auto_resolve"),
            "comms_drafts":revised["comms_drafts"]}

  # Path 4: no conflict + low confidence (INV-020)
  return {"conflict_detected":False,"final_decision":"escalate",
          "incident_brief":build_incident_brief(state,"escalate")}

Import revise_comms from graph.nodes.comms. Import MAX_LOOPS from config.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Conflict, loop_count=0 | `final_decision="loop"`, `loop_count=1` |
| TC-2 | Conflict, loop_count=2 | `final_decision="escalate"`, `incident_brief` set |
| TC-3 | No conflict, auto-resolve conditions met | `final_decision="auto_resolve"`, `resolution_plan` set |
| TC-4 | No conflict, mean conf < 0.75 | `final_decision="escalate"` |
| TC-5 | `loop_count` never exceeds MAX_LOOPS | Confirmed by TC-2 path |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_coordinator.py -v && echo "TASK 4.2 PASS"
```

**Invariant flags:** INV-017, INV-018, INV-019, INV-020, INV-025, INV-026, INV-027, INV-032, INV-033

---

### Task 4.3 — Wire real nodes into graph

**Description:** Replace all stubs in `graph.py` with real implementations.

**CC prompt:**
```
Modify backend/graph/graph.py only. Do not create other files.
Replace all make_stub_node calls with real imports:
  from graph.nodes.parse_alert import parse_alert_node
  from graph.nodes.log_analyst import log_analyst_node
  from graph.nodes.runbook import runbook_node
  from graph.nodes.blast_radius import blast_radius_node
  from graph.nodes.comms import comms_node
  from graph.nodes.coordinator_arbiter import coordinator_arbiter_node
Keep all edge definitions identical — do not change any edges.
if __name__ == "__main__": print("Graph compile: OK") must remain.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `python graph/graph.py` | Prints `Graph compile: OK` |
| TC-2 | Skeleton tests | All still pass |

**Verification command:**
```bash
cd backend && python graph/graph.py && python -m pytest tests/test_graph_skeleton.py -v && echo "TASK 4.3 PASS"
```

**Invariant flags:** INV-007, INV-010

---

### Task 4.4 — End-to-end integration tests

**Description:** Implement `backend/tests/test_integration.py` — full graph invocations with all LLM calls mocked to reproduce all three scenario outcomes deterministically.

**CC prompt:**
```
Implement backend/tests/test_integration.py using pytest and pytest-asyncio.
All LLM and vectorstore calls mocked — no real Vertex AI calls.

Create mock helpers that patch ChatVertexAI.ainvoke to return pre-defined JSON:
  auto_resolve_mocks: log confident (0.91, db_timeout), runbook match (0.88), blast radius ok
  conflict_escalate_mocks: log confident (0.82, oom), runbook no_match on all queries

test_scenario_auto_resolve:
  Apply auto_resolve_mocks. Mock vectorstore to return Document(title="DB Pool Recovery", score=0.88).
  Assert final_decision=="auto_resolve", loop_count==0, resolution_plan non-None, incident_brief non-None.

test_scenario_conflict_escalate:
  Apply conflict_escalate_mocks. Mock vectorstore to return empty results.
  Assert final_decision=="escalate", conflict_detected==True, conflict_reason non-None, loop_count==2.

test_loop_never_terminal:
  Run auto_resolve and conflict_escalate scenarios. Assert final_decision != "loop" for each.

test_incident_brief_always_set:
  Run both scenarios. Assert incident_brief is not None and len > 0 for each.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Auto-resolve mock | `final_decision="auto_resolve"`, `loop_count=0` |
| TC-2 | Conflict escalate mock | `final_decision="escalate"`, `conflict_detected=True`, `loop_count=2` |
| TC-3 | Any scenario | `final_decision != "loop"` at END |
| TC-4 | Any scenario | `incident_brief` non-None and non-empty |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_integration.py -v && echo "TASK 4.4 PASS"
```

**Invariant flags:** INV-018, INV-019, INV-025, INV-033, INV-044

---

## Session 5 — API & SSE

**Goal:** FastAPI server running with all endpoints, SSE stream delivering live agent events, deduplication working, demo trigger firing all three scenarios.

**Integration check:**
```bash
cd backend && uvicorn main:app --port 8000 --workers 1 &
sleep 3
curl -sf http://localhost:8000/health | python3 -c "import sys,json; assert json.load(sys.stdin)['status']=='ok'" && \
curl -sf -X POST http://localhost:8000/demo/trigger/scenario_a | python3 -c "import sys,json; assert 'incident_id' in json.load(sys.stdin)" && \
echo "SESSION 5 INTEGRATION PASS"
kill %1
```

---

### Task 5.1 — In-memory store and SSE publisher

**Description:** Implement `backend/store.py` (incident dict, SSE queues, dedup index) and `backend/sse.py` (async publisher, LangGraph event mapper).

**CC prompt:**
```
Implement two files. Do not create others.

backend/store.py:
Module-level dicts (not a class):
  incidents: dict[str,dict] = {}
  sse_queues: dict[str,asyncio.Queue] = {}
  dedup_index: dict[tuple,str] = {}        # (service_name,error_type) → incident_id
  dedup_timestamps: dict[str,float] = {}   # incident_id → unix timestamp

Functions:
  create_incident(id, state): store in incidents, create asyncio.Queue in sse_queues
  update_incident(id, partial): merge partial dict into stored state
  get_incident(id) → dict|None
  get_all_incidents() → list[dict]
  check_dedup(service_name, error_type, window_seconds=300) → str|None:
    If (service_name,error_type) in dedup_index AND time.time()-dedup_timestamps[id] < window_seconds: return id
    else: return None
  register_dedup(service_name, error_type, id): store entry and current timestamp

backend/sse.py:
async publish(incident_id, event: dict): queue.put_nowait(event) if queue exists.
map_langgraph_event(raw: dict) -> dict|None:
  on_chain_start where name in known node names → {"event":"node_start","node":name,"timestamp":now_iso()}
  on_chain_end where name in known node names → {"event":"node_complete","node":name, include confidence/status if in output}
  Return None for irrelevant events.
Known node names: parse_alert,log_analyst,runbook,blast_radius,comms,coordinator_arbiter,auto_resolve,escalate
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `create_incident` then `get_incident` | Returns stored state |
| TC-2 | `check_dedup` within window | Returns existing `incident_id` |
| TC-3 | `check_dedup` after window expired | Returns `None` |
| TC-4 | `publish` puts on queue | `queue.get_nowait()` returns the event |

**Verification command:**
```bash
cd backend && python -c "
import asyncio, time
from store import create_incident, get_incident, check_dedup, register_dedup
create_incident('t1',{'alert':{'service_name':'s','error_type':'e'}})
assert get_incident('t1') is not None
register_dedup('s','e','t1')
assert check_dedup('s','e') == 't1'
print('TASK 5.1 PASS')
"
```

**Invariant flags:** INV-036

---

### Task 5.2 — FastAPI application

**Description:** Implement `backend/main.py` with all six routes: health, webhook, incidents list/detail, SSE stream, demo trigger.

**CC prompt:**
```
Implement backend/main.py. Add comment at top: "# Run with --workers 1 only. See ARCHITECTURE.md §10."
Do not create other files.

Create FastAPI app. Add startup event that seeds vectorstore if not already seeded.

Define AlertPayloadRequest as Pydantic BaseModel (not TypedDict) with same fields as AlertPayload.

Endpoints:
GET /health → {"status":"ok"}

POST /webhook/alert (body: AlertPayloadRequest):
  1. dedup = check_dedup(service_name, error_type)
     if dedup: return {"incident_id":dedup,"deduplicated":True,"stream_url":f"/incidents/{dedup}/stream"}
  2. incident_id = str(uuid4())
  3. Build initial IncidentState dict with all agent keys None, loop_count=0, conflict_detected=False
  4. create_incident(incident_id, state), register_dedup(service_name, error_type, incident_id)
  5. background_tasks.add_task(run_graph_task, incident_id, state)
  6. return {"incident_id":incident_id,"stream_url":f"/incidents/{incident_id}/stream","deduplicated":False}

GET /incidents → list of all incidents (all fields)
GET /incidents/{id} → full state or 404

GET /incidents/{id}/stream:
  EventSourceResponse from sse_starlette.
  Async generator: loop reading from sse_queues[id] until None sentinel.
  yield {"data": json.dumps(event)} per event.

POST /demo/trigger/{scenario} where scenario in ("scenario_a","scenario_b","scenario_c"):
  Map names: scenario_a→scenario_a_db_pool, scenario_b→scenario_b_oom, scenario_c→scenario_c_auth_dns
  Load fixtures/alerts/{mapped_name}.json, construct AlertPayloadRequest, invoke webhook logic directly.

async run_graph_task(incident_id, state):
  async for event in graph.astream_events(state, version="v2"):
    sse_event = map_langgraph_event(event)
    if sse_event: await publish(incident_id, sse_event)
    if event.get("event") == "on_chain_end":
      output = event.get("data",{}).get("output",{})
      if output: update_incident(incident_id, output)
  await publish(incident_id, {"event":"decision","decision":get_incident(incident_id).get("final_decision"),"timestamp":now_iso()})
  await publish(incident_id, {"event":"done","timestamp":now_iso()})
  sse_queues[incident_id].put_nowait(None)
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `GET /health` | `{"status":"ok"}`, HTTP 200 |
| TC-2 | `POST /webhook/alert` missing `log_snippet` | HTTP 422 |
| TC-3 | `POST /webhook/alert` valid | Returns `incident_id` and `stream_url` |
| TC-4 | Same alert twice within 5 min | Second response: `deduplicated=True`, same `incident_id` |
| TC-5 | `POST /demo/trigger/scenario_a` | Returns `incident_id` |
| TC-6 | `GET /incidents/{id}` after trigger | Returns state with `alert` populated |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_api.py -v && echo "TASK 5.2 PASS"
```

**Invariant flags:** INV-035, INV-036, INV-037

---

### Task 5.3 — API tests

**Description:** Implement `backend/tests/test_api.py` using FastAPI TestClient with mocked graph.

**CC prompt:**
```
Implement backend/tests/test_api.py using pytest and FastAPI TestClient.
Mock graph.astream_events and graph.ainvoke to avoid real Vertex AI.

test_health, test_webhook_missing_field (422), test_webhook_valid (incident_id returned),
test_deduplication (second call deduplicated=True same incident_id),
test_demo_trigger_scenario_a (returns incident_id), test_get_incident (state returned),
test_severity_p2_routing: POST P2 alert; assert only log_analyst node fires (check SSE events or mock call count).
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | All 7 functions | 0 failures |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_api.py -v && echo "TASK 5.3 PASS"
```

**Invariant flags:** INV-035, INV-036, INV-037

---

### Task 5.4 — Alert and metrics fixtures

**Description:** Create the three scenario alert JSON fixtures and the metrics mock file.

**CC prompt:**
```
Create exactly these four files. No others.

backend/fixtures/alerts/scenario_a_db_pool.json:
{"alert_id":"demo-scenario-a","service_name":"payments-api","severity":"P1",
 "error_type":"connection_pool_timeout",
 "log_snippet":"ERROR [payments-api] HikariPool-1 - Connection not available, timed out after 30000ms\nERROR [payments-api] Unable to acquire JDBC Connection\nWARN  [payments-api] HikariPool stats: total=10, active=10, idle=0, waiting=47",
 "timestamp":"2026-03-23T14:32:00Z"}

backend/fixtures/alerts/scenario_b_oom.json:
{"alert_id":"demo-scenario-b","service_name":"user-service","severity":"P0",
 "error_type":"out_of_memory",
 "log_snippet":"java.lang.OutOfMemoryError: GC overhead limit exceeded\n\tat com.example.UserService.processRequest(UserService.java:142)\nERROR [user-service] 3 pods OOM killed in last 5 minutes",
 "timestamp":"2026-03-23T15:10:00Z"}

backend/fixtures/alerts/scenario_c_auth_dns.json:
{"alert_id":"demo-scenario-c","service_name":"auth-service","severity":"P1",
 "error_type":"upstream_connect_error",
 "log_snippet":"upstream connect error or disconnect/reset before headers. reset reason: connection failure\nERROR [auth-service] DNS resolution failed for identity-provider.internal\nWARN  [auth-service] 5xx rate: 12% over 3 minutes",
 "timestamp":"2026-03-23T16:45:00Z"}

backend/fixtures/metrics/metrics_mock.json:
{"payments-api":{"error_rate_5m":0.082,"p99_latency_ms":4200,"affected_users_10m":1200,"regions":["eu-west-1","eu-central-1"],"downstream_services":["order-service","notification-service"],"estimated_revenue_per_minute":4200},
 "user-service":{"error_rate_5m":0.31,"p99_latency_ms":8900,"affected_users_10m":8400,"regions":["us-east-1","eu-west-1","ap-southeast-1"],"downstream_services":["payments-api","cart-service"],"estimated_revenue_per_minute":12000},
 "auth-service":{"error_rate_5m":0.12,"p99_latency_ms":3100,"affected_users_10m":4100,"regions":["eu-west-1"],"downstream_services":["all"],"estimated_revenue_per_minute":8500}}
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | All four files valid JSON | `python -c "import json; json.load(open(f))"` exits 0 for each |

**Verification command:**
```bash
cd backend && python -c "
import json
for f in ['fixtures/alerts/scenario_a_db_pool.json','fixtures/alerts/scenario_b_oom.json','fixtures/alerts/scenario_c_auth_dns.json','fixtures/metrics/metrics_mock.json']:
    json.load(open(f)); print(f'OK: {f}')
print('TASK 5.4 PASS')
"
```

**Invariant flags:** INV-043, INV-044

---

## Session 6 — Vector Store & Runbook Fixtures

**Goal:** ChromaDB seeded with 15 runbook documents. Thresholds calibrated. Scenario B intentionally has no matching runbook.

**Integration check:**
```bash
cd backend && python tools/vectorstore.py --seed && python tools/vectorstore.py --calibrate
```
Calibration output must show: db_timeout >= 0.65, OOM < 0.65, DNS >= 0.65.

---

### Task 6.1 — Runbook documents

**Description:** Create 15 Markdown runbook files. Scenario A match (`db_pool_recovery.md`) and scenario C match (`dns_resolution.md`) must score above threshold. No OOM runbook may exist (scenario B conflict requires this).

**CC prompt:**
```
Create exactly 15 Markdown files in backend/fixtures/runbooks/.
Each must have YAML frontmatter (between --- markers): title, category, service_tags (list), last_updated.
Each must have sections: ## Symptoms, ## Root Cause, ## Resolution Steps (numbered list), ## Verification.

Required files:
1. db_pool_recovery.md — "DB Connection Pool Recovery", database, [payments-api,orders-api]
   Steps: check pool metrics, kubectl rollout restart, increase pool size config
2. dns_resolution.md — "DNS Resolution Failure", network, [auth-service,api-gateway]
   Steps: check CoreDNS pods, flush DNS cache, verify service DNS entries
3. auth_service_restart.md — "Auth Service Graceful Restart", auth, [auth-service]
4. network_degradation.md, 5. cache_eviction_storm.md, 6. disk_pressure.md,
7. cert_expiry.md, 8. rate_limit_breach.md, 9. kafka_consumer_lag.md,
10. redis_memory_pressure.md, 11. pod_crashloop.md, 12. hpa_scaling_failure.md,
13. upstream_timeout.md, 14. db_replica_lag.md, 15. ingress_503.md

CRITICAL: Do NOT create any runbook about Java OOM, GC overhead, heap pressure,
or OutOfMemoryError. Scenario B must produce no_match. This is intentional.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Exactly 15 files | `ls fixtures/runbooks/*.md \| wc -l` = 15 |
| TC-2 | No OOM runbook | `grep -ri "outofmemory\|gc overhead\|java heap" fixtures/runbooks/` returns nothing |

**Verification command:**
```bash
cd backend && \
[ $(ls fixtures/runbooks/*.md | wc -l) -eq 15 ] && \
! grep -riq "outofmemory\|gc overhead\|java heap" fixtures/runbooks/ && \
echo "TASK 6.1 PASS"
```

**Invariant flags:** INV-023 (no_match for scenario B is intentional), INV-044

---

### Task 6.2 — Vector store seeder and calibration

**Description:** Implement `backend/tools/vectorstore.py` with seed, get_vectorstore singleton, and threshold calibration.

**CC prompt:**
```
Implement backend/tools/vectorstore.py. Do not create other files.

_vectorstore = None  # module-level singleton

get_vectorstore() -> Chroma:
  If _vectorstore is None: initialise with VertexAIEmbeddings(text-embedding-004) and Chroma("runbooks").
  Return _vectorstore.

seed_vectorstore() -> int:
  For each .md in fixtures/runbooks/: parse YAML frontmatter, create Document with metadata.
  vectorstore.add_documents(docs). Return len(docs).

calibrate():
  Queries to run and print scores for:
    "db_timeout connection pool timeout HikariPool"
    "OutOfMemoryError GC overhead limit exceeded JVM heap"  
    "DNS resolution failed upstream connect error"
  For each: print top match title, score, PASS/FAIL vs SIMILARITY_THRESHOLD.

if __name__ == "__main__":
  --seed: print f"Seeded {seed_vectorstore()} documents"
  --calibrate: calibrate()
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `--seed` | Prints `Seeded 15 documents` |
| TC-2 | db_timeout calibration | Score >= 0.65, match is db_pool_recovery |
| TC-3 | OOM calibration | Score < 0.65 for all results |
| TC-4 | DNS calibration | Score >= 0.65, match is dns_resolution |

**Verification command:**
```bash
cd backend && python tools/vectorstore.py --seed && python tools/vectorstore.py --calibrate && echo "TASK 6.2 PASS"
```
Manually verify calibration output confirms TC-2 through TC-4 before signing off.

**Invariant flags:** INV-008, INV-023, INV-034

---

### Task 6.3 — Scenario regression tests (slow)

**Description:** Implement `backend/tests/test_scenarios.py` — full graph invocations against real Vertex AI. Run manually before each demo, not in CI.

**CC prompt:**
```
Implement backend/tests/test_scenarios.py and backend/tests/conftest.py. No other files.

conftest.py:
  def pytest_addoption(parser): parser.addoption("--slow", action="store_true", default=False)
  def pytest_collection_modifyitems(config, items):
    if not config.getoption("--slow"):
      skip_slow = pytest.mark.skip(reason="Use --slow to run")
      for item in items:
        if "slow" in item.keywords: item.add_marker(skip_slow)

test_scenarios.py:
  load_fixture(name): reads fixtures/alerts/{name}.json, builds full IncidentState dict.

  @pytest.mark.slow
  test_scenario_a: final_decision=="auto_resolve", loop_count==0, resolution_plan non-None
  test_scenario_b: final_decision=="escalate", conflict_detected==True, conflict_reason non-None
  test_all_no_loop_terminal: all three scenarios, assert final_decision != "loop"
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Scenario A (real LLM) | `final_decision="auto_resolve"` |
| TC-2 | Scenario B (real LLM) | `final_decision="escalate"`, `conflict_detected=True` |
| TC-3 | All scenarios | `final_decision != "loop"` |

**Verification command:**
```bash
cd backend && python -m pytest tests/test_scenarios.py --slow -v -s && echo "TASK 6.3 PASS"
```

**Invariant flags:** INV-019, INV-044

---

## Session 7 — Frontend

**Goal:** React dashboard with live agent panel, SSE-driven updates, brief display, and demo trigger buttons. All three scenarios visually demonstrable.

**Integration check:**
```bash
cd frontend && npm run build 2>&1 | tail -3 && echo "Frontend build: OK"
```

---

### Task 7.1 — TypeScript types and SSE hook

**Description:** Create `frontend/src/types/incident.ts` and `frontend/src/hooks/useIncidentStream.ts`.

**CC prompt:**
```
Implement two files. Do not create others.

frontend/src/types/incident.ts:
Export: AgentId, AgentStatus, FinalDecision, AgentFinding, CommsDraft, IncidentSummary, StreamEvent.
AgentStatus = "idle"|"running"|"success"|"no_match"|"timeout"|"error"|"conflict"
FinalDecision = "auto_resolve"|"escalate"|"loop"|null

frontend/src/hooks/useIncidentStream.ts:
useIncidentStream(incidentId: string|null) returns {events, agentStatuses, finalDecision, isComplete}
EventSource on /api/incidents/{id}/stream.
node_start → agentStatuses[node]="running"
node_complete → agentStatuses[node]=event.status or "success"
conflict → agentStatuses["coordinator_arbiter"]="conflict"
decision → set finalDecision
done → isComplete=true, close EventSource
null incidentId → no EventSource, empty state.
Return cleanup closing EventSource on unmount.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `npm run build` | No TypeScript errors |
| TC-2 | null incidentId | No EventSource created |

**Verification command:**
```bash
cd frontend && npm run build && echo "TASK 7.1 PASS"
```

**Invariant flags:** —

---

### Task 7.2 — Agent status panel and confidence bar

**Description:** Implement `AgentStatusPanel.tsx` and `ConfidenceBar.tsx`.

**CC prompt:**
```
Implement two files using React and TailwindCSS. No inline styles. Do not create others.

ConfidenceBar.tsx: Props {confidence: number|null, label: string}
  Progress bar. Width=confidence*100%. Color: green>=0.75, amber 0.5-0.74, red<0.5|null.
  Show numeric value to 2dp. Animate with transition-all duration-500.

AgentStatusPanel.tsx: Props {agentStatuses: Record<string,AgentStatus>, findings: Record<string,any>}
  2x2 grid: Log Analyst, Runbook, Blast Radius, Comms. Plus Coordinator below.
  Each tile: agent name, status badge (idle=gray, running=amber animate-pulse, success=green,
    no_match=orange, error|timeout=red, conflict=red bold border), ConfidenceBar when findings present.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `npm run build` | No errors |

**Verification command:**
```bash
cd frontend && npm run build && echo "TASK 7.2 PASS"
```

**Invariant flags:** —

---

### Task 7.3 — Timeline, brief panel, comms panel

**Description:** Implement `TimelineView.tsx`, `BriefPanel.tsx`, `CommsPanel.tsx`.

**CC prompt:**
```
Implement three files. TailwindCSS only — no inline styles. Do not create others.

TimelineView.tsx: Props {events: StreamEvent[]}
  Chronological list. conflict/loop events: red left border, bold. decision event: green/red highlight.

BriefPanel.tsx: Props {incidentBrief, resolutionPlan, finalDecision}
  auto_resolve: numbered checklist of resolution steps above brief.
  escalate: red banner "Escalated to on-call engineer" above brief.
  Both null: gray placeholder "Awaiting agent findings..."
  Render brief as pre-formatted monospace text.

CommsPanel.tsx: Props {commsDraft: CommsDraft|null}
  Two tabs: Status Page, Slack Message. Read-only textarea per tab.
  "Revised" green badge if revised==true. Placeholder if null.
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `npm run build` | No errors |

**Verification command:**
```bash
cd frontend && npm run build && echo "TASK 7.3 PASS"
```

**Invariant flags:** INV-018 (`"loop"` never shown as final decision text)

---

### Task 7.4 — Demo trigger, incident feed, App.tsx

**Description:** Implement `DemoTrigger.tsx`, `IncidentFeed.tsx`, and `App.tsx`.

**CC prompt:**
```
Implement three files. TailwindCSS only. Do not create others.

DemoTrigger.tsx: Three buttons for scenario_a/b/c. POST to /api/demo/trigger/{scenario}.
  On success: call onIncidentCreated(incident_id) prop. Loading state on clicked button.

IncidentFeed.tsx: Props {onSelectIncident, selectedId}
  GET /api/incidents, poll every 3s. List with service_name, severity badge, final_decision badge.
  Highlight selected. Click → onSelectIncident.

App.tsx:
  Left sidebar 280px: DemoTrigger + IncidentFeed.
  Main: when selectedId set → AgentStatusPanel + TimelineView + BriefPanel + CommsPanel fed from useIncidentStream.
  When no selection: "Select or trigger an incident to begin".
  VITE_API_URL env var prefixes all fetch calls (empty default for local dev).
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `npm run build` | No errors |
| TC-2 | No incident selected | Placeholder text rendered |

**Verification command:**
```bash
cd frontend && npm run build && echo "TASK 7.4 PASS"
```

**Invariant flags:** INV-043

---

### Task 7.5 — Full-stack smoke test (manual)

**Description:** Run the full stack locally. Verify all three scenarios display correctly in the UI. No code changes permitted in this task.

**CC prompt:** *(none — human verification only)*

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Scenario A in UI | Agents animate running→success. Green auto_resolve banner. Steps shown. |
| TC-2 | Scenario B in UI | Red conflict event in timeline. Red escalated banner. |
| TC-3 | Updates SSE-driven | No polling artifacts — updates appear live. |

**Verification command:**
```bash
cd backend && uvicorn main:app --port 8000 --workers 1 &
cd frontend && npm run dev
# Open http://localhost:5173 and manually run all three scenarios
```

**Invariant flags:** INV-009 (parallelism visible in UI), INV-019 (all scenarios reach terminal state)

---

## Session 8 — GCP Deployment

**Goal:** Both services live on Cloud Run. Full demo verifiable on public URLs.

**Integration check:**
```bash
BACKEND=$(gcloud run services describe incident-war-room-backend --region=us-central1 --format='value(status.url)')
curl -sf $BACKEND/health | python3 -c "import sys,json; assert json.load(sys.stdin)['status']=='ok'" && \
curl -sf -X POST $BACKEND/demo/trigger/scenario_a | python3 -c "import sys,json; assert 'incident_id' in json.load(sys.stdin)" && \
echo "SESSION 8 INTEGRATION PASS"
```

---

### Task 8.1 — Dockerfiles and nginx config

**Description:** Implement `deploy/Dockerfile.backend`, `deploy/Dockerfile.frontend`, `deploy/nginx.conf`.

**CC prompt:**
```
Implement three files in deploy/. Do not create others.

Dockerfile.backend:
FROM python:3.11-slim. WORKDIR /app. COPY requirements.txt, pip install.
COPY backend/. RUN python tools/vectorstore.py --seed.
EXPOSE 8000. CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8000","--workers","1"]

Dockerfile.frontend:
Stage 1 node:20-alpine: npm ci, ARG VITE_API_URL, ENV VITE_API_URL=$VITE_API_URL, npm run build.
Stage 2 nginx:alpine: copy dist, copy nginx.conf as template.
CMD: envsubst '$BACKEND_URL' < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'

nginx.conf (as template file — uses $BACKEND_URL):
listen 80. location /api/ { proxy_pass $BACKEND_URL/; proxy_buffering off; proxy_cache off; proxy_read_timeout 120s; }
location / { try_files $uri $uri/ /index.html; }
```

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `docker build -f deploy/Dockerfile.backend .` | Builds, seed output visible in logs |
| TC-2 | `docker build -f deploy/Dockerfile.frontend --build-arg VITE_API_URL=http://test .` | Builds successfully |

**Verification command:**
```bash
docker build -f deploy/Dockerfile.backend -t war-room-backend-test . && \
docker build -f deploy/Dockerfile.frontend --build-arg VITE_API_URL=http://localhost:8000 -t war-room-frontend-test . && \
echo "TASK 8.1 PASS"
```

**Invariant flags:** INV-011 (no credentials in Dockerfiles)

---

### Task 8.2 — Service account and Cloud Run deployment

**Description:** Create service account, assign IAM roles, deploy backend then frontend. Follow ARCHITECTURE.md §14.5 and §14.6 exactly.

**CC prompt:** *(none — manual gcloud commands from ARCHITECTURE.md §14.5 and §14.6)*

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | `GET https://[backend-url]/health` | HTTP 200, `{"status":"ok"}` |
| TC-2 | `POST https://[backend-url]/demo/trigger/scenario_a` | Returns `incident_id` |
| TC-3 | Frontend URL in browser | React app renders, three demo buttons visible |

**Verification command:**
```bash
BACKEND=$(gcloud run services describe incident-war-room-backend --region=us-central1 --format='value(status.url)')
curl -sf $BACKEND/health && curl -sf -X POST $BACKEND/demo/trigger/scenario_a | python3 -c "import sys,json; assert 'incident_id' in json.load(sys.stdin)" && echo "TASK 8.2 PASS"
```

**Invariant flags:** INV-011 (service account ADC), INV-031 (60s SLA — verify on Cloud Run)

---

### Task 8.3 — Demo rehearsal on Cloud Run (manual)

**Description:** Run all three scenarios on the live Cloud Run deployment. Record timing. No code changes.

**CC prompt:** *(none — human verification only)*

**Test cases:**

| Case | Scenario | Expected |
|------|----------|----------|
| TC-1 | Scenario A on Cloud Run | < 60s, `auto_resolve` |
| TC-2 | Scenario B on Cloud Run | < 90s, `escalate`, conflict visible in UI |
| TC-3 | Scenario C on Cloud Run | `loop_count==1`, `auto_resolve` |
| TC-4 | No credentials visible | No API keys in any request/response |

**Verification command:**
```bash
echo "Manual rehearsal required on Cloud Run frontend URL. Record timings in SESSION_LOG.md."
```

**Invariant flags:** INV-011, INV-031, INV-043, INV-044

---

## Dependency Map

```
S1 (Scaffold)
  └── S2 (Graph skeleton)
        └── S3 (Agent nodes)
              ├── S4 (Coordinator) ──── S5 (API)
              │                             └── S7 (Frontend)
              │                                       └── S8 (Deploy)
              └── S6 (Vector store + fixtures)
                        └── S8 (Deploy)
```

S6 can be worked in parallel with S4/S5 by a second team member.  
S7 stub UI can begin after S2 — mock SSE events locally while agents are being built.

---

*EXECUTION_PLAN.md — Incident War Room · PBVI Phase 3 · March 2026*
