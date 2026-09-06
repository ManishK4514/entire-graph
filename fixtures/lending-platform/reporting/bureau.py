"""Credit bureau reporting. A default here damages a borrower's score for years."""
from core.loan import Loan
from recovery.dunning import compute_overdue


def bureau_record(loan: Loan, months_overdue: int) -> dict:
    overdue = compute_overdue(loan, months_overdue)
    return {
        "loan_id": loan.loan_id,
        "dpd": months_overdue * 30,
        "amount_overdue": overdue["total_due"],
        "status": "DEFAULT" if months_overdue >= 3 else "CURRENT",
    }
