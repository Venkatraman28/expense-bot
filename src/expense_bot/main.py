import logging
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from expense_bot.bot.filters import allowed_user_filter
from expense_bot.bot.handlers import (
    categories_handler,
    expense_callback_handler,
    on_error,
    start_handler,
    text_message_handler,
    voice_message_handler,
    photo_message_handler,
    add_category_handler,
    delete_category_handler,
    budgets_handler,
    delete_budget_handler,
    set_budget_handler,
)
from expense_bot.config import settings
from expense_bot.database import engine, init_db

from telegram.request import HTTPXRequest
from telegram.ext import ApplicationBuilder

# Configure generous connection and read timeouts for Telegram API calls
request_config = HTTPXRequest(
    connect_timeout=20.0,
    read_timeout=60.0,
    write_timeout=20.0,
    pool_timeout=10.0,
)

# Configure clean logging for bot activity and inference tracking
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
# httpx logs full request URLs at INFO, and Telegram's URL contains the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Initializing database tables and default categories...")
    init_db(engine, settings.ALLOWED_CHAT_IDS)

    logger.info("Building Telegram application...")
    app = ApplicationBuilder().token(settings.TELEGRAM_BOT_TOKEN).request(request_config).build()

    # Commands (restricted by allowed_user_filter)
    app.add_handler(CommandHandler("start", start_handler, filters=allowed_user_filter))
    app.add_handler(CommandHandler("categories", categories_handler, filters=allowed_user_filter))
    app.add_handler(CommandHandler("addcategory", add_category_handler, filters=allowed_user_filter))
    app.add_handler(CommandHandler("delcategory", delete_category_handler, filters=allowed_user_filter))
    app.add_handler(CommandHandler("budgets", budgets_handler, filters=allowed_user_filter))
    app.add_handler(CommandHandler("setbudget", set_budget_handler, filters=allowed_user_filter))
    app.add_handler(CommandHandler("delbudget", delete_budget_handler, filters=allowed_user_filter))

    # Natural language ingestion: intercepts plain text messages that are not commands
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND & allowed_user_filter,
            text_message_handler,
        )
    )

    # Inline button callback queries (matches save:<id> and discard:<id>)
    app.add_handler(
        CallbackQueryHandler(
            expense_callback_handler,
            pattern=r"^(save|discard|del_confirm|del_cancel):",
        )
    )

    # Audio handler
    app.add_handler(
        MessageHandler(
            (filters.VOICE | filters.AUDIO) & allowed_user_filter,
            voice_message_handler,
        )
    )

    # Vision handler
    app.add_handler(
        MessageHandler(
            filters.PHOTO & allowed_user_filter,
            photo_message_handler,
        )
    )

    app.add_error_handler(on_error)

    logger.info("Starting Telegram polling...")
    app.run_polling()


if __name__ == "__main__":
    main()