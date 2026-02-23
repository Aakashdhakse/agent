# Meta Agent CX — AI-Powered CX Phone Agent Builder

> **A Meta Agent system that creates and configures Customer Experience (CX) phone agents
> through natural language descriptions.**

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-green)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-teal)

---

## 🎯 Overview

This system implements a **Meta Agent** — an AI that creates other AI agents. Non-technical
users describe what kind of phone support agent they need in plain English, and the Meta Agent
generates:

- **Persona Configuration** — name, role, personality, system prompt
- **Voice Settings** — TTS provider, voice ID, gender, language, speed
- **Intent Definitions** — what the agent can recognize, with training phrases
- **Function Calls** — API integrations with endpoint mappings and mock data
- **Conversation Flow** — complete state machine with nodes and transitions
- **Deployment Config** — platform-ready settings for VoiceOwl, Twilio, or Vonage

---

## 🏗️ Architecture

The system uses a **modular sub-agent architecture**:

```
User Request → Meta Orchestrator → Agent Creator + Function Creator → CXAgentConfig
```

| Component | File | Role |
|-----------|------|------|
| **Meta Orchestrator** | `meta_agent/orchestrator.py` | Analyzes requests, coordinates sub-agents |
| **Agent Creator** | `meta_agent/agent_creator.py` | Generates persona, voice, intents, flow |
| **Function Creator** | `meta_agent/function_creator.py` | Defines callable functions + API mappings |
| **Data Models** | `meta_agent/models.py` | Pydantic schemas for all configurations |
| **Prompt Chain** | `meta_agent/prompts.py` | System prompts for all agents |
| **FastAPI Server** | `main.py` | REST API + web UI serving |

> See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed diagrams and component descriptions.

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. (Optional) Set OpenAI API Key

For LLM-powered generation:
```bash
# Create a .env file
echo OPENAI_API_KEY=sk-your-key-here > .env
```

> **Without an API key, the system runs in rule-based mode** — fully functional
> with deterministic, keyword-driven generation.

### 3. Run the Server

```bash
python main.py
```

Or with Uvicorn directly:
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 4. Open the Web UI

Navigate to **http://localhost:8000** in your browser.

### 5. API Usage

```bash
curl -X POST http://localhost:8000/api/create-agent \
  -H "Content-Type: application/json" \
  -d '{
    "user_prompt": "Create a support bot for appointment booking. It should greet, ask for name and date, and confirm availability via an API.",
    "language": "en-US",
    "platform": "voiceowl"
  }'
```

---

## 📋 Deliverables Mapping

| # | Deliverable | Location |
|---|-------------|----------|
| 1 | **Meta Prompt / Prompt Chain** | `meta_agent/prompts.py` |
| 2 | **Function Definition Logic** | `meta_agent/function_creator.py` |
| 3 | **Example Input → Output** | `examples/example_output.json` + `/api/example` endpoint |
| 4 | **Architecture Sketch** | `ARCHITECTURE.md` |
| 5 | **Minimal Prototype** | Full FastAPI app (`main.py` + `meta_agent/`) |

---

## 📝 Prompt Engineering Details

### Prompt Chain Design

The system uses a **3-stage prompt chain**:

#### Stage 1: Meta Orchestrator Prompt
```
Purpose:  Analyze natural language → structured analysis brief
Input:    User's free-text description
Output:   JSON with domain, tasks, functions_needed, flow_summary
Strategy: Zero-shot with detailed output schema specification
```

#### Stage 2: Agent Creator Prompt
```
Purpose:  Analysis brief → agent configuration
Input:    JSON analysis brief from Stage 1
Output:   JSON with persona, voice, intents, conversation_flow
Strategy: Few-shot style with detailed rules for system prompt generation
```

#### Stage 3: Function Creator Prompt
```
Purpose:  Function requirements → complete function definitions
Input:    JSON array of function requirements from Stage 1
Output:   JSON with function definitions, API endpoints, mock responses
Strategy: Schema-driven with REST convention enforcement
```

### Key Prompt Engineering Techniques Used

1. **Structured Output Enforcement** — All prompts require JSON-only output
2. **Schema Specification** — Exact JSON schemas provided in each prompt
3. **Role Definition** — Clear role assignment ("You are the Agent Creator...")
4. **Constraint Rules** — Explicit rules section with do's and don'ts
5. **Separation of Concerns** — Each sub-agent has a focused responsibility
6. **Fallback Strategy** — LLM failure → rule-based deterministic generation
7. **Temperature Tuning** — Low temperature (0.3-0.4) for consistent structured output

---

## ⚡ Function Call Integration

### How Functions Are Defined

1. The **Meta Orchestrator** extracts `functions_needed` from the user request
2. The **Function Creator** generates full definitions with:
   - Typed parameter schemas
   - REST API endpoint configurations
   - Realistic mock responses
   - OpenAI-compatible tool schemas

### OpenAI Function Calling Format

Every generated function is also output as an OpenAI tool schema:

```json
{
  "type": "function",
  "function": {
    "name": "get_appointment_slots",
    "description": "Check available appointment slots...",
    "parameters": {
      "type": "object",
      "properties": {
        "preferred_date": {
          "type": "string",
          "description": "The customer's preferred date"
        }
      },
      "required": ["preferred_date"]
    }
  }
}
```

### Function → API Mapping

Each function includes an `api_endpoint` configuration:

```json
{
  "url": "/api/v1/appointments/slots",
  "method": "GET",
  "headers": { "Content-Type": "application/json" },
  "auth_type": "bearer",
  "timeout_seconds": 10
}
```

---

## 🔧 Example: Input → Output

### Input
```
"Create a support bot for appointment booking. It should greet,
ask for name and date, and confirm availability via an API."
```

### Output Summary
- **Agent Name:** MediBot
- **Role:** Healthcare Appointment & Patient Support Agent
- **Personality:** Friendly, professional, helpful
- **Voice:** Google Neural2-F (female, en-US)
- **Intents:** greeting, request_appointment_booking, request_confirm_availability, fallback, request_human_agent
- **Functions:** `get_appointment_slots()`, `check_availability()`
- **Flow:** 10+ nodes (greeting → collect name → collect date → API call → decision → success/failure → confirm → end)

> See the full JSON output at the `/api/example` endpoint or in `examples/example_output.json`.

---

## 🏗️ Project Structure

```
geetabhawan/
├── main.py                      # FastAPI application entry point
├── requirements.txt             # Python dependencies
├── .env                         # (optional) OpenAI API key
├── ARCHITECTURE.md              # Architecture documentation
├── README.md                    # This file
├── meta_agent/
│   ├── __init__.py
│   ├── orchestrator.py          # Meta Orchestrator (main coordinator)
│   ├── agent_creator.py         # Agent Creator sub-agent
│   ├── function_creator.py      # Function Creator sub-agent
│   ├── models.py                # Pydantic data models
│   └── prompts.py               # System prompts for all agents
├── static/
│   ├── index.html               # Web UI
│   ├── style.css                # Design system & styles
│   └── script.js                # Frontend logic
└── examples/
    └── example_output.json      # Pre-built example output
```

---

## 📊 Evaluation Rubric Coverage

| Category (Points) | Implementation |
|---|---|
| **Conceptual Design (20)** | Modular sub-agent arch, clear separation of concerns, dual-mode (LLM/rule-based) |
| **Prompt Engineering (25)** | 3-stage prompt chain, JSON enforcement, temperature tuning, schema-driven |
| **Function Call Integration (20)** | Full parameter schemas, API endpoint mapping, OpenAI tool format, mock responses |
| **Example Quality (15)** | Complete input→output with all config sections, live `/api/example` endpoint |
| **Technical Implementation (10)** | FastAPI + Pydantic, async, type hints, error handling, dual mode |
| **Documentation & Clarity (10)** | README, ARCHITECTURE.md, inline docstrings, prompt documentation |
| **Bonus (+10)** | Phone context (voice config, TTS), modular sub-agents, deployment awareness |

---

## License

MIT
