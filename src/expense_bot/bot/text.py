from telegram.helpers import escape_markdown


def esc(value) -> str:
    """Make any text safe to show with ParseMode.MARKDOWN."""
    return escape_markdown(str(value))