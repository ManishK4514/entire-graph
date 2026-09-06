"""Key Fact Statement generator.

REGULATED DISCLOSURE SURFACE. RBI has mandated the KFS for retail and MSME
loans since October 2024. It must carry the all-inclusive APR, every fee, the
amortisation schedule, penal charge details, the grievance contact and the
cooling-off period. Anything not disclosed here cannot be charged.
"""
from core.loan import Loan
from pricing.fees import all_charges, penal_rate_annualised
from pricing.interest import effective_apr
from pricing.schedule import build_schedule, emi, overdue_projection


GRIEVANCE_OFFICER = {"name": "Grievance Redressal Officer", "email": "gro@example-nbfc.test"}


def cooling_off_days(loan: Loan) -> int:
    """Digital loans carry an exit window: repay principal plus proportionate
    charges and walk away without penalty."""
    return 3 if loan.is_digital else 0


def penal_illustration(loan: Loan) -> dict:
    """RBI requires penal charge details in the KFS. We disclose a worked
    example: what the borrower owes after missing three instalments."""
    return {
        "months_missed": 3,
        "amount_due": overdue_projection(loan, 3),
        "annual_penal_rate_pct": penal_rate_annualised(loan),
    }


def generate_kfs(loan: Loan) -> dict:
    return {
        "loan_id": loan.loan_id,
        "sanctioned_amount": loan.sanctioned_amount,
        "net_disbursal": loan.net_disbursal(),
        "tenure_months": loan.tenure_months,
        "apr": effective_apr(loan),
        "emi": emi(loan),
        "charges": all_charges(loan),
        "penal_rate_annual_pct": penal_rate_annualised(loan),
        "amortisation": build_schedule(loan),
        "penal_illustration": penal_illustration(loan),
        "cooling_off_days": cooling_off_days(loan),
        "grievance": GRIEVANCE_OFFICER,
    }


def render_kfs_text(loan: Loan) -> str:
    kfs = generate_kfs(loan)
    return (
        f"KEY FACT STATEMENT — {kfs['loan_id']}\n"
        f"Amount sanctioned: {kfs['sanctioned_amount']}\n"
        f"Amount you receive: {kfs['net_disbursal']}\n"
        f"Annual Percentage Rate (all-inclusive): {kfs['apr']}%\n"
        f"Monthly instalment: {kfs['emi']}\n"
        f"Penal charges: {kfs['penal_rate_annual_pct']}% per year\n"
        f"If you miss 3 instalments you will owe: {kfs['penal_illustration']['amount_due']}\n"
        f"Cooling-off window: {kfs['cooling_off_days']} days\n"
    )
