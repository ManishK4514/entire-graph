"""EMI and amortisation schedule."""
from decimal import Decimal

from core.loan import Loan
from core.money import to_money
from pricing.fees import penal_charge
from pricing.interest import effective_rate


def emi(loan: Loan) -> Decimal:
    r = effective_rate(loan) / Decimal("1200")
    n = loan.tenure_months
    p = loan.sanctioned_amount
    if r == 0:
        return to_money(p / n)
    factor = (1 + r) ** n
    return to_money(p * r * factor / (factor - 1))


def build_schedule(loan: Loan) -> list:
    """Amortisation rows. The KFS must carry this schedule."""
    instalment = emi(loan)
    balance = loan.sanctioned_amount
    r = effective_rate(loan) / Decimal("1200")
    rows = []
    for month in range(1, loan.tenure_months + 1):
        interest = to_money(balance * r)
        principal = to_money(instalment - interest)
        balance = to_money(balance - principal)
        rows.append({
            "month": month,
            "emi": instalment,
            "principal": principal,
            "interest": interest,
            "balance": max(balance, Decimal("0")),
        })
    return rows


def overdue_projection(loan: Loan, months_overdue: int) -> Decimal:
    """What a borrower owes if they miss instalments. Uses penal_charge."""
    instalment = emi(loan)
    return to_money(
        instalment * months_overdue + penal_charge(loan, instalment, months_overdue)
    )
