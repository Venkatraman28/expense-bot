import base64
import json
import logging
from datetime import date
from typing import Any
from openai import OpenAI
from expense_bot.config import settings
from expense_bot.prompts.loader import load_vision_prompt
from expense_bot.tools.definitions import ROUTER_TOOLS
from expense_bot.tools.schemas import LogExpenseArgs

logger = logging.getLogger(__name__)


class VisionClient:
    def __init__(self):
        # 1. Initialize Groq client
        self.groq_client = (
            OpenAI(
                base_url=settings.GROQ_BASE_URL,
                api_key=settings.GROQ_API_KEY,
            )
            if getattr(settings, "GROQ_API_KEY", None)
            else None
        )
        self.groq_model = settings.GROQ_VISION_MODEL

        # 2. Initialize NVIDIA client
        self.nvidia_client = (
            OpenAI(
                base_url=settings.NVIDIA_BASE_URL,
                api_key=settings.NVIDIA_API_KEY,
            )
            if getattr(settings, "NVIDIA_API_KEY", None)
            else None
        )
        self.nvidia_model = settings.NVIDIA_VISION_MODEL

    def _get_provider_pipeline(self) -> list[tuple[str, OpenAI | None, str]]:
        """
        Determines the execution order based on settings.ACTIVE_LLM_PROVIDER.
        Returns a list of (provider_name, client, model) tuples.
        """
        active_provider = settings.ACTIVE_VISION_LLM_PROVIDER

        if active_provider == "nvidia":
            return [
                ("nvidia", self.nvidia_client, self.nvidia_model),
                ("groq", self.groq_client, self.groq_model),
            ]
        else:
            return [
                ("groq", self.groq_client, self.groq_model),
                ("nvidia", self.nvidia_client, self.nvidia_model),
            ]

    def _execute_vision_call(
        self,
        client: OpenAI,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> tuple[LogExpenseArgs | None, str | None]:
        """Performs the OpenAI-compatible chat completion with tool calling."""
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
        )

        msg = response.choices[0].message

        # Check for tool call execution
        if msg.tool_calls:
            call = msg.tool_calls[0]
            if call.function.name == "log_expense":
                args_dict = json.loads(call.function.arguments)
                return LogExpenseArgs(**args_dict), None

        # Return text response if model gave a conversational fallback (e.g. blurry/bad image)
        return None, msg.content or "Could not extract clear transaction details."

    def parse_receipt(
        self,
        image_bytes: bytes,
        categories: list[str],
        user_caption: str | None = None,
        reference_date: date | None = None,
    ) -> tuple[LogExpenseArgs | None, str | None]:
        """
        Extracts expense data from an image.
        Uses ACTIVE_LLM_PROVIDER first, then fails over to the alternative provider.
        """
        system_prompt = load_vision_prompt(
            categories=categories,
            reference_date=reference_date or date.today(),
        )

        b64_image = base64.b64encode(image_bytes).decode("utf-8")
        user_text = (
            user_caption
            if user_caption
            else "Extract all transaction details from this receipt or payment screenshot."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_image}"},
                    },
                ],
            },
        ]

        vision_tools = [t for t in ROUTER_TOOLS if t["function"]["name"] == "log_expense"]
        pipeline = self._get_provider_pipeline()

        for idx, (provider_name, client, model) in enumerate(pipeline):
            if not client:
                logger.warning("Provider %s is not configured (missing API key).", provider_name)
                continue

            try:
                role = "Primary" if idx == 0 else "Fallback"
                logger.info("%s vision inference using %s (%s)...", role, provider_name.upper(), model)

                return self._execute_vision_call(
                    client=client,
                    model=model,
                    messages=messages,
                    tools=vision_tools,
                )

            except Exception as e:
                logger.warning(
                    "%s provider (%s) vision call failed: %s",
                    "Primary" if idx == 0 else "Secondary",
                    provider_name,
                    e,
                )
                # Continue to next provider in loop

        return None, "⚠️ Vision extraction failed on all configured providers."