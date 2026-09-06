from decimal import Decimal

from core.loan import Loan
from pricing.fees import (
    processing_fee, penal_charge, penal_rate_annualised, foreclosure_charge, all_charges,
)


def sample_loan(**kw) -> Loan:
    base = dict(
        loan_id="L-1001",
        sanctioned_amount=Decimal("100000"),
        tenure_months=12,
        nominal_rate_pct=Decimal("18"),
    )
    base.update(kw)
    return Loan(**base)


def test_processing_fee_is_two_percent():
    assert processing_fee(sample_loan()) == Decimal("2000.00")


def test_penal_rate_annualises_to_thirty_six():
    assert penal_rate_annualised(sample_loan()) == Decimal("36.00")


def test_penal_charge_compounds_across_months():
    loan = sample_loan()
    one = penal_charge(loan, Decimal("10000"), 1)
    two = penal_charge(loan, Decimal("10000"), 2)
    assert two > one * 2


def test_no_foreclosure_charge_on_floating_rate():
    assert foreclosure_charge(sample_loan(is_floating=True), Decimal("50000")) == Decimal("0.00")


def test_all_charges_lists_every_chargeable_item():
    keys = set(all_charges(sample_loan()))
    assert keys == {"processing_fee", "insurance_premium", "penal_rate_annual_pct", "foreclosure_pct"}
