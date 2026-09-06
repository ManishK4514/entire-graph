"""Money primitives. Every rupee amount in the platform passes through here."""
from decimal import Decimal, ROUND_HALF_UP

PAISE = Decimal("0.01")


def to_money(value) -> Decimal:
    """Coerce to a 2-decimal rupee amount."""
    return Decimal(str(value)).quantize(PAISE, rounding=ROUND_HALF_UP)


def pct(amount, rate_pct) -> Decimal:
    """rate_pct is a percentage, e.g. 3 for 3%."""
    return to_money(Decimal(str(amount)) * Decimal(str(rate_pct)) / Decimal("100"))


def annualise_monthly(monthly_rate_pct) -> Decimal:
    """Simple annualisation of a monthly rate. 3%/month -> 36%/year."""
    return to_money(Decimal(str(monthly_rate_pct)) * 12)
