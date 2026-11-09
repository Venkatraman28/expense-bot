from datetime import date
import logging
import uuid
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from expense_bot.bot.formatters import format_analytics_report
from expense_bot.bot.text import esc
from expense_bot.clients.audio_client import AudioClient
from expense_bot.clients.llm_client import LLMClient
from expense_bot.clients.vision_client import VisionClient
from expense_bot.database import SessionLocal
from expense_bot.repositories.expense_repo import ExpenseRepository
from expense_bot.tools import (
    DeleteExpenseArgs,
    LogExpenseArgs,
    PlanDeletionArgs,
    QueryAnalyticsArgs,
)

logger = logging.getLogger(__name__)
llm_client = LLMClient()
audio_client = AudioClient()
vision_client = VisionClient()


# ---------------------------------------------------------
# Commands
# ---------------------------------------------------------

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Greets the allowed user and explains usage."""
    user = update.effective_user
    greeting_name = user.first_name if user else "there"

    await update.message.reply_text(
        f"👋 Welcome {esc(greeting_name)}!\n\n"
        "Your AI-native expense assistant is online.\n\n"
        "You can chat naturally:\n"
        "• *Log Expenses:* _Spent 350 on Swiggy lunch and 80 for chai_\n"
        "• *Check Stats:* _How much did I spend in Jan 2026?_ or _Show food spend last week_\n"
        "• *Undo / Delete:* _Undo last expense_ or _Delete yesterday's cab ride_\n"
        "• *Photos & Audio:* Send voice notes or photos of bills and UPI payments.\n\n"
        "Commands:\n"
        "• `/categories` — View active categories\n"
        "• `/addcategory <name>` — Create a custom category\n"
        "• `/delcategory <name>` — Delete custom category (e.g. `/delcategory Gym, Books`)\n"
        "• `/budgets` — Check budget limits & progress\n"
        "• `/setbudget <Cat> <Amt>` — Set category or Overall limit\n"
        "• `/delbudget <Cat>` — Remove budget limit\n"
        "• `/start` — Show this guide",
        parse_mode=ParseMode.MARKDOWN,
    )


async def categories_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Fetches and displays active categories."""
    user_id = update.effective_user.id

    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        categories = repo.get_categories(user_id)

    if not categories:
        await update.message.reply_text("No categories found.")
        return

    lines = []
    for cat in categories:
        tag = " *(custom)*" if cat.get("is_custom") else ""
        lines.append(f"• {esc(cat['name'])}{tag}")

    message = "📁 *Your Active Categories:*\n\n" + "\n".join(lines)
    await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)


# ---------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------

async def handle_log_expense_tool(
    status_msg,
    context: ContextTypes.DEFAULT_TYPE,
    args: LogExpenseArgs,
    latency_ms: int,
) -> None:
    """Renders the interactive confirmation card with UUID action tracking."""
    items = args.expenses
    if not items:
        await status_msg.edit_text(
            "👋 I didn't detect any concrete amounts or items in that expense.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    action_id = str(uuid.uuid4())[:8]
    if "staged_expenses" not in context.user_data:
        context.user_data["staged_expenses"] = {}

    context.user_data["staged_expenses"][action_id] = [
        item.model_dump(mode="json") for item in items
    ]

    total_amount = sum(item.amount for item in items)
    count = len(items)

    lines = [f"💳 *Confirm Expense{'s' if count > 1 else ''}*", "━━━━━━━━━━━━━━━━━━━━"]
    for idx, item in enumerate(items, 1):
        category = esc(item.category)
        cat_badge = f"{category} 🆕" if item.is_new_category else category
        prefix = f"{idx}. " if count > 1 else ""
        lines.append(f"{prefix}*₹{item.amount:,.2f}* — {cat_badge}")
        if item.merchant:
            lines.append(f"   🏪 Vendor: {esc(item.merchant)}")
        if item.note:
            lines.append(f"   📝 Note: {esc(item.note)}")
        lines.append(f"   📅 Date: {item.spent_on}")
        if count > 1 and idx < count:
            lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    if count > 1:
        lines.append(f"💰 *Total ({count} items):* ₹{total_amount:,.2f}")
    if latency_ms > 0:
        lines.append(f"⚡ _Inference: {latency_ms}ms_")

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"✅ Save ({count})", callback_data=f"save:{action_id}"),
                InlineKeyboardButton("❌ Discard", callback_data=f"discard:{action_id}"),
            ]
        ]
    )

    await status_msg.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )


async def handle_query_analytics_tool(
    status_msg,
    user_id: int,
    args: QueryAnalyticsArgs,
) -> None:
    """Executes database aggregate queries and renders summary metrics."""
    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        summary = repo.get_summary_range(
            user_id=user_id,
            start_date=args.start_date,
            end_date=args.end_date,
            category_name=args.category_name,
        )
        breakdown = repo.get_breakdown_range(
            user_id=user_id,
            start_date=args.start_date,
            end_date=args.end_date,
        )

    report_text = format_analytics_report(
        summary=summary,
        breakdown=breakdown,
        period_label=args.period_label,
        category_filter=args.category_name,
    )
    await status_msg.edit_text(report_text, parse_mode=ParseMode.MARKDOWN)


async def handle_delete_expense_tool(
    status_msg,
    user_id: int,
    args: DeleteExpenseArgs,
) -> None:
    """Executes undo or targeted expense deletions."""
    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        if args.target == "last":
            deleted = repo.delete_last_expense(user_id=user_id)
            if not deleted:
                await status_msg.edit_text(
                    "⚠️ No recent expenses found to undo.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

            merchant_str = f" from *{deleted['merchant']}*" if deleted.get("merchant") else ""
            msg = (
                f"🗑️ *Undone Last Expense:*\n"
                f"• Removed *₹{float(deleted['amount']):,.2f}* ({deleted['category_name']}){merchant_str} logged on `{deleted['spent_on']}`."
            )
            await status_msg.edit_text(msg, parse_mode=ParseMode.MARKDOWN)
        else:
            deleted_list = repo.delete_specific_expenses(
                user_id=user_id,
                amount=args.amount,
                merchant=args.merchant,
                spent_on=args.spent_on,
            )
            if not deleted_list:
                await status_msg.edit_text(
                    "⚠️ No expenses matched your deletion criteria.",
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

            lines = [
                f"🗑️ *Deleted {len(deleted_list)} Expense(s):*",
                "━━━━━━━━━━━━━━━━━━━━",
            ]
            for item in deleted_list:
                m_str = f" • _{item['merchant']}_" if item.get("merchant") else ""
                lines.append(
                    f"• *₹{float(item['amount']):,.2f}* — {item['category_name']}{m_str} `[{item['spent_on']}]`"
                )
            await status_msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def handle_plan_deletion_tool(
    status_msg,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    args: PlanDeletionArgs,
) -> None:
    """Agent preview handler: finds matching records and prompts for user confirmation."""
    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        targets = repo.preview_deletion(
            user_id=user_id,
            sql_where_clause=args.sql_where_clause,
        )

    if not targets:
        await status_msg.edit_text(
            f"ℹ️ Found no matching expenses for: *{esc(args.explanation)}*",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    action_id = str(uuid.uuid4())[:8]
    if "staged_deletions" not in context.user_data:
        context.user_data["staged_deletions"] = {}

    target_ids = [t["id"] for t in targets]
    context.user_data["staged_deletions"][action_id] = target_ids

    total_amount = sum(float(t["amount"]) for t in targets)
    count = len(targets)

    lines = [
        f"⚠️ *Confirm Deletion: {esc(args.explanation)}*",
        f"Targeting *{count}* transaction(s) totaling `₹{total_amount:,.2f}`:",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for item in targets[:5]:
        m_str = f" • _{esc(item['merchant'])}_" if item.get("merchant") else ""
        lines.append(
            f"• *₹{float(item['amount']):,.2f}* — {esc(item['category_name'])}{m_str} `[{item['spent_on']}]`"
        )

    if count > 5:
        lines.append(f"_...and {count - 5} more transactions._")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("Are you sure you want to permanently delete these?")

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"🗑️ Confirm Delete ({count})",
                    callback_data=f"del_confirm:{action_id}",
                ),
                InlineKeyboardButton(
                    "❌ Keep",
                    callback_data=f"del_cancel:{action_id}",
                ),
            ]
        ]
    )

    await status_msg.edit_text(
        "\n".join(lines),
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN,
    )


# ---------------------------------------------------------
# Core Text Processing Pipeline (Shared by Text & Audio)
# ---------------------------------------------------------

async def _process_text_input(
    user_text: str,
    status_msg,
    user,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Core pipeline: fetches categories, routes via LLM, logs telemetry, and dispatches tools."""
    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        categories = repo.get_categories(user.id)
        cat_names = [c["name"] for c in categories]

    # Intent routing via LLM
    llm_result = llm_client.route_message(user_text, cat_names)

    # Telemetry logging to llm_calls table
    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        repo.log_llm_call(
            user_id=user.id,
            task="intent_routing",
            model_name=llm_result.model_name,
            latency_ms=llm_result.latency_ms,
            prompt_tokens=llm_result.prompt_tokens,
            completion_tokens=llm_result.completion_tokens,
            total_tokens=llm_result.total_tokens,
            raw_prompt=user_text,
            raw_response=llm_result.raw_response or (llm_result.error_message or ""),
            status=llm_result.status,
            error_message=llm_result.error_message,
        )

    if llm_result.status != "success":
        await status_msg.edit_text(
            "⚠️ Sorry, I ran into an error processing that. Please try again.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Dispatch tool calls
    if llm_result.result_type == "tool_call" and llm_result.tool_call:
        tool_name = llm_result.tool_call.name
        tool_data = llm_result.tool_call.data

        if tool_name == "log_expense":
            await handle_log_expense_tool(
                status_msg,
                context,
                tool_data,
                llm_result.latency_ms,
            )
        elif tool_name == "query_analytics":
            await handle_query_analytics_tool(
                status_msg,
                user.id,
                tool_data,
            )
        elif tool_name == "plan_deletion":
            await handle_plan_deletion_tool(
                status_msg,
                context,
                user.id,
                tool_data,
            )
        elif tool_name == "delete_or_undo_expense":
            await handle_delete_expense_tool(
                status_msg,
                user.id,
                tool_data,
            )
        else:
            logger.warning("Unmapped tool invoked by model: %s", tool_name)
            await status_msg.edit_text(
                f"⚠️ Action not recognized: `{tool_name}`",
                parse_mode=ParseMode.MARKDOWN,
            )
    else:
        await status_msg.edit_text(llm_result.text_content or "Got it!")


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Intercepts natural text and forwards to the core processing engine."""
    user = update.effective_user
    user_text = update.message.text.strip()
    status_msg = await update.message.reply_text("🧠 Thinking...")
    await _process_text_input(user_text, status_msg, user, context)


# ---------------------------------------------------------
# Audio Handler
# ---------------------------------------------------------

async def voice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Downloads voice note from Telegram, transcribes it, and routes it through the pipeline."""
    voice_obj = update.message.voice or update.message.audio
    if not voice_obj:
        return

    user = update.effective_user
    status_msg = await update.message.reply_text("🎙️ Listening...")

    try:
        tg_file = await context.bot.get_file(voice_obj.file_id)
        audio_bytes = await tg_file.download_as_bytearray()

        transcript = audio_client.transcribe(bytes(audio_bytes), filename="voice.ogg")

        if not transcript:
            await status_msg.edit_text("⚠️ Could not hear anything clearly. Please try again.")
            return

        await status_msg.edit_text(
            f"🗣️ _\"{transcript}\"_\n🧠 Thinking...",
            parse_mode=ParseMode.MARKDOWN,
        )

        await _process_text_input(transcript, status_msg, user, context)

    except Exception as e:
        logger.error("Audio transcription failed: %s", e, exc_info=True)
        await status_msg.edit_text("⚠️ Failed to transcribe audio note. Please try typing.")


# ---------------------------------------------------------
# Vision / Photo Handler
# ---------------------------------------------------------

async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Downloads receipts or payment screenshots, extracts via vision model, and stages for confirmation."""
    photos = update.message.photo
    if not photos:
        return

    highest_res_photo = photos[-1]
    user_caption = update.message.caption or ""
    user = update.effective_user

    status_msg = await update.message.reply_text("🔍 Analyzing receipt / image...")

    try:
        # Pass explicit read_timeout (60s) to allow Telegram servers time to transfer the photo
        tg_file = await context.bot.get_file(highest_res_photo.file_id, read_timeout=60.0)
        image_bytes = await tg_file.download_as_bytearray(read_timeout=60.0)

        with SessionLocal() as session:
            repo = ExpenseRepository(session)
            categories = repo.get_categories(user.id)
            cat_names = [c["name"] for c in categories]

        extracted_args, text_reply = vision_client.parse_receipt(
            image_bytes=bytes(image_bytes),
            categories=cat_names,
            user_caption=user_caption,
        )

        if extracted_args and extracted_args.expenses:
            await handle_log_expense_tool(
                status_msg=status_msg,
                context=context,
                args=extracted_args,
                latency_ms=0,
            )
        else:
            await status_msg.edit_text(
                text_reply or "⚠️ Could not detect a valid expense in this image.",
                parse_mode=ParseMode.MARKDOWN,
            )

    except Exception as e:
        logger.error("Vision processing failed: %s", e, exc_info=True)
        await status_msg.edit_text("⚠️ Failed to parse image. Please try typing or snapping a clearer picture.")


# ---------------------------------------------------------
# Callback Query State Machine (Save / Discard)
# ---------------------------------------------------------

async def expense_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles Save/Discard for logged expenses and Confirm/Cancel for agentic deletions."""
    query = update.callback_query
    await query.answer()

    data = query.data
    action, action_id = data.split(":")
    user_id = update.effective_user.id

    if action == "del_cancel":
        context.user_data.get("staged_deletions", {}).pop(action_id, None)
        await query.edit_message_text(
            "❌ *Deletion cancelled. Your records are untouched.*",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if action == "del_confirm":
        target_ids = context.user_data.get("staged_deletions", {}).pop(action_id, None)

        if not target_ids:
            await query.edit_message_text(
                "⚠️ This deletion request has expired or was already processed.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        with SessionLocal() as session:
            repo = ExpenseRepository(session)
            deleted_count = repo.execute_deletion_by_ids(user_id=user_id, ids=target_ids)

        await query.edit_message_text(
            f"🗑️ *Deleted Successfully!*\n\n"
            f"Removed {deleted_count} expense record{'s' if deleted_count > 1 else ''} from your account.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    staged_items = context.user_data.get("staged_expenses", {}).pop(action_id, None)

    if not staged_items:
        await query.edit_message_text(
            "⚠️ This confirmation has expired or was already processed.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if action == "discard":
        await query.edit_message_text("❌ Discarded.", parse_mode=ParseMode.MARKDOWN)
        return

    if action == "save":
        saved_count = 0
        total_amount = 0.0
        affected_category_ids: list[int] = []

        with SessionLocal() as session:
            repo = ExpenseRepository(session)
            for item in staged_items:
                cat_id = repo.get_or_create_category(user_id, item["category"])
                repo.add_expense(
                    user_id=user_id,
                    category_id=cat_id,
                    amount=item["amount"],
                    spent_on=date.fromisoformat(item["spent_on"]),
                    merchant=item.get("merchant"),
                    note=item.get("note"),
                )
                affected_category_ids.append(cat_id)
                total_amount += item["amount"]
                saved_count += 1

            # Evaluate budget alerts for touched categories and overall threshold
            alerts = repo.check_budget_alerts(
                user_id=user_id,
                category_ids=affected_category_ids,
            )

        reply_text = (
            f"✅ *Saved Successfully!*\n\n"
            f"Logged {saved_count} item{'s' if saved_count > 1 else ''} totaling *₹{total_amount:,.2f}*."
        )

        if alerts:
            reply_text += "\n\n━━━━━━━━━━━━━━━━━━━━\n" + "\n".join(alerts)

        await query.edit_message_text(
            reply_text,
            parse_mode=ParseMode.MARKDOWN,
        )


# ---------------------------------------------------------
# Global error handler
# ---------------------------------------------------------

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Catch any unhandled error so the bot never goes silent."""
    logger.error("Unhandled error while handling an update", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "⚠️ Something went wrong. Please try again."
        )


# ---------------------------------------------------------
# Application enhancements
# ---------------------------------------------------------

async def add_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /addcategory <Category Name>."""
    user = update.effective_user
    args = context.args

    if not args:
        await update.message.reply_text(
            "⚠️ Please provide a category name.\n\n"
            "Example:\n"
            "`/addcategory Gym & Fitness`\n"
            "`/addcategory Subscriptions`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    category_name = " ".join(args).strip().title()

    if len(category_name) > 30:
        await update.message.reply_text("⚠️ Category name must be under 30 characters.")
        return

    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        category_id, created = repo.add_new_category(user_id=user.id, name=category_name)

    if created:
        await update.message.reply_text(
            f"✅ *Category Created!*\n\n"
            f"📁 Added `*{esc(category_name)}*` *(custom)* to your active categories.\n"
            f"The LLM router will now automatically map relevant expenses to it.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            f"ℹ️ Category `*{esc(category_name)}*` already exists in your active list.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def delete_category_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /delcategory <Category1>, <Category2> (single or bulk)."""
    user = update.effective_user
    args = context.args

    if not args:
        await update.message.reply_text(
            "⚠️ Please specify which category or categories to delete.\n\n"
            "*Single:* `/delcategory Gym`\n"
            "*Bulk:* `/delcategory Gym, Subscriptions, Books`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Split on commas to support multiple multi-word categories cleanly
    raw_input = " ".join(args)
    category_targets = [item.strip() for item in raw_input.split(",") if item.strip()]

    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        result = repo.delete_categories(
            user_id=user.id,
            targets=category_targets,
            reassign_to="Other",  # Automatically reassigns any existing expenses to "Other"
        )

    deleted_names = result["deleted_names"]
    skipped_names = result["skipped_names"]

    response_lines = []
    if deleted_names:
        names_str = ", ".join(f"`{esc(name)}`" for name in deleted_names)
        response_lines.append(f"🗑️ *Deleted {len(deleted_names)} Category(s):* {names_str}")
        response_lines.append("_(Any associated expenses have been safely moved to 'Other')_")

    if skipped_names:
        skipped_str = ", ".join(f"`{esc(name)}`" for name in skipped_names)
        response_lines.append(f"⚠️ *Skipped default / non-custom categories:* {skipped_str}")

    if not deleted_names and not skipped_names:
        response_lines.append("⚠️ No matching categories found to delete.")

    await update.message.reply_text("\n\n".join(response_lines), parse_mode=ParseMode.MARKDOWN)


async def set_budget_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /setbudget <Category | Overall> <Amount>."""
    user = update.effective_user
    args = context.args

    if not args or len(args) < 2:
        await update.message.reply_text(
            "⚠️ *Usage:*\n"
            "`/setbudget <Category> <Amount>`\n\n"
            "*Examples:*\n"
            "• `/setbudget Food 15000`\n"
            "• `/setbudget Travel 8000`\n"
            "• `/setbudget Overall 50000`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    # Last argument is the amount, preceding tokens make up the category name
    amount_str = args[-1].replace(",", "").replace("₹", "").strip()
    category_name = " ".join(args[:-1]).strip()

    try:
        limit_val = float(amount_str)
        if limit_val <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("⚠️ Please enter a valid positive budget amount.")
        return

    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        target_name, created = repo.set_budget(user_id=user.id, category_name=category_name, limit=limit_val)

    action_word = "Set" if created else "Updated"
    await update.message.reply_text(
        f"🎯 *Monthly Budget {action_word}!*\n\n"
        f"• Target: `*{esc(target_name)}*`\n"
        f"• Limit: *₹{limit_val:,.2f}* / month",
        parse_mode=ParseMode.MARKDOWN,
    )


async def budgets_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /budgets: displays all active budgets and spending bars for this month."""
    user = update.effective_user

    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        budgets = repo.get_budgets_progress(user_id=user.id)

    if not budgets:
        await update.message.reply_text(
            "ℹ️ No monthly budgets configured yet.\n\n"
            "Use `/setbudget <Category> <Amount>` to establish limits.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    lines = [
        f"📊 *Monthly Budgets ({date.today().strftime('%b %Y')}):*",
        "━━━━━━━━━━━━━━━━━━━━",
    ]

    for b in budgets:
        pct = b["percentage"]
        # Visual progress bar (10 blocks)
        filled = min(10, int(pct // 10))
        bar = "█" * filled + "░" * (10 - filled)
        badge = "🚨" if pct >= 100 else ("⚠️" if pct >= 80 else "✅")

        lines.append(f"{badge} *{esc(b['name'])}*")
        lines.append(f"`[{bar}]` {pct:.1f}%")
        lines.append(f"₹{b['spent']:,.2f} / ₹{b['limit']:,.2f}\n")

    lines.append("━━━━━━━━━━━━━━━━━━━━")
    lines.append("_Tip: Use `/setbudget` to update or `/delbudget` to remove._")

    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def delete_budget_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /delbudget <Category | Overall>."""
    user = update.effective_user
    args = context.args

    if not args:
        await update.message.reply_text(
            "⚠️ Please specify which budget to remove.\n\n"
            "Example: `/delbudget Food` or `/delbudget Overall`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    category_name = " ".join(args).strip()

    with SessionLocal() as session:
        repo = ExpenseRepository(session)
        deleted = repo.delete_budget(user_id=user.id, category_name=category_name)

    if deleted:
        await update.message.reply_text(
            f"🗑️ Removed budget limit for `*{esc(category_name)}*`.",
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        await update.message.reply_text(
            f"⚠️ No active budget found for `*{esc(category_name)}*`.",
            parse_mode=ParseMode.MARKDOWN,
        )