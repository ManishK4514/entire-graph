"""Monthly regulatory return. REGULATED DISCLOSURE SURFACE."""
from core.loan import Loan
from core.money import to_money
from recovery.dunning import compute_overdue
from pricing.interest import effective_apr


def portfolio_row(loan: Loan, months_overdue: int) -> dict:
    overdue = compute_overdue(loan, months_overdue)
    return {
        "loan_id": loan.loan_id,
        "apr_reported": effective_apr(loan),
        "penal_charges_levied": overdue["penal_charges"],
        "outstanding": overdue["total_due"],
    }


def build_return(loans: list) -> dict:
    rows = [portfolio_row(loan, 0) for loan in loans]
    return {
        "row_count": len(rows),
        "total_outstanding": to_money(sum(r["outstanding"] for r in rows)),
        "rows": rows,
    }
