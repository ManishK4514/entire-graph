from decimal import Decimal

from pricing.interest import flat_to_reducing, effective_apr, effective_rate
from tests.test_fees import sample_loan


def test_twelve_percent_flat_is_about_twentytwo_reducing():
    assert Decimal("21") < flat_to_reducing(Decimal("12"), 12) < Decimal("23")


def test_effective_rate_passes_through_for_reducing_loans():
    assert effective_rate(sample_loan()) == Decimal("18.00")


def test_apr_exceeds_nominal_rate_because_of_fees():
    loan = sample_loan()
    assert effective_apr(loan) > loan.nominal_rate_pct
