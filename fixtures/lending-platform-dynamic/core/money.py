"""Money helpers. Same contract as the main fixture: paise-accurate, half-up."""
from decimal import Decimal, ROUND_HALF_UP


def round_to_paise(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def monthly_rate_to_annual(monthly_rate_pct: Decimal) -> Decimal:
    """Turn "3% per month" into the annual figure the borrower must be shown."""
    return round_to_paise(monthly_rate_pct * 12)
