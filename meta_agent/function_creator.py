"""
Function Creator Sub-Agent

Responsible for generating function definitions that CX agents use to
interact with external APIs. For each function it produces:
  - A detailed description (for LLM context during function calling)
  - Typed parameter schemas
  - REST API endpoint mappings
  - Realistic mock responses for testing
  - OpenAI-compatible tool schemas

This sub-agent works alongside the Agent Creator; the Orchestrator
merges their outputs into a single CXAgentConfig.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .models import (
    APIEndpoint,
    FunctionDefinition,
    FunctionParameter,
    HTTPMethod,
    ParamType,
)
from .prompts import FUNCTION_CREATOR_PROMPT

logger = logging.getLogger(__name__)


class FunctionCreator:
    """
    Sub-agent that generates callable function definitions from
    the orchestrator's analysis brief.
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client
        self.system_prompt = FUNCTION_CREATOR_PROMPT

    async def create_functions(
        self,
        functions_needed: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        Generate full function definitions from the requirements list.

        Args:
            functions_needed: List of function requirement dicts from
                              the orchestrator's analysis brief.

        Returns:
            List of complete function definition dicts.
        """
        if not functions_needed:
            return []

        if self.llm_client:
            return await self._create_with_llm(functions_needed)
        return self._create_with_rules(functions_needed)

    # ────────────────── LLM-Powered Generation ──────────────────

    async def _create_with_llm(
        self, functions_needed: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Use OpenAI API to generate function definitions."""
        try:
            response = await self.llm_client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": json.dumps(functions_needed, indent=2)},
                ],
                temperature=0.3,
                max_tokens=3000,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            result = json.loads(raw)
            return result.get("functions", [])
        except Exception as e:
            logger.warning("LLM call failed (%s), falling back to rules", e)
            return self._create_with_rules(functions_needed)

    # ────────────────── Rule-Based Fallback ──────────────────

    def _create_with_rules(
        self, functions_needed: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Deterministic rule-based function definition generation."""
        functions = []
        for fn_req in functions_needed:
            fn_def = self._build_function(fn_req)
            functions.append(fn_def)
        return functions

    def _build_function(self, fn_req: dict[str, Any]) -> dict[str, Any]:
        """Build a single function definition from a requirement."""
        name = fn_req.get("name", "unknown_function")
        purpose = fn_req.get("purpose", "Perform an action")
        input_params = fn_req.get("input_params", [])
        expected_output = fn_req.get("expected_output", "JSON response")

        # Build parameters
        parameters = []
        for param in input_params:
            param_type = param.get("type", "string")
            parameters.append({
                "name": param.get("name", "param"),
                "type": param_type,
                "description": param.get("description", f"The {param.get('name', 'param')} value"),
                "required": param.get("required", True),
                "default": param.get("default"),
                "enum": param.get("enum"),
            })

        # Determine HTTP method and build endpoint
        method = self._infer_http_method(name, purpose)
        endpoint = self._build_endpoint(name, method, parameters)

        # Generate mock response
        mock = self._generate_mock_response(name, expected_output, parameters)

        return {
            "name": name,
            "description": (
                f"{purpose}. This function is called during the conversation when "
                f"the agent needs to {purpose.lower()}. "
                f"Returns: {expected_output}"
            ),
            "parameters": parameters,
            "returns_description": expected_output,
            "api_endpoint": endpoint,
            "mock_response": mock,
        }

    def _infer_http_method(self, name: str, purpose: str) -> str:
        """Infer the HTTP method from the function name and purpose."""
        name_lower = name.lower()
        purpose_lower = purpose.lower()

        if any(kw in name_lower for kw in ["get", "fetch", "list", "check", "search", "find", "lookup"]):
            return "GET"
        if any(kw in name_lower for kw in ["create", "book", "schedule", "submit", "register"]):
            return "POST"
        if any(kw in name_lower for kw in ["update", "modify", "change"]):
            return "PUT"
        if any(kw in name_lower for kw in ["delete", "cancel", "remove"]):
            return "DELETE"
        if any(kw in purpose_lower for kw in ["retrieve", "query", "look up"]):
            return "GET"
        return "POST"

    def _build_endpoint(
        self, name: str, method: str, parameters: list[dict]
    ) -> dict[str, Any]:
        """Build an API endpoint configuration."""
        # Generate URL from function name
        # e.g., get_appointment_slots → /api/v1/appointments/slots
        parts = name.split("_")
        # Remove verb prefixes
        verbs = {"get", "fetch", "create", "book", "update", "delete", "check", "list", "search", "submit", "cancel"}
        resource_parts = [p for p in parts if p.lower() not in verbs]
        if not resource_parts:
            resource_parts = parts[1:] if len(parts) > 1 else parts

        url_path = "/".join(resource_parts)

        # For GET requests with ID-like params, use path parameters
        if method == "GET":
            id_params = [p for p in parameters if "id" in p["name"].lower()]
            if id_params:
                url_path += f"/{{{id_params[0]['name']}}}"

        return {
            "url": f"/api/v1/{url_path}",
            "method": method,
            "headers": {"Content-Type": "application/json"},
            "auth_type": "bearer",
            "timeout_seconds": 10,
        }

    def _generate_mock_response(
        self,
        name: str,
        expected_output: str,
        parameters: list[dict],
    ) -> dict[str, Any]:
        """Generate a realistic mock response for testing."""
        name_lower = name.lower()

        # Domain-specific mock responses
        mock_templates: dict[str, dict[str, Any]] = {
            "appointment": {
                "success": True,
                "data": {
                    "available_slots": [
                        {"date": "2026-02-24", "time": "09:00 AM", "available": True},
                        {"date": "2026-02-24", "time": "10:30 AM", "available": True},
                        {"date": "2026-02-24", "time": "02:00 PM", "available": True},
                    ],
                    "timezone": "America/New_York",
                },
                "message": "Available slots retrieved successfully",
            },
            "book": {
                "success": True,
                "data": {
                    "booking_id": "BK-20260224-001",
                    "status": "confirmed",
                    "confirmation_code": "CONF-7829",
                    "date": "2026-02-24",
                    "time": "10:30 AM",
                },
                "message": "Appointment booked successfully",
            },
            "order": {
                "success": True,
                "data": {
                    "order_id": "ORD-2026-4521",
                    "status": "shipped",
                    "tracking_number": "1Z999AA10123456784",
                    "estimated_delivery": "2026-02-26",
                    "items": [
                        {"name": "Product A", "quantity": 1, "price": 29.99}
                    ],
                },
                "message": "Order details retrieved successfully",
            },
            "account": {
                "success": True,
                "data": {
                    "account_id": "ACC-78291",
                    "name": "John Smith",
                    "status": "active",
                    "balance": 1250.00,
                    "last_activity": "2026-02-23",
                },
                "message": "Account information retrieved successfully",
            },
            "cancel": {
                "success": True,
                "data": {
                    "cancellation_id": "CAN-20260224-003",
                    "status": "cancelled",
                    "refund_amount": 29.99,
                    "refund_eta": "3-5 business days",
                },
                "message": "Cancellation processed successfully",
            },
            "transfer": {
                "success": True,
                "data": {
                    "transfer_id": "TRF-001",
                    "department": "Customer Support",
                    "estimated_wait": "2 minutes",
                    "queue_position": 3,
                },
                "message": "Transfer initiated",
            },
            "verify": {
                "success": True,
                "data": {
                    "verified": True,
                    "customer_id": "CUST-45678",
                    "name": "John Smith",
                },
                "message": "Customer verified successfully",
            },
        }

        # Find matching template
        for keyword, template in mock_templates.items():
            if keyword in name_lower:
                return template

        # Generic fallback mock
        return {
            "success": True,
            "data": {
                "result": f"Operation '{name}' completed successfully",
                "id": "RES-20260224-001",
                "timestamp": "2026-02-24T10:30:00Z",
            },
            "message": f"{name.replace('_', ' ').title()} completed successfully",
        }

    @staticmethod
    def to_openai_tools(functions: list[dict[str, Any]]) -> list[dict]:
        """Convert function definitions to OpenAI tool schemas."""
        tools = []
        for fn in functions:
            properties = {}
            required = []
            for p in fn.get("parameters", []):
                prop: dict[str, Any] = {
                    "type": p.get("type", "string"),
                    "description": p.get("description", ""),
                }
                if p.get("enum"):
                    prop["enum"] = p["enum"]
                if p.get("default") is not None:
                    prop["default"] = p["default"]
                properties[p["name"]] = prop
                if p.get("required", True):
                    required.append(p["name"])

            tools.append({
                "type": "function",
                "function": {
                    "name": fn["name"],
                    "description": fn.get("description", ""),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
        return tools
