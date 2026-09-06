"""The Loan aggregate passed between pricing, disclosure and collections."""
from dataclasses import dataclass, field
from decimal import Decimal

from core.money import to_money


@dataclass
class Loan:
    loan_id: str
    sanctioned_amount: Decimal
    tenure_months: int
    nominal_rate_pct: Decimal          # advertised annual rate
    rate_basis: str = "reducing"       # "reducing" | "flat"
    processing_fee_pct: Decimal = Decimal("2")
    insurance_premium: Decimal = Decimal("0")
    penal_rate_monthly_pct: Decimal = Decimal("3")
    is_floating: bool = False
    is_digital: bool = True
    charges: dict = field(default_factory=dict)

    def net_disbursal(self) -> Decimal:
        """What actually reaches the borrower's account."""
        from pricing.fees import processing_fee
        return to_money(
            self.sanctioned_amount - processing_fee(self) - self.insurance_premium
        )
