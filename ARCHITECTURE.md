# Meta Agent CX — Architecture

## High-Level System Flow

```
┌─────────────────────────────────────────────────────────────┐
│                     USER INTERFACE                           │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Natural Language Input                                │  │
│  │  "Create a support bot for appointment booking..."     │  │
│  └──────────────────────┬─────────────────────────────────┘  │
│                         │ POST /api/create-agent             │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    FASTAPI SERVER                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  main.py                                               │  │
│  │  • Receives AgentCreateRequest                         │  │
│  │  • Validates input                                     │  │
│  │  • Delegates to MetaOrchestrator                       │  │
│  │  • Returns AgentCreateResponse                         │  │
│  └──────────────────────┬─────────────────────────────────┘  │
└─────────────────────────┼───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 META ORCHESTRATOR                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  orchestrator.py — Step 1: ANALYZE                     │  │
│  │                                                        │  │
│  │  Input:  "Create a support bot for appointment..."     │  │
│  │                                                        │  │
│  │  Process:                                              │  │
│  │  ┌──────────────────────────────────────────────────┐  │  │
│  │  │  LLM Mode: GPT-4o + META_ORCHESTRATOR_PROMPT    │  │  │
│  │  │  OR                                              │  │  │
│  │  │  Rule Mode: Keyword detection + pattern matching │  │  │
│  │  └──────────────────────────────────────────────────┘  │  │
│  │                                                        │  │
│  │  Output: Analysis Brief (JSON)                         │  │
│  │  {                                                     │  │
│  │    "domain": "healthcare",                             │  │
│  │    "tasks": [...],                                     │  │
│  │    "functions_needed": [...],                           │  │
│  │    "flow_summary": [...]                               │  │
│  │  }                                                     │  │
│  └──────────────┬────────────────────┬────────────────────┘  │
│                 │                    │                        │
│          ┌──────┘                    └──────┐                 │
│          ▼                                 ▼                 │
│  ┌──────────────────┐         ┌──────────────────────┐       │
│  │  AGENT CREATOR   │         │  FUNCTION CREATOR    │       │
│  │  (Sub-Agent)     │         │  (Sub-Agent)         │       │
│  │                  │         │                      │       │
│  │  Generates:      │         │  Generates:          │       │
│  │  • Persona       │         │  • Function defs     │       │
│  │  • System prompt │         │  • API endpoints     │       │
│  │  • Voice config  │         │  • Parameters        │       │
│  │  • Intents       │         │  • Mock responses    │       │
│  │  • Flow graph    │         │  • OpenAI schemas    │       │
│  └────────┬─────────┘         └──────────┬───────────┘       │
│           │                              │                   │
│           └──────────┬───────────────────┘                   │
│                      ▼                                       │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Step 4: MERGE & VALIDATE                              │  │
│  │                                                        │  │
│  │  • Combine sub-agent outputs                           │  │
│  │  • Build Pydantic CXAgentConfig                        │  │
│  │  • Validate references (fn calls ↔ definitions)        │  │
│  │  • Generate OpenAI tool schemas                        │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  CXAgentConfig (OUTPUT)                       │
│                                                              │
│  {                                                           │
│    "agent_id": "agent_abc123",                               │
│    "persona": { name, role, system_prompt, ... },            │
│    "voice": { provider, voice_id, gender, ... },             │
│    "intents": [ { name, training_phrases, ... } ],           │
│    "functions": [ { name, parameters, api_endpoint, ... } ], │
│    "conversation_flow": { nodes, transitions, ... },         │
│    "deployment": { platform, phone_number, ... }             │
│  }                                                           │
│                                                              │
│  Ready for: VoiceOwl │ Twilio │ Vonage                       │
└─────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Meta Orchestrator (`orchestrator.py`)

**Responsibility:** Central coordinator — the "brain" of the system.

**Prompt:** `META_ORCHESTRATOR_PROMPT` — A detailed system prompt that instructs GPT-4o
to analyze user requests and produce structured analysis briefs.

**Dual Mode:**
- **LLM Mode:** Sends the user request + system prompt to GPT-4o with JSON response format
- **Rule Mode:** Uses keyword detection, regex patterns, and lookup tables (zero external calls)

**Key Methods:**
| Method | Description |
|--------|-------------|
| `process_request()` | End-to-end pipeline entry point |
| `_analyze_request()` | NLP analysis (LLM or rule-based) |
| `_detect_domain()` | Classifies business domain from keywords |
| `_detect_tasks()` | Extracts tasks + data slots from the request |
| `_detect_functions()` | Determines which API functions are needed |
| `_merge_config()` | Combines sub-agent outputs into CXAgentConfig |

---

### 2. Agent Creator (`agent_creator.py`)

**Responsibility:** Generates everything about the agent's identity and behavior.

**Prompt:** `AGENT_CREATOR_PROMPT` — Instructs GPT-4o to produce persona, voice, intents,
and conversation flow from the analysis brief.

**Outputs:**
- **PersonaConfig:** Name, role, system prompt (200+ words), personality traits
- **VoiceConfig:** TTS provider, voice ID, gender, language, speed
- **IntentDefinitions:** Named intents with 3-5 training phrases each
- **ConversationFlow:** Node-based state machine with transitions

**Flow Graph Design:**
```
greeting → collect_info → collect_info → api_call → decision
                                                      ├── success → confirm → end
                                                      └── failure → transfer → end
```

---

### 3. Function Creator (`function_creator.py`)

**Responsibility:** Generates callable function definitions for API integration.

**Prompt:** `FUNCTION_CREATOR_PROMPT` — Instructs GPT-4o to produce complete function
definitions with parameter schemas, API endpoint mappings, and mock responses.

**Outputs per Function:**
| Field | Description |
|-------|-------------|
| `name` | Snake_case function name (e.g., `get_appointment_slots`) |
| `description` | Detailed description for LLM context |
| `parameters` | Typed parameter list with descriptions |
| `api_endpoint` | REST endpoint config (URL, method, headers, auth) |
| `mock_response` | Realistic test data |

**OpenAI Tool Schema:**
Each function is also converted to the OpenAI function-calling format:
```json
{
  "type": "function",
  "function": {
    "name": "get_appointment_slots",
    "description": "...",
    "parameters": {
      "type": "object",
      "properties": { ... },
      "required": [ ... ]
    }
  }
}
```

---

### 4. Prompt Chain

```
┌─────────────────────────────────────┐
│  Prompt 1: META_ORCHESTRATOR_PROMPT │  → Analysis Brief
└─────────────────┬───────────────────┘
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
┌───────────────┐  ┌────────────────────┐
│  Prompt 2:    │  │  Prompt 3:         │
│  AGENT_CREATOR│  │  FUNCTION_CREATOR  │  → Agent Config + Functions
│  _PROMPT      │  │  _PROMPT           │
└───────────────┘  └────────────────────┘
```

Each prompt enforces:
- **Strict JSON output** (no markdown, no commentary)
- **Complete schemas** (all required fields specified)
- **Domain awareness** (healthcare, e-commerce, finance, etc.)
- **Error handling** (fallback messages, escalation paths)

---

### 5. Data Models (`models.py`)

```
CXAgentConfig
├── PersonaConfig         — Name, role, system prompt, fallback/escalation
├── VoiceConfig           — TTS provider, voice ID, gender, speed, pitch
├── IntentDefinition[]    — Intent names, training phrases, priorities
│   └── TrainingPhrase[]
├── FunctionDefinition[]  — Callable functions with API mappings
│   ├── FunctionParameter[]
│   └── APIEndpoint
├── ConversationFlow      — State machine graph
│   └── FlowNode[]
│       └── FlowTransition[]
└── DeploymentConfig      — Platform, phone number, webhook URL
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, Pydantic v2 |
| AI/LLM | OpenAI GPT-4o (optional, rule-based fallback) |
| Frontend | Vanilla HTML/CSS/JS, glassmorphism design |
| Fonts | Inter, JetBrains Mono (Google Fonts) |
| Deployment | Uvicorn ASGI server |

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serve web UI |
| `GET` | `/api/health` | Health check |
| `POST` | `/api/create-agent` | Create CX agent from natural language |
| `GET` | `/api/example` | Pre-built example input→output |
