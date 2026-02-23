"""
Meta Agent Orchestrator

The central coordinator that:
  1. Receives natural language requests from users
  2. Analyzes the request using the Meta Orchestrator prompt
  3. Dispatches to Agent Creator and Function Creator sub-agents
  4. Merges outputs into a deployable CXAgentConfig
  5. Validates the final configuration

This module supports two modes:
  - LLM Mode:  Uses OpenAI API for intelligent analysis + generation
  - Rule Mode: Fully deterministic, no external API calls (for demos/testing)
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from .agent_creator import AgentCreator
from .function_creator import FunctionCreator
from .models import (
    AgentCreateRequest,
    AgentCreateResponse,
    AgentStatus,
    CXAgentConfig,
    ConversationFlow,
    DeploymentConfig,
    FlowNode,
    FlowTransition,
    FunctionDefinition,
    FunctionParameter,
    IntentDefinition,
    PersonaConfig,
    TrainingPhrase,
    VoiceConfig,
    APIEndpoint,
)
from .prompts import META_ORCHESTRATOR_PROMPT

logger = logging.getLogger(__name__)


class MetaOrchestrator:
    """
    Top-level Meta Agent that orchestrates CX agent creation.

    Architecture:
        User Request
            │
            ▼
        ┌──────────────────┐
        │  Meta Orchestrator│  ← Analyzes request, produces brief
        └────────┬─────────┘
                 │ analysis brief (JSON)
           ┌─────┴─────┐
           ▼           ▼
     ┌───────────┐ ┌────────────────┐
     │  Agent    │ │   Function     │
     │  Creator  │ │   Creator      │
     └─────┬─────┘ └──────┬─────────┘
           │              │
           ▼              ▼
        ┌──────────────────┐
        │   Merge & Validate│
        └──────────────────┘
                 │
                 ▼
          CXAgentConfig (JSON)
    """

    def __init__(self, openai_api_key: str | None = None):
        """
        Initialize the Meta Orchestrator.

        Args:
            openai_api_key: If provided, uses GPT for analysis and generation.
                            If None, uses deterministic rule-based logic.
        """
        self.llm_client = None
        if openai_api_key:
            try:
                from openai import AsyncOpenAI
                self.llm_client = AsyncOpenAI(api_key=openai_api_key)
                logger.info("Initialized with OpenAI LLM client")
            except ImportError:
                logger.warning("openai package not installed, using rule-based mode")
            except Exception as e:
                logger.warning("Failed to init OpenAI client: %s", e)

        self.agent_creator = AgentCreator(llm_client=self.llm_client)
        self.function_creator = FunctionCreator(llm_client=self.llm_client)
        self.system_prompt = META_ORCHESTRATOR_PROMPT

    async def process_request(self, request: AgentCreateRequest) -> AgentCreateResponse:
        """
        End-to-end processing: user request → CX agent configuration.

        Steps:
          1. Analyze the user's natural language request
          2. Generate agent config (persona, voice, intents, flow)
          3. Generate function definitions
          4. Merge everything into a CXAgentConfig
          5. Return structured response
        """
        try:
            # Step 1: Analyze the request
            logger.info("Step 1: Analyzing user request...")
            analysis = await self._analyze_request(request.user_prompt, request.language.value, request.platform)

            # Step 2: Create agent configuration
            logger.info("Step 2: Creating agent configuration...")
            agent_config_raw = await self.agent_creator.create_agent_config(analysis)

            # Step 3: Create function definitions
            logger.info("Step 3: Creating function definitions...")
            functions_needed = analysis.get("functions_needed", [])
            functions_raw = await self.function_creator.create_functions(functions_needed)

            # Step 4: Merge into CXAgentConfig
            logger.info("Step 4: Merging into final configuration...")
            agent_config = self._merge_config(
                analysis=analysis,
                agent_config=agent_config_raw,
                functions=functions_raw,
                platform=request.platform,
            )

            # Step 5: Generate OpenAI tool schemas
            openai_tools = self.function_creator.to_openai_tools(functions_raw)

            return AgentCreateResponse(
                success=True,
                message=f"Successfully created CX agent '{agent_config.persona.name}' "
                        f"with {len(agent_config.functions)} functions and "
                        f"{len(agent_config.intents)} intents.",
                agent_config=agent_config,
                openai_tools_schema=openai_tools,
                raw_analysis=analysis,
            )

        except Exception as e:
            logger.exception("Failed to process request")
            return AgentCreateResponse(
                success=False,
                message=f"Failed to create agent: {str(e)}",
                agent_config=None,
            )

    # ────────────────── Step 1: Analyze Request ──────────────────

    async def _analyze_request(self, user_prompt: str, language: str, platform: str) -> dict[str, Any]:
        """
        Parse the user's natural language into a structured analysis brief.
        """
        if self.llm_client:
            return await self._analyze_with_llm(user_prompt, language, platform)
        return self._analyze_with_rules(user_prompt, language, platform)

    async def _analyze_with_llm(self, user_prompt: str, language: str, platform: str) -> dict[str, Any]:
        """Use GPT to analyze the user request."""
        try:
            augmented_prompt = (
                f"User request: {user_prompt}\n\n"
                f"Preferred language: {language}\n"
                f"Target platform: {platform}"
            )
            response = await self.llm_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": augmented_prompt},
                ],
                temperature=0.3,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            return json.loads(raw)
        except Exception as e:
            logger.warning("LLM analysis failed (%s), falling back to rules", e)
            return self._analyze_with_rules(user_prompt, language, platform)

    def _analyze_with_rules(self, user_prompt: str, language: str, platform: str) -> dict[str, Any]:
        """
        Rule-based NLP analysis of the user request.
        Uses keyword matching and pattern extraction to build the analysis brief.
        """
        prompt_lower = user_prompt.lower()

        # Domain detection
        domain = self._detect_domain(prompt_lower)

        # Extract explicit data fields the user mentioned
        user_slots = self._extract_user_slots(prompt_lower)

        # Detect tasks
        tasks = self._detect_tasks(prompt_lower, domain)

        # Merge user-mentioned slots into tasks
        if user_slots:
            tasks = self._merge_user_slots_into_tasks(tasks, user_slots)

        # Detect functions needed
        functions_needed = self._detect_functions(tasks, prompt_lower)

        # Detect persona preferences
        name, traits, style = self._detect_persona(prompt_lower, domain)

        # Build flow summary
        flow_summary = self._build_flow_summary(tasks)

        # Detect voice preferences
        gender = self._detect_voice_gender(prompt_lower)

        return {
            "domain": domain,
            "agent_name_suggestion": name,
            "agent_role": f"{domain.title()} {self._role_for_domain(domain)}",
            "personality_traits": traits,
            "greeting_style": style,
            "language": language,
            "voice_gender": gender,
            "tasks": tasks,
            "functions_needed": functions_needed,
            "flow_summary": flow_summary,
            "ambiguities": [],
            "platform": platform,
            "user_requested_slots": user_slots,
        }

    def _detect_domain(self, text: str) -> str:
        domain_keywords = {
            "healthcare": ["appointment", "doctor", "clinic", "hospital", "patient", "medical", "health", "therapy"],
            "e-commerce": ["order", "product", "shipping", "cart", "purchase", "delivery", "shop", "store", "buy"],
            "finance": ["account", "balance", "transaction", "payment", "loan", "bank", "card", "credit"],
            "travel": ["flight", "hotel", "booking", "reservation", "travel", "trip", "airline"],
            "telecommunications": ["plan", "data", "mobile", "phone bill", "sim", "network", "roaming"],
            "food_delivery": ["food", "restaurant", "delivery", "menu", "order food", "meal"],
            "insurance": ["claim", "policy", "insurance", "coverage", "premium"],
            "education": ["course", "class", "enrollment", "student", "tutor", "training"],
            "real_estate": ["property", "rent", "lease", "apartment", "house", "real estate"],
            "automotive": ["car", "vehicle", "service", "repair", "maintenance", "dealership"],
        }
        for domain, keywords in domain_keywords.items():
            if any(kw in text for kw in keywords):
                return domain
        return "general_support"

    def _extract_user_slots(self, text: str) -> list[str]:
        """
        Scan the user's prompt for explicitly mentioned data fields.
        Returns a list of slot names the user wants to collect.
        """
        slot_keywords = {
            "customer_name": ["name", "first name", "last name", "full name", "caller name", "user name"],
            "email": ["email", "e-mail", "email address", "mail"],
            "phone_number": ["phone", "phone number", "mobile", "contact number", "cell"],
            "preferred_date": ["date", "day", "when", "preferred date", "appointment date"],
            "preferred_time": ["time", "preferred time", "appointment time", "what time"],
            "address": ["address", "location", "where"],
            "service_type": ["service", "service type", "type of service"],
            "reason": ["reason", "purpose", "why"],
            "order_number": ["order number", "order id", "order #"],
            "account_number": ["account number", "account id", "account #"],
            "issue_description": ["issue", "problem", "complaint", "describe"],
            "age": ["age", "how old"],
            "dob": ["date of birth", "dob", "birthday"],
            "insurance_id": ["insurance", "insurance id", "policy number"],
            "company_name": ["company", "organization", "business name"],
        }

        found_slots = []
        for slot_name, keywords in slot_keywords.items():
            for kw in keywords:
                if kw in text:
                    if slot_name not in found_slots:
                        found_slots.append(slot_name)
                    break
        return found_slots

    def _merge_user_slots_into_tasks(
        self, tasks: list[dict], user_slots: list[str]
    ) -> list[dict]:
        """
        Merge user-specified data slots into the most relevant task.
        If a user says 'take name and email', those slots get added to
        the primary task (e.g. Appointment Booking) instead of being ignored.
        """
        # Find the primary task (first API-requiring task, or first non-greeting)
        primary_task = None
        for task in tasks:
            if task.get("requires_api"):
                primary_task = task
                break
        if primary_task is None:
            for task in tasks:
                if task["task_name"] != "Greeting":
                    primary_task = task
                    break

        if primary_task is None:
            # All we have is greeting, create a data collection task
            tasks.append({
                "task_name": "Collect Customer Information",
                "description": "Collect customer details for the interaction",
                "data_to_collect": user_slots,
                "requires_api": True,
                "api_description": "Store or process collected customer information",
            })
            return tasks

        # Merge user slots into primary task's data_to_collect
        existing_slots = set(primary_task.get("data_to_collect", []))
        for slot in user_slots:
            if slot not in existing_slots:
                primary_task.setdefault("data_to_collect", []).append(slot)
                existing_slots.add(slot)

        return tasks

    def _detect_tasks(self, text: str, domain: str) -> list[dict]:
        tasks = []
        task_patterns = {
            "greet": {
                "keywords": ["greet", "welcome", "hello", "introduce"],
                "task_name": "Greeting",
                "description": "Greet the caller and introduce the service",
                "data_to_collect": [],
                "requires_api": False,
                "api_description": "",
            },
            "collect_name": {
                "keywords": ["take name", "ask name", "collect name", "get name", "ask for name"],
                "task_name": "Collect Customer Name",
                "description": "Collect the caller's name for personalization",
                "data_to_collect": ["customer_name"],
                "requires_api": False,
                "api_description": "",
            },
            "collect_email": {
                "keywords": ["email", "e-mail", "mail address"],
                "task_name": "Collect Email",
                "description": "Collect the caller's email address",
                "data_to_collect": ["email"],
                "requires_api": False,
                "api_description": "",
            },
            "collect_phone": {
                "keywords": ["phone number", "mobile number", "contact number"],
                "task_name": "Collect Phone Number",
                "description": "Collect the caller's phone number",
                "data_to_collect": ["phone_number"],
                "requires_api": False,
                "api_description": "",
            },
            "appointment": {
                "keywords": ["appointment", "schedule", "book", "booking", "slot"],
                "task_name": "Appointment Booking",
                "description": "Book an appointment for the customer",
                "data_to_collect": ["customer_name", "preferred_date", "preferred_time"],
                "requires_api": True,
                "api_description": "Check available appointment slots and book an appointment",
            },
            "order_status": {
                "keywords": ["order status", "track order", "where is my order", "order tracking"],
                "task_name": "Order Status Check",
                "description": "Check the status of a customer's order",
                "data_to_collect": ["order_number"],
                "requires_api": True,
                "api_description": "Look up order status by order number",
            },
            "account_inquiry": {
                "keywords": ["account", "balance", "statement"],
                "task_name": "Account Inquiry",
                "description": "Look up customer account information",
                "data_to_collect": ["account_number"],
                "requires_api": True,
                "api_description": "Retrieve account details and balance",
            },
            "complaint": {
                "keywords": ["complaint", "issue", "problem", "wrong"],
                "task_name": "File Complaint",
                "description": "Record and process a customer complaint",
                "data_to_collect": ["customer_name", "issue_description"],
                "requires_api": True,
                "api_description": "Submit a customer complaint ticket",
            },
            "cancel": {
                "keywords": ["cancel", "cancellation", "refund"],
                "task_name": "Cancellation Processing",
                "description": "Process a cancellation or refund request",
                "data_to_collect": ["order_number", "cancellation_reason"],
                "requires_api": True,
                "api_description": "Process cancellation and initiate refund",
            },
            "confirm": {
                "keywords": ["confirm", "verify", "availability", "available"],
                "task_name": "Confirm Availability",
                "description": "Confirm availability via external system",
                "data_to_collect": [],
                "requires_api": True,
                "api_description": "Verify availability through the backend API",
            },
            "faq": {
                "keywords": ["faq", "question", "information", "info", "help"],
                "task_name": "FAQ & Information",
                "description": "Answer frequently asked questions",
                "data_to_collect": [],
                "requires_api": False,
                "api_description": "",
            },
        }

        # Detect greeting (always present)
        if any(kw in text for kw in task_patterns["greet"]["keywords"]) or True:
            greet = task_patterns["greet"].copy()
            tasks.append(greet)

        # Detect other tasks
        for key, pattern in task_patterns.items():
            if key == "greet":
                continue
            if any(kw in text for kw in pattern["keywords"]):
                task = pattern.copy()
                task.pop("keywords", None)
                tasks.append(task)

        # If only greeting detected, try domain-based defaults
        if len(tasks) <= 1:
            domain_defaults = self._domain_default_tasks(domain)
            tasks.extend(domain_defaults)

        # Deduplicate tasks by name
        seen_names = set()
        unique_tasks = []
        for t in tasks:
            if t["task_name"] not in seen_names:
                seen_names.add(t["task_name"])
                unique_tasks.append(t)
        return unique_tasks

    def _domain_default_tasks(self, domain: str) -> list[dict]:
        defaults = {
            "healthcare": [
                {
                    "task_name": "Appointment Booking",
                    "description": "Book an appointment for the customer",
                    "data_to_collect": ["customer_name", "preferred_date", "preferred_time"],
                    "requires_api": True,
                    "api_description": "Check available appointment slots and book an appointment",
                }
            ],
            "e-commerce": [
                {
                    "task_name": "Order Status Check",
                    "description": "Check the status of a customer's order",
                    "data_to_collect": ["order_number"],
                    "requires_api": True,
                    "api_description": "Look up order status by order number",
                }
            ],
            "finance": [
                {
                    "task_name": "Account Inquiry",
                    "description": "Look up customer account information",
                    "data_to_collect": ["account_number"],
                    "requires_api": True,
                    "api_description": "Retrieve account details and balance",
                }
            ],
        }
        return defaults.get(domain, [
            {
                "task_name": "General Inquiry",
                "description": "Handle general customer inquiries",
                "data_to_collect": ["customer_name", "inquiry_details"],
                "requires_api": False,
                "api_description": "",
            }
        ])

    def _detect_functions(self, tasks: list[dict], text: str) -> list[dict]:
        functions = []
        for task in tasks:
            if not task.get("requires_api"):
                continue

            task_name = task["task_name"].lower().replace(" ", "_")
            fn_name = self._task_to_function_name(task_name, task)
            fn_params = self._task_to_function_params(task, text)

            functions.append({
                "name": fn_name,
                "purpose": task.get("api_description", task.get("description", "")),
                "input_params": fn_params,
                "expected_output": self._infer_output(fn_name, task),
            })

        return functions

    def _task_to_function_name(self, task_name: str, task: dict) -> str:
        name_map = {
            "appointment_booking": "get_appointment_slots",
            "order_status_check": "get_order_status",
            "account_inquiry": "get_account_info",
            "file_complaint": "submit_complaint",
            "cancellation_processing": "process_cancellation",
            "confirm_availability": "check_availability",
            "general_inquiry": "search_knowledge_base",
        }
        fn_name = name_map.get(task_name)
        if fn_name:
            return fn_name

        # Generate from task name
        clean = re.sub(r"[^a-z0-9_]", "", task_name)
        return clean if clean else "perform_action"

    def _task_to_function_params(self, task: dict, text: str) -> list[dict]:
        params = []
        for slot in task.get("data_to_collect", []):
            param_type = "string"
            if "date" in slot.lower():
                param_type = "string"  # ISO date string
            elif "number" in slot.lower() or "amount" in slot.lower():
                param_type = "string"
            elif "count" in slot.lower() or "quantity" in slot.lower():
                param_type = "integer"

            params.append({
                "name": slot,
                "type": param_type,
                "description": f"The customer's {slot.replace('_', ' ')}",
            })
        return params

    def _infer_output(self, fn_name: str, task: dict) -> str:
        output_map = {
            "get_appointment_slots": "List of available appointment slots with dates and times",
            "book_appointment": "Booking confirmation with confirmation code",
            "get_order_status": "Order status including tracking info and estimated delivery",
            "get_account_info": "Account details including balance and recent activity",
            "submit_complaint": "Complaint ticket ID and status",
            "process_cancellation": "Cancellation confirmation and refund details",
            "check_availability": "Availability status with available options",
            "search_knowledge_base": "Relevant FAQ entries or knowledge base articles",
        }
        return output_map.get(fn_name, "JSON response with operation result")

    def _detect_persona(self, text: str, domain: str) -> tuple[str, list[str], str]:
        domain_names = {
            "healthcare": "MediBot",
            "e-commerce": "ShopAssist",
            "finance": "FinanceHelper",
            "travel": "TravelBuddy",
            "telecommunications": "TeleConnect",
            "food_delivery": "FoodieBot",
            "insurance": "InsureGuide",
            "education": "EduAssist",
            "real_estate": "PropertyPal",
            "automotive": "AutoCare",
            "general_support": "Ava",
        }
        name = domain_names.get(domain, "Ava")

        if "formal" in text:
            style = "formal"
            traits = ["professional", "courteous", "precise"]
        elif "casual" in text or "friendly" in text:
            style = "casual"
            traits = ["friendly", "upbeat", "approachable"]
        else:
            style = "warm"
            traits = ["friendly", "professional", "helpful"]

        return name, traits, style

    def _detect_voice_gender(self, text: str) -> str:
        if "male voice" in text or "male agent" in text:
            return "male"
        if "female voice" in text or "female agent" in text:
            return "female"
        return "female"

    def _role_for_domain(self, domain: str) -> str:
        roles = {
            "healthcare": "Appointment & Patient Support Agent",
            "e-commerce": "Order & Shopping Support Agent",
            "finance": "Account & Financial Support Agent",
            "travel": "Booking & Travel Support Agent",
            "telecommunications": "Service & Billing Support Agent",
            "food_delivery": "Order & Delivery Support Agent",
            "insurance": "Claims & Policy Support Agent",
            "education": "Enrollment & Course Support Agent",
            "real_estate": "Property & Leasing Support Agent",
            "automotive": "Service & Repair Support Agent",
            "general_support": "Customer Support Agent",
        }
        return roles.get(domain, "Customer Support Agent")

    def _build_flow_summary(self, tasks: list[dict]) -> list[str]:
        steps = ["Step 1: Greet the caller and introduce the service"]
        step_num = 2

        for task in tasks:
            if task["task_name"] == "Greeting":
                continue
            slots = task.get("data_to_collect", [])
            for slot in slots:
                steps.append(
                    f"Step {step_num}: Ask for the customer's {slot.replace('_', ' ')}"
                )
                step_num += 1
            if task.get("requires_api"):
                steps.append(
                    f"Step {step_num}: {task.get('api_description', 'Call external API')}"
                )
                step_num += 1
                steps.append(
                    f"Step {step_num}: Communicate the result to the caller"
                )
                step_num += 1

        steps.append(f"Step {step_num}: Ask if there's anything else")
        steps.append(f"Step {step_num + 1}: End the call politely")
        return steps

    # ────────────────── Step 4: Merge Config ──────────────────

    def _merge_config(
        self,
        analysis: dict[str, Any],
        agent_config: dict[str, Any],
        functions: list[dict[str, Any]],
        platform: str,
    ) -> CXAgentConfig:
        """Merge sub-agent outputs into a single CXAgentConfig."""

        # Build PersonaConfig
        persona_raw = agent_config.get("persona", {})
        persona = PersonaConfig(
            name=persona_raw.get("name", "Ava"),
            role=persona_raw.get("role", "Customer Support Agent"),
            personality_traits=persona_raw.get("personality_traits", ["friendly"]),
            greeting_style=persona_raw.get("greeting_style", "warm"),
            system_prompt=persona_raw.get("system_prompt", "You are a helpful agent."),
            fallback_message=persona_raw.get("fallback_message", "I didn't catch that."),
            escalation_message=persona_raw.get("escalation_message", "Let me transfer you."),
            max_retries=persona_raw.get("max_retries", 3),
        )

        # Build VoiceConfig
        voice_raw = agent_config.get("voice", {})
        voice = VoiceConfig(
            provider=voice_raw.get("provider", "google"),
            voice_id=voice_raw.get("voice_id", "en-US-Neural2-F"),
            gender=voice_raw.get("gender", "female"),
            language=voice_raw.get("language", "en-US"),
            speaking_rate=voice_raw.get("speaking_rate", 1.0),
            pitch=voice_raw.get("pitch", 0.0),
        )

        # Build IntentDefinitions
        intents = []
        for intent_raw in agent_config.get("intents", []):
            phrases = [
                TrainingPhrase(text=p["text"], language=p.get("language", "en-US"))
                for p in intent_raw.get("training_phrases", [])
            ]
            intents.append(IntentDefinition(
                name=intent_raw["name"],
                description=intent_raw.get("description", ""),
                training_phrases=phrases,
                priority=intent_raw.get("priority", 0),
            ))

        # Build FunctionDefinitions
        func_defs = []
        for fn_raw in functions:
            params = [
                FunctionParameter(
                    name=p["name"],
                    type=p.get("type", "string"),
                    description=p.get("description", ""),
                    required=p.get("required", True),
                    default=p.get("default"),
                    enum=p.get("enum"),
                )
                for p in fn_raw.get("parameters", [])
            ]
            endpoint = None
            if fn_raw.get("api_endpoint"):
                ep = fn_raw["api_endpoint"]
                endpoint = APIEndpoint(
                    url=ep.get("url", "/api/v1/action"),
                    method=ep.get("method", "POST"),
                    headers=ep.get("headers", {"Content-Type": "application/json"}),
                    auth_type=ep.get("auth_type"),
                    timeout_seconds=ep.get("timeout_seconds", 10),
                )
            func_defs.append(FunctionDefinition(
                name=fn_raw["name"],
                description=fn_raw.get("description", ""),
                parameters=params,
                returns_description=fn_raw.get("returns_description", ""),
                api_endpoint=endpoint,
                mock_response=fn_raw.get("mock_response"),
            ))

        # Build ConversationFlow
        flow_raw = agent_config.get("conversation_flow")
        flow = None
        if flow_raw:
            flow_nodes = []
            for n in flow_raw.get("nodes", []):
                transitions = [
                    FlowTransition(
                        condition=t["condition"],
                        target_node_id=t["target_node_id"],
                    )
                    for t in n.get("transitions", [])
                ]
                flow_nodes.append(FlowNode(
                    node_id=n["node_id"],
                    type=n.get("type", "response"),
                    label=n.get("label", ""),
                    prompt_text=n.get("prompt_text"),
                    collect_slot=n.get("collect_slot"),
                    function_call=n.get("function_call"),
                    transitions=transitions,
                ))
            flow = ConversationFlow(
                name=flow_raw.get("name", "main_flow"),
                description=flow_raw.get("description", ""),
                entry_node_id=flow_raw.get("entry_node_id", "node_greet"),
                nodes=flow_nodes,
            )

        # Build DeploymentConfig
        deployment = DeploymentConfig(platform=platform)

        return CXAgentConfig(
            persona=persona,
            voice=voice,
            intents=intents,
            functions=func_defs,
            conversation_flow=flow,
            deployment=deployment,
            metadata={
                "source_prompt": analysis.get("domain", ""),
                "generation_mode": "llm" if self.llm_client else "rule_based",
            },
        )
