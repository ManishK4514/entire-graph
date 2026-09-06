"""Key Fact Statement rendering.

Which charge rows appear on a KFS is a property of the PRODUCT, not of the code:
a personal loan discloses different rows from a two-wheeler loan. So the rows are
data-driven, and the callee is chosen from `CHARGE_RULES` at runtime.

This is an ordinary, defensible design. It is also the reason no static analysis
can tell you that `pricing.fees.late_payment_charge` feeds a regulated disclosure.
"""
from pricing import fees

CHARGE_RULES = {
    "penal": fees.late_payment_charge,
    "processing": fees.origination_fee,
    "foreclosure": fees.prepayment_charge,
}

COOLING_OFF_DAYS = 3


def render_kfs_document(loan: dict) -> dict:
    """The document the borrower is legally entitled to receive."""
    rows = {}
    for code in loan["applicable_charges"]:
        rows[code] = CHARGE_RULES[code](loan)
    return {
        "loan_id": loan["loan_id"],
        "charges": rows,
        "cooling_off_days": COOLING_OFF_DAYS,
    }
