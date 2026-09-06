"""Interest and the all-inclusive APR."""
from decimal import Decimal

from core.loan import Loan
from core.money import to_money
from pricing.fees import processing_fee


def flat_to_reducing(flat_rate_pct, tenure_months: int) -> Decimal:
    """A 12% flat loan is roughly 21-22% on a reducing basis."""
    n = Decimal(str(tenure_months))
    return to_money(Decimal(str(flat_rate_pct)) * 2 * n / (n + 1))


def effective_rate(loan: Loan) -> Decimal:
    if loan.rate_basis == "flat":
        return flat_to_reducing(loan.nominal_rate_pct, loan.tenure_months)
    return to_money(loan.nominal_rate_pct)


def effective_apr(loan: Loan) -> Decimal:
    """All-inclusive annual cost: interest plus every fee, on the money the
    borrower actually received. RBI requires this in the KFS."""
    principal = loan.net_disbursal()
    fees = processing_fee(loan) + loan.insurance_premium
    years = Decimal(str(loan.tenure_months)) / Decimal("12")
    fee_drag = (fees / principal) / years * Decimal("100")
    return to_money(effective_rate(loan) + fee_drag)
