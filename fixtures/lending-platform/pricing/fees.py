"""Fee computation. CHANGE TARGET: the penal charge rules live here."""
from decimal import Decimal

from core.loan import Loan
from core.money import to_money, pct, annualise_monthly


def processing_fee(loan: Loan) -> Decimal:
    return pct(loan.sanctioned_amount, loan.processing_fee_pct)


def penal_charge(loan: Loan, overdue_principal, months_overdue: int) -> Decimal:
    """Penal charge on an overdue instalment.

    NOTE: this compounds month on month. RBI's 2024 circular requires penal
    *charges* to be reasonable and bars penal *interest* that compounds.
    """
    charge = Decimal("0")
    base = Decimal(str(overdue_principal))
    for _ in range(months_overdue):
        month_charge = pct(base, loan.penal_rate_monthly_pct)
        charge += month_charge
        base += month_charge          # <-- compounding
    return to_money(charge)


def penal_rate_annualised(loan: Loan) -> Decimal:
    """The number a borrower actually needs to see: 3%/month -> 36%/year."""
    return annualise_monthly(loan.penal_rate_monthly_pct)


def foreclosure_charge(loan: Loan, outstanding) -> Decimal:
    """RBI bars prepayment penalties on floating-rate loans to individuals."""
    if loan.is_floating:
        return to_money(0)
    return pct(outstanding, 4)


def all_charges(loan: Loan) -> dict:
    """Every chargeable item. The KFS must disclose all of these."""
    return {
        "processing_fee": processing_fee(loan),
        "insurance_premium": to_money(loan.insurance_premium),
        "penal_rate_annual_pct": penal_rate_annualised(loan),
        "foreclosure_pct": Decimal("0") if loan.is_floating else Decimal("4"),
    }
