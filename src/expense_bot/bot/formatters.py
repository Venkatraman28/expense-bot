from typing import Any

from expense_bot.bot.text import esc


def format_analytics_report(
    summary: dict[str, Any],
    breakdown: list[dict[str, Any]],
    period_label: str,
    category_filter: str | None = None,
) -> str:
    period_label = esc(period_label)
    category_filter = esc(category_filter) if category_filter else None

    total_amount = float(summary.get("total_amount", 0.0))
    total_count = int(summary.get("total_count", 0))
    avg_amount = float(summary.get("average_amount", 0.0))

    if total_count == 0 or total_amount == 0.0:
        filter_note = f" for category *{category_filter}*" if category_filter else ""
        return f"📊 *Report: {period_label}*\n\nNo recorded transactions found{filter_note}."

    lines = [
        f"📊 *Spending Report: {period_label}*",
        f"💰 *Total:* `₹{total_amount:,.2f}`  |  🧾 *Count:* `{total_count}`",
        f"📈 *Avg/Transaction:* `₹{avg_amount:,.2f}`",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    if category_filter:
        lines.append(f"🔍 *Filter:* {category_filter}")
        return "\n".join(lines)

    lines.append("*Category Distribution:*")
    for item in breakdown:
        cat_total = float(item["category_total"])
        pct = (cat_total / total_amount) * 100 if total_amount > 0 else 0
        filled = int(round(pct / 10))
        bar = "█" * filled + "░" * (10 - filled)
        lines.append(
            f"`{bar}` *{pct:4.1f}%* — {esc(item['category_name'])}\n    `₹{cat_total:,.2f}` ({item['expense_count']} transactions)"
        )

    return "\n".join(lines)