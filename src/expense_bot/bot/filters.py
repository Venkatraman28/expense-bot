from telegram import Update
from telegram.ext.filters import UpdateFilter

from expense_bot.config import settings


class AllowedUserFilter(UpdateFilter):
    def filter(self, update: Update) -> bool:
        user = update.effective_user
        if not user:
            return False
        return user.id in settings.ALLOWED_CHAT_IDS


allowed_user_filter = AllowedUserFilter()