import yaml
from typing import Any
from datetime import date
from pathlib import Path

PROMPTS_FILE = Path(__file__).resolve().parent / "prompts.yaml"


def _read_prompt() -> dict[str, Any]:
    with open(PROMPTS_FILE, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def _build_fragments(categories: list[str], ref_date: date) -> dict[str, str]:
    today_with_day = ref_date.strftime("%Y-%m-%d (%A)")
    today_date = ref_date.isoformat()
    cat_list = "\n".join(f"    - {c}" for c in categories) or "    - (None defined)"

    data = _read_prompt()
    raw = data.get("_fragments", {})

    return {
        "fragment_context_anchor": raw.get("context_anchor", "").format(
            today_with_day=today_with_day,
            categories_list=cat_list,
        ),
        "fragment_amount_rules": raw.get("amount_rules", ""),
        "fragment_date_rules": raw.get("date_rules", "").format(
            today_date=today_date,
            today_with_day=today_with_day,
        ),
        "fragment_tool_discipline": raw.get("tool_discipline", "")
    }


def load_intent_router_prompt(categories: list[str], reference_date: date | None = None) -> str:
    """Loads and compiles the master text/voice intent router prompt"""
    ref_date = reference_date or date.today()
    fragments = _build_fragments(categories, ref_date)
    today_date = ref_date.isoformat()

    data = _read_prompt()
    template: str = data["intent_router"]["system"]
    return template.format(today_date=today_date, **fragments)


def load_vision_prompt(categories: list[str], reference_date: date | None = None) -> str:
    """Loads and compiles the master vision prompt"""
    ref_date = reference_date or date.today()
    fragments = _build_fragments(categories, ref_date)
    today_date = ref_date.isoformat()

    data = _read_prompt()
    template: str = data["vision_parser"]["system"]
    return template.format(today_date=today_date, **fragments)