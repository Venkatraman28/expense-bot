import json
import logging
import time
from datetime import date
from typing import Any
from openai import OpenAI

from expense_bot.config import settings
from expense_bot.prompts.loader import load_intent_router_prompt
from expense_bot.tools import (
    ROUTER_TOOLS,
    DeleteExpenseArgs,
    LLMResult,
    LogExpenseArgs,
    QueryAnalyticsArgs,
    ToolCallPayload,
    PlanDeletionArgs,
)

logger = logging.getLogger(__name__)


class LLMClient:

    def __init__(self):
        if settings.ACTIVE_LLM_PROVIDER == "groq":
            logger.info("Initializing Groq client (%s)", settings.GROQ_MODEL)
            self.client = OpenAI(
                base_url=settings.GROQ_BASE_URL,
                api_key=settings.GROQ_API_KEY,
                timeout=getattr(settings, "GROQ_TIMEOUT", 30.0),
            )
            self.model = settings.GROQ_MODEL
        else:
            logger.info(
                "Initializing NVIDIA client (%s)", settings.NVIDIA_MODEL
            )
            self.client = OpenAI(
                base_url=settings.NVIDIA_BASE_URL,
                api_key=settings.NVIDIA_API_KEY,
                timeout=getattr(settings, "NVIDIA_TIMEOUT", 60.0),
            )
            self.model = settings.NVIDIA_MODEL

    def route_message(
        self,
        user_text: str,
        categories: list[str],
        reference_date: date | None = None,
    ) -> LLMResult:
        system_prompt = load_intent_router_prompt(
            categories=categories,
            reference_date=reference_date,
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "tools": ROUTER_TOOLS,
            "tool_choice": "auto",
            "temperature": settings.TEMPERATURE,
        }

        # Option 1: Route reasoning effort safely per provider
        if settings.REASONING_EFFORT:
            if settings.ACTIVE_LLM_PROVIDER == "groq":
                payload["reasoning_effort"] = settings.REASONING_EFFORT
            elif settings.ACTIVE_LLM_PROVIDER == "nvidia":
                payload["extra_body"] = {
                    "reasoning_effort": settings.REASONING_EFFORT
                }

        start = time.perf_counter()
        try:
            response = self.client.chat.completions.create(**payload)
            latency_ms = int((time.perf_counter() - start) * 1000)

            msg = response.choices[0].message
            usage = response.usage

            # Branch A: Model called a tool
            if msg.tool_calls:
                call = msg.tool_calls[0]
                tool_name = call.function.name
                raw_args = json.loads(call.function.arguments)

                validated_data: Any
                if tool_name == "log_expense":
                    validated_data = LogExpenseArgs(**raw_args)
                elif tool_name == "query_analytics":
                    validated_data = QueryAnalyticsArgs(**raw_args)
                elif tool_name == "delete_or_undo_expense":
                    validated_data = DeleteExpenseArgs(**raw_args)
                elif tool_name == "plan_deletion":
                    validated_data = PlanDeletionArgs(**raw_args)
                else:
                    raise ValueError(f"Unrecognized tool: {tool_name}")

                return LLMResult(
                    result_type="tool_call",
                    tool_call=ToolCallPayload(
                        name=tool_name, data=validated_data
                    ),
                    text_content=None,
                    raw_response=call.function.arguments,
                    latency_ms=latency_ms,
                    prompt_tokens=usage.prompt_tokens if usage else None,
                    completion_tokens=(
                        usage.completion_tokens if usage else None
                    ),
                    total_tokens=usage.total_tokens if usage else None,
                    model_name=self.model,
                    status="success",
                )

            # Branch B: Plain conversational text (chitchat, pranks, clarification)
            return LLMResult(
                result_type="text",
                tool_call=None,
                text_content=msg.content or "Got it!",
                raw_response=msg.content or "",
                latency_ms=latency_ms,
                prompt_tokens=usage.prompt_tokens if usage else None,
                completion_tokens=usage.completion_tokens if usage else None,
                total_tokens=usage.total_tokens if usage else None,
                model_name=self.model,
                status="success",
            )

        except Exception as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error("LLM routing call failed: %s", exc, exc_info=True)
            return LLMResult(
                result_type="text",
                tool_call=None,
                text_content="Sorry, I ran into an issue processing that. Please try again.",
                raw_response="",
                latency_ms=latency_ms,
                model_name=self.model,
                status="error",
                error_message=str(exc),
            )