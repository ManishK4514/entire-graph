"""Fee computation.

Nothing in this repository calls `late_payment_charge` through a name. It is reached
only through the charge registry in `disclosure/kfs.py`, which is why a static
reverse-dependency walk reports it as having no dependents at all.
"""
from decimal import Decimal

from core.money import round_to_paise


def late_payment_charge(loan: dict) -> Decimal:
    """Penal charge on the overdue instalment.

    RBI, August 2023: this is a CHARGE, not penal interest, and it may not be
    capitalised or compounded.
    """
    return round_to_paise(Decimal(loan["overdue_amount"]) * Decimal("0.02"))


def origination_fee(loan: dict) -> Decimal:
    return round_to_paise(Decimal(loan["sanctioned_amount"]) * Decimal("0.01"))


def prepayment_charge(loan: dict) -> Decimal:
    return round_to_paise(Decimal(loan["outstanding"]) * Decimal("0.04"))
