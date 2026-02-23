"""
Agent Creator Sub-Agent

Responsible for generating the complete agent configuration including:
  - Persona (system prompt, greeting, fallback messages)
  - Voice settings (TTS provider, voice ID, speech rate)
  - Intent definitions with training phrases
  - Conversation flow graph (nodes + transitions)

This sub-agent receives the analysis brief from the Orchestrator and
produces the agent-side configuration. It works alongside the
Function Creator which handles function definitions separately.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .models import (
    ConversationFlow,
    CXAgentConfig,
    DeploymentConfig,
    FlowNode,
    FlowTransition,
    IntentDefinition,
    LanguageCode,
    NodeType,
    PersonaConfig,
    TrainingPhrase,
    VoiceConfig,
    VoiceGender,
    VoiceProvider,
)
from .prompts import AGENT_CREATOR_PROMPT

logger = logging.getLogger(__name__)


class AgentCreator:
    """
    Sub-agent that transforms an analysis brief into a structured
    CX agent configuration (persona, voice, intents, conversation flow).
    """

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: Optional OpenAI client. If None, uses built-in
                        rule-based generation (no external API needed).
        """
        self.llm_client = llm_client
        self.system_prompt = AGENT_CREATOR_PROMPT

    async def create_agent_config(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """
        Generate a full agent configuration from the orchestrator's analysis.

        If an LLM client is available, uses GPT to generate the config.
        Otherwise, falls back to deterministic rule-based generation.
        """
        if self.llm_client:
            return await self._create_with_llm(analysis)
        return self._create_with_rules(analysis)

    async def _create_with_llm(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Use OpenAI API to generate agent configuration."""
        try:
            response = await self.llm_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps(analysis, indent=2)},
                ],
                temperature=0.4,
                max_tokens=4000,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            return json.loads(raw)
        except Exception as e:
            logger.warning("LLM call failed (%s), falling back to rules", e)
            return self._create_with_rules(analysis)

    # ────────────────── Rule-Based Fallback ──────────────────

    def _create_with_rules(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Deterministic rule-based agent configuration generation."""
        persona = self._build_persona(analysis)
        voice = self._build_voice(analysis)
        intents = self._build_intents(analysis)
        flow = self._build_flow(analysis)

        return {
            "persona": persona,
            "voice": voice,
            "intents": intents,
            "conversation_flow": flow,
        }

    def _build_persona(self, analysis: dict[str, Any]) -> dict[str, Any]:
        name = analysis.get("agent_name_suggestion", "Ava")
        role = analysis.get("agent_role", "Customer Support Assistant")
        traits = analysis.get("personality_traits", ["friendly", "professional", "helpful"])
        domain = analysis.get("domain", "general")
        greeting_style = analysis.get("greeting_style", "warm")

        # Build the tasks section of the system prompt
        tasks = analysis.get("tasks", [])
        task_instructions = ""
        for i, task in enumerate(tasks, 1):
            task_instructions += f"\n{i}. **{task.get('task_name', 'Task')}**: {task.get('description', '')}"
            slots = task.get("data_to_collect", [])
            if slots:
                task_instructions += f"\n   - Collect: {', '.join(slots)}"
            if task.get("requires_api"):
                task_instructions += f"\n   - API Integration: {task.get('api_description', 'External API call')}"

        system_prompt = (
            f"You are {name}, a {', '.join(traits)} {role} specializing in {domain}. "
            f"You handle phone conversations with customers and your primary tasks are:\n"
            f"{task_instructions}\n\n"
            f"## Conversation Guidelines\n"
            f"- Always greet the caller warmly and introduce yourself by name.\n"
            f"- Speak clearly and at a moderate pace.\n"
            f"- Confirm information back to the caller before proceeding.\n"
            f"- If you don't understand something, politely ask for clarification.\n"
            f"- If you cannot help with a request, offer to transfer to a human agent.\n"
            f"- Keep responses concise — callers prefer short, clear answers.\n"
            f"- End every call by asking if there's anything else you can help with.\n\n"
            f"## Error Handling\n"
            f"- If an API call fails, apologize and offer to try again or escalate.\n"
            f"- After {3} failed attempts to understand, escalate to a human.\n"
            f"- Never make up information — only state what you know or can look up.\n\n"
            f"## Tone\n"
            f"- You are {', '.join(traits)}.\n"
            f"- Match the caller's energy level while maintaining professionalism.\n"
            f"- Use the caller's name once you have it to personalize the experience."
        )

        greeting_map = {
            "warm": (
                f"Hello! Thank you for calling. My name is {name}, and I'm here to help you today. "
                f"How can I assist you?"
            ),
            "formal": (
                f"Good day. This is {name}, your {role}. How may I assist you today?"
            ),
            "casual": (
                f"Hey there! I'm {name}. What can I help you with today?"
            ),
        }

        return {
            "name": name,
            "role": role,
            "personality_traits": traits,
            "greeting_style": greeting_style,
            "system_prompt": system_prompt,
            "fallback_message": (
                "I'm sorry, I didn't quite catch that. Could you please repeat "
                "what you said?"
            ),
            "escalation_message": (
                "I appreciate your patience. Let me connect you with a team member "
                "who can help you further. Please hold for just a moment."
            ),
            "max_retries": 3,
            "_greeting_text": greeting_map.get(greeting_style, greeting_map["warm"]),
        }

    def _build_voice(self, analysis: dict[str, Any]) -> dict[str, Any]:
        gender = analysis.get("voice_gender", "female")
        lang = analysis.get("language", "en-US")

        voice_map = {
            ("female", "en-US"): "en-US-Neural2-F",
            ("male", "en-US"): "en-US-Neural2-D",
            ("neutral", "en-US"): "en-US-Neural2-C",
            ("female", "en-GB"): "en-GB-Neural2-A",
            ("male", "en-GB"): "en-GB-Neural2-B",
            ("female", "hi-IN"): "hi-IN-Neural2-A",
            ("male", "hi-IN"): "hi-IN-Neural2-B",
            ("female", "es-ES"): "es-ES-Neural2-A",
        }

        voice_id = voice_map.get((gender, lang), "en-US-Neural2-F")

        return {
            "provider": "google",
            "voice_id": voice_id,
            "gender": gender,
            "language": lang,
            "speaking_rate": 1.0,
            "pitch": 0.0,
        }

    def _build_intents(self, analysis: dict[str, Any]) -> list[dict]:
        intents = []
        tasks = analysis.get("tasks", [])

        # Always include a greeting intent
        intents.append({
            "name": "greeting",
            "description": "Caller greets the agent or starts the conversation",
            "training_phrases": [
                {"text": "Hello", "language": analysis.get("language", "en-US")},
                {"text": "Hi there", "language": analysis.get("language", "en-US")},
                {"text": "Good morning", "language": analysis.get("language", "en-US")},
                {"text": "Hey", "language": analysis.get("language", "en-US")},
                {"text": "I need help", "language": analysis.get("language", "en-US")},
            ],
            "priority": 5,
        })

        for task in tasks:
            task_name = task.get("task_name", "unknown").lower().replace(" ", "_")
            intent_name = f"request_{task_name}"
            desc = task.get("description", "")
            intents.append({
                "name": intent_name,
                "description": f"Caller wants to: {desc}",
                "training_phrases": [
                    {"text": f"I want to {desc.lower()}", "language": analysis.get("language", "en-US")},
                    {"text": f"Can you help me {desc.lower()}", "language": analysis.get("language", "en-US")},
                    {"text": f"I need to {task_name.replace('_', ' ')}", "language": analysis.get("language", "en-US")},
                    {"text": f"Please {desc.lower()}", "language": analysis.get("language", "en-US")},
                ],
                "priority": 3,
            })

        # Fallback intent
        intents.append({
            "name": "fallback",
            "description": "Caller's request is not understood",
            "training_phrases": [],
            "priority": 0,
        })

        # Transfer / escalation intent
        intents.append({
            "name": "request_human_agent",
            "description": "Caller wants to speak with a human",
            "training_phrases": [
                {"text": "I want to talk to a person", "language": analysis.get("language", "en-US")},
                {"text": "Transfer me to a human", "language": analysis.get("language", "en-US")},
                {"text": "Can I speak with someone", "language": analysis.get("language", "en-US")},
                {"text": "Let me talk to a real person", "language": analysis.get("language", "en-US")},
            ],
            "priority": 8,
        })

        return intents

    def _build_flow(self, analysis: dict[str, Any]) -> dict[str, Any]:
        """Build a conversation flow graph from the analysis."""
        nodes: list[dict] = []
        tasks = analysis.get("tasks", [])
        functions_needed = analysis.get("functions_needed", [])
        func_names = {f["name"] for f in functions_needed}

        # 1. Greeting node
        persona_greeting = (
            f"Hello! Thank you for calling. My name is "
            f"{analysis.get('agent_name_suggestion', 'Ava')}, and I'm here to help you today. "
            f"How can I assist you?"
        )
        nodes.append({
            "node_id": "node_greet",
            "type": "greeting",
            "label": "Welcome Greeting",
            "prompt_text": persona_greeting,
            "collect_slot": None,
            "function_call": None,
            "transitions": [],
        })

        prev_node_id = "node_greet"

        # 2. For each task, create collect nodes + API call + response
        for task in tasks:
            task_name = task.get("task_name", "task").lower().replace(" ", "_")
            slots = task.get("data_to_collect", [])

            # Link previous node to first collect node or API node
            first_task_node_id = None

            # Collect slots
            for slot in slots:
                slot_id = slot.lower().replace(" ", "_")
                node_id = f"node_collect_{slot_id}"
                if first_task_node_id is None:
                    first_task_node_id = node_id

                prompt = self._slot_prompt(slot, analysis.get("agent_name_suggestion", "Ava"))
                nodes.append({
                    "node_id": node_id,
                    "type": "collect_info",
                    "label": f"Collect {slot.replace('_', ' ').title()}",
                    "prompt_text": prompt,
                    "collect_slot": slot_id,
                    "function_call": None,
                    "transitions": [],
                })

            # API call node (if task requires it)
            if task.get("requires_api"):
                matching_fn = None
                for fn in functions_needed:
                    if task_name in fn["name"] or fn["name"] in str(task.get("api_description", "")):
                        matching_fn = fn["name"]
                        break
                if matching_fn is None and functions_needed:
                    matching_fn = functions_needed[0]["name"]

                api_node_id = f"node_api_{task_name}"
                nodes.append({
                    "node_id": api_node_id,
                    "type": "api_call",
                    "label": f"Call API for {task_name.replace('_', ' ').title()}",
                    "prompt_text": "One moment while I look that up for you...",
                    "collect_slot": None,
                    "function_call": matching_fn,
                    "transitions": [],
                })

                # Decision node after API
                decision_node_id = f"node_decision_{task_name}"
                nodes.append({
                    "node_id": decision_node_id,
                    "type": "decision",
                    "label": f"Check {task_name.replace('_', ' ').title()} Result",
                    "prompt_text": None,
                    "collect_slot": None,
                    "function_call": None,
                    "transitions": [],
                })

                # Success response
                success_node_id = f"node_success_{task_name}"
                nodes.append({
                    "node_id": success_node_id,
                    "type": "response",
                    "label": f"{task_name.replace('_', ' ').title()} — Success",
                    "prompt_text": f"Great news! I've processed your {task_name.replace('_', ' ')} successfully.",
                    "collect_slot": None,
                    "function_call": None,
                    "transitions": [],
                })

                # Failure response
                failure_node_id = f"node_failure_{task_name}"
                nodes.append({
                    "node_id": failure_node_id,
                    "type": "response",
                    "label": f"{task_name.replace('_', ' ').title()} — Failure",
                    "prompt_text": (
                        f"I'm sorry, I wasn't able to complete your "
                        f"{task_name.replace('_', ' ')} at this time. "
                        f"Would you like me to transfer you to a team member?"
                    ),
                    "collect_slot": None,
                    "function_call": None,
                    "transitions": [],
                })

        # Confirm node
        nodes.append({
            "node_id": "node_confirm",
            "type": "confirm",
            "label": "Confirm & Anything Else",
            "prompt_text": "Is there anything else I can help you with today?",
            "collect_slot": None,
            "function_call": None,
            "transitions": [],
        })

        # Fallback node
        nodes.append({
            "node_id": "node_fallback",
            "type": "fallback",
            "label": "Fallback / Didn't Understand",
            "prompt_text": "I'm sorry, I didn't quite catch that. Could you please repeat what you said?",
            "collect_slot": None,
            "function_call": None,
            "transitions": [],
        })

        # Transfer node
        nodes.append({
            "node_id": "node_transfer",
            "type": "transfer",
            "label": "Transfer to Human Agent",
            "prompt_text": (
                "I appreciate your patience. Let me connect you with a team member "
                "who can help you further. Please hold for just a moment."
            ),
            "collect_slot": None,
            "function_call": None,
            "transitions": [],
        })

        # End node
        nodes.append({
            "node_id": "node_end",
            "type": "end",
            "label": "End Call",
            "prompt_text": "Thank you for calling! Have a wonderful day. Goodbye!",
            "collect_slot": None,
            "function_call": None,
            "transitions": [],
        })

        # ── Wire transitions ──
        self._wire_transitions(nodes, tasks, functions_needed)

        return {
            "name": f"{analysis.get('domain', 'general')}_flow",
            "description": (
                f"Conversation flow for {analysis.get('agent_name_suggestion', 'the agent')} "
                f"handling {', '.join(t.get('task_name', '') for t in tasks)}"
            ),
            "entry_node_id": "node_greet",
            "nodes": nodes,
        }

    def _wire_transitions(
        self,
        nodes: list[dict],
        tasks: list[dict],
        functions_needed: list[dict],
    ) -> None:
        """Wire up transitions between flow nodes."""
        node_map = {n["node_id"]: n for n in nodes}

        # Find ordered task-related node groups
        task_groups: list[list[str]] = []
        for task in tasks:
            task_name = task.get("task_name", "task").lower().replace(" ", "_")
            slots = task.get("data_to_collect", [])
            group_ids: list[str] = []

            for slot in slots:
                nid = f"node_collect_{slot.lower().replace(' ', '_')}"
                if nid in node_map:
                    group_ids.append(nid)

            if task.get("requires_api"):
                api_nid = f"node_api_{task_name}"
                if api_nid in node_map:
                    group_ids.append(api_nid)
                dec_nid = f"node_decision_{task_name}"
                if dec_nid in node_map:
                    group_ids.append(dec_nid)

            task_groups.append(group_ids)

        # Greeting → first task node
        if task_groups and task_groups[0]:
            node_map["node_greet"]["transitions"].append(
                {"condition": "user_responds", "target_node_id": task_groups[0][0]}
            )
        else:
            node_map["node_greet"]["transitions"].append(
                {"condition": "user_responds", "target_node_id": "node_confirm"}
            )

        # Chain nodes within each task group
        for group in task_groups:
            for i, nid in enumerate(group):
                next_nid = group[i + 1] if i + 1 < len(group) else None
                node = node_map[nid]

                if node["type"] == "collect_info":
                    if next_nid:
                        node["transitions"].append(
                            {"condition": "slot_filled", "target_node_id": next_nid}
                        )
                    else:
                        node["transitions"].append(
                            {"condition": "slot_filled", "target_node_id": "node_confirm"}
                        )
                elif node["type"] == "api_call":
                    if next_nid:
                        node["transitions"].append(
                            {"condition": "api_response_received", "target_node_id": next_nid}
                        )
                    else:
                        node["transitions"].append(
                            {"condition": "api_response_received", "target_node_id": "node_confirm"}
                        )
                elif node["type"] == "decision":
                    task_name = nid.replace("node_decision_", "")
                    success_nid = f"node_success_{task_name}"
                    failure_nid = f"node_failure_{task_name}"
                    if success_nid in node_map:
                        node["transitions"].append(
                            {"condition": "success", "target_node_id": success_nid}
                        )
                        node_map[success_nid]["transitions"].append(
                            {"condition": "continue", "target_node_id": "node_confirm"}
                        )
                    if failure_nid in node_map:
                        node["transitions"].append(
                            {"condition": "failure", "target_node_id": failure_nid}
                        )
                        node_map[failure_nid]["transitions"].append(
                            {"condition": "user_wants_transfer", "target_node_id": "node_transfer"}
                        )
                        node_map[failure_nid]["transitions"].append(
                            {"condition": "user_declines_transfer", "target_node_id": "node_confirm"}
                        )

        # Confirm → end or back to greeting
        if "node_confirm" in node_map:
            node_map["node_confirm"]["transitions"].extend([
                {"condition": "nothing_else", "target_node_id": "node_end"},
                {"condition": "has_more_questions", "target_node_id": "node_greet"},
            ])

        # Fallback → back to previous context (greet for simplicity)
        if "node_fallback" in node_map:
            node_map["node_fallback"]["transitions"].append(
                {"condition": "retry", "target_node_id": "node_greet"}
            )

        # Transfer → end
        if "node_transfer" in node_map:
            node_map["node_transfer"]["transitions"].append(
                {"condition": "transferred", "target_node_id": "node_end"}
            )

    def _slot_prompt(self, slot: str, agent_name: str) -> str:
        """Generate a natural prompt for collecting a slot value."""
        slot_prompts = {
            "name": "Could I please have your name?",
            "customer_name": "Could I please have your name?",
            "full_name": "May I have your full name, please?",
            "first_name": "What's your first name?",
            "date": "What date works best for you?",
            "appointment_date": "What date would you like to schedule your appointment?",
            "preferred_date": "When would you prefer to come in?",
            "time": "And what time would you prefer?",
            "appointment_time": "What time would you like your appointment?",
            "preferred_time": "What time works best for you?",
            "email": "Could you provide your email address?",
            "phone": "What's the best phone number to reach you at?",
            "phone_number": "What's the best phone number to reach you at?",
            "service": "What type of service are you looking for?",
            "service_type": "What type of service do you need?",
            "reason": "Could you tell me the reason for your visit?",
            "location": "Which location would you prefer?",
            "order_number": "Could you provide your order number?",
            "account_number": "What's your account number?",
            "issue": "Could you describe the issue you're experiencing?",
            "product": "Which product are you inquiring about?",
        }
        readable = slot.replace("_", " ")
        return slot_prompts.get(
            slot.lower(),
            f"Could you please provide your {readable}?"
        )
