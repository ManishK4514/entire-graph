"""Collections. Consumes penal charges to compute what an overdue borrower owes."""
from core.loan import Loan
from core.money import to_money
from pricing.fees import penal_charge
from pricing.schedule import emi


def compute_overdue(loan: Loan, months_overdue: int) -> dict:
    instalment = emi(loan)
    penalty = penal_charge(loan, instalment, months_overdue)
    return {
        "loan_id": loan.loan_id,
        "instalments_due": to_money(instalment * months_overdue),
        "penal_charges": penalty,
        "total_due": to_money(instalment * months_overdue + penalty),
    }


def _format_sms_text(name: str, amount) -> str:
    """Private helper. Used only by build_reminder and its test."""
    return f"Hi {name}, an amount of Rs {amount} is overdue on your loan."


def build_reminder(loan: Loan, borrower_name: str, months_overdue: int) -> str:
    due = compute_overdue(loan, months_overdue)
    return _format_sms_text(borrower_name, due["total_due"])
