import calendar
from datetime import date


def get_month_date_range(year: int, month: int) -> tuple[date, date]:
    """Returns (start_date, end_date) for a given year and month."""
    _, last_day = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    return start_date, end_date