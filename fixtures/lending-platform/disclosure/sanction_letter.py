"""Sanction letter. REGULATED DISCLOSURE SURFACE — its charges must match the KFS."""
from core.loan import Loan
from disclosure.kfs import generate_kfs


def generate_sanction_letter(loan: Loan) -> dict:
    kfs = generate_kfs(loan)
    return {
        "loan_id": loan.loan_id,
        "amount": kfs["sanctioned_amount"],
        "apr": kfs["apr"],
        "charges": kfs["charges"],
        "accepted_by_borrower": False,
    }


def charges_match_kfs(loan: Loan) -> bool:
    """Nothing may be charged that the KFS did not disclose."""
    letter = generate_sanction_letter(loan)
    kfs = generate_kfs(loan)
    return letter["charges"] == kfs["charges"]
