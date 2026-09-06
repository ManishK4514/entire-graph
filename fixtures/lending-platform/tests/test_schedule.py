from decimal import Decimal

from pricing.schedule import emi, build_schedule, overdue_projection
from tests.test_fees import sample_loan


def test_schedule_has_one_row_per_month():
    assert len(build_schedule(sample_loan())) == 12


def test_schedule_amortises_to_zero():
    assert build_schedule(sample_loan())[-1]["balance"] < Decimal("1")


def test_overdue_projection_exceeds_plain_instalments():
    loan = sample_loan()
    assert overdue_projection(loan, 3) > emi(loan) * 3
