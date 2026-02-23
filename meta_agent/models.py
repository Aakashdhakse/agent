"""
Pydantic models for the Meta Agent CX system.
Defines structured schemas for agent configurations, function calls,
intents, conversation flows, and deployment settings.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ──────────────────────────── Enums ────────────────────────────

class VoiceGender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    NEUTRAL = "neutral"


class VoiceProvider(str, Enum):
    GOOGLE = "google"
    AZURE = "azure"
    ELEVENLABS = "elevenlabs"
    AWS_POLLY = "aws_polly"


class LanguageCode(str, Enum):
    EN_US = "en-US"
    EN_GB = "en-GB"
    ES_ES = "es-ES"
    FR_FR = "fr-FR"
    DE_DE = "de-DE"
    HI_IN = "hi-IN"
    JA_JP = "ja-JP"


class ParamType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"


class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class NodeType(str, Enum):
    GREETING = "greeting"
    COLLECT_INFO = "collect_info"
    API_CALL = "api_call"
    DECISION = "decision"
    RESPONSE = "response"
    TRANSFER = "transfer"
    END = "end"
    CONFIRM = "confirm"
    FALLBACK = "fallback"


class AgentStatus(str, Enum):
    DRAFT = "draft"
    TESTING = "testing"
    DEPLOYED = "deployed"
    ARCHIVED = "archived"


# ──────────────────────────── Voice & Persona ────────────────────────────

class VoiceConfig(BaseModel):
    """TTS voice configuration for the phone agent."""
    provider: VoiceProvider = VoiceProvider.GOOGLE
    voice_id: str = Field(default="en-US-Neural2-F", description="Provider-specific voice identifier")
    gender: VoiceGender = VoiceGender.FEMALE
    language: LanguageCode = LanguageCode.EN_US
    speaking_rate: float = Field(default=1.0, ge=0.5, le=2.0, description="Speech speed multiplier")
    pitch: float = Field(default=0.0, ge=-10.0, le=10.0, description="Voice pitch adjustment")


class PersonaConfig(BaseModel):
    """Defines the agent's personality and behavior."""
    name: str = Field(..., description="Display name of the agent, e.g. 'Ava'")
    role: str = Field(..., description="Role description, e.g. 'Appointment Scheduling Assistant'")
    personality_traits: list[str] = Field(
        default_factory=lambda: ["friendly", "professional", "helpful"],
        description="Personality adjectives"
    )
    greeting_style: str = Field(
        default="warm",
        description="Greeting tone: warm, formal, casual"
    )
    system_prompt: str = Field(..., description="Full system prompt for the LLM powering this agent")
    fallback_message: str = Field(
        default="I'm sorry, I didn't quite catch that. Could you please repeat?",
        description="Default message when the agent can't understand"
    )
    escalation_message: str = Field(
        default="Let me transfer you to a human agent who can assist you further.",
        description="Message before transferring to a human"
    )
    max_retries: int = Field(default=3, ge=1, le=5, description="Max retry attempts per slot")


# ──────────────────────────── Intents ────────────────────────────

class TrainingPhrase(BaseModel):
    """Example utterance for intent recognition."""
    text: str
    language: LanguageCode = LanguageCode.EN_US


class IntentDefinition(BaseModel):
    """A single conversational intent the agent can recognize."""
    intent_id: str = Field(default_factory=lambda: f"intent_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Intent name, e.g. 'book_appointment'")
    description: str = Field(..., description="What this intent represents")
    training_phrases: list[TrainingPhrase] = Field(
        default_factory=list,
        description="Sample utterances to train the intent classifier"
    )
    priority: int = Field(default=0, ge=0, le=10)


# ──────────────────────────── Function Calls ────────────────────────────

class FunctionParameter(BaseModel):
    """A single parameter for a function call."""
    name: str
    type: ParamType = ParamType.STRING
    description: str
    required: bool = True
    default: Any | None = None
    enum: list[str] | None = None


class APIEndpoint(BaseModel):
    """Backend API endpoint that a function call maps to."""
    url: str = Field(..., description="Full URL or path template, e.g. /api/appointments/slots")
    method: HTTPMethod = HTTPMethod.POST
    headers: dict[str, str] = Field(default_factory=lambda: {"Content-Type": "application/json"})
    auth_type: str | None = Field(default=None, description="none | api_key | bearer | oauth2")
    timeout_seconds: int = Field(default=10, ge=1, le=60)


class FunctionDefinition(BaseModel):
    """
    A callable function that the CX agent can invoke during conversation.
    Maps to OpenAI-style function calling schema.
    """
    function_id: str = Field(default_factory=lambda: f"fn_{uuid.uuid4().hex[:8]}")
    name: str = Field(..., description="Function name, e.g. 'get_appointment_slots'")
    description: str = Field(..., description="What the function does, for LLM context")
    parameters: list[FunctionParameter] = Field(default_factory=list)
    returns_description: str = Field(default="", description="Description of the return value")
    api_endpoint: APIEndpoint | None = Field(
        default=None,
        description="Backend endpoint to call when this function is invoked"
    )
    mock_response: dict[str, Any] | None = Field(
        default=None,
        description="Mock response for testing purposes"
    )

    def to_openai_tool_schema(self) -> dict:
        """Convert to OpenAI function-calling tool format."""
        properties = {}
        required = []
        for p in self.parameters:
            prop: dict[str, Any] = {
                "type": p.type.value,
                "description": p.description,
            }
            if p.enum:
                prop["enum"] = p.enum
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# ──────────────────────────── Conversation Flow ────────────────────────────

class FlowTransition(BaseModel):
    """Edge in the conversation flow graph."""
    condition: str = Field(..., description="Condition label, e.g. 'user_provides_name' or 'api_success'")
    target_node_id: str = Field(..., description="ID of the next node")


class FlowNode(BaseModel):
    """A single node in the conversation flow graph."""
    node_id: str = Field(default_factory=lambda: f"node_{uuid.uuid4().hex[:8]}")
    type: NodeType
    label: str = Field(..., description="Human-readable label for this step")
    prompt_text: str | None = Field(default=None, description="What the agent says at this node")
    collect_slot: str | None = Field(
        default=None,
        description="Slot/variable to fill at this node, e.g. 'customer_name'"
    )
    function_call: str | None = Field(
        default=None,
        description="Function name to invoke at this node (must match a FunctionDefinition.name)"
    )
    transitions: list[FlowTransition] = Field(default_factory=list)


class ConversationFlow(BaseModel):
    """Complete conversation flow graph for the agent."""
    flow_id: str = Field(default_factory=lambda: f"flow_{uuid.uuid4().hex[:8]}")
    name: str
    description: str
    entry_node_id: str = Field(..., description="ID of the first node in the flow")
    nodes: list[FlowNode] = Field(default_factory=list)


# ──────────────────────────── Top-Level Agent Config ────────────────────────────

class DeploymentConfig(BaseModel):
    """Deployment settings for the agent."""
    platform: str = Field(default="voiceowl", description="Target platform: voiceowl, twilio, vonage")
    phone_number: str | None = None
    webhook_url: str | None = None
    environment: str = Field(default="staging", description="staging | production")
    max_concurrent_calls: int = Field(default=10, ge=1)
    recording_enabled: bool = True
    analytics_enabled: bool = True


class CXAgentConfig(BaseModel):
    """
    Complete configuration for a generated CX phone agent.
    This is the primary output of the Meta Agent.
    """
    agent_id: str = Field(default_factory=lambda: f"agent_{uuid.uuid4().hex[:12]}")
    version: str = "1.0.0"
    status: AgentStatus = AgentStatus.DRAFT
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    persona: PersonaConfig
    voice: VoiceConfig
    intents: list[IntentDefinition] = Field(default_factory=list)
    functions: list[FunctionDefinition] = Field(default_factory=list)
    conversation_flow: ConversationFlow | None = None
    deployment: DeploymentConfig = Field(default_factory=DeploymentConfig)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_openai_tools(self) -> list[dict]:
        """Return all functions as OpenAI-compatible tool definitions."""
        return [f.to_openai_tool_schema() for f in self.functions]


# ──────────────────────────── API Request / Response ────────────────────────────

class AgentCreateRequest(BaseModel):
    """Incoming request to create a new CX agent."""
    user_prompt: str = Field(
        ...,
        min_length=10,
        description="Natural language description of the desired agent"
    )
    language: LanguageCode = LanguageCode.EN_US
    platform: str = "voiceowl"


class AgentCreateResponse(BaseModel):
    """Response containing the generated CX agent configuration."""
    success: bool
    message: str
    agent_config: CXAgentConfig | None = None
    openai_tools_schema: list[dict] | None = None
    raw_analysis: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
