from decimal import Decimal

from disclosure.kfs import generate_kfs, render_kfs_text, cooling_off_days, penal_illustration
from disclosure.sanction_letter import charges_match_kfs
from tests.test_fees import sample_loan


def test_kfs_discloses_all_inclusive_apr():
    kfs = generate_kfs(sample_loan())
    assert kfs["apr"] > Decimal("18")


def test_kfs_carries_amortisation_schedule():
    assert len(generate_kfs(sample_loan())["amortisation"]) == 12


def test_kfs_states_penal_rate_annually():
    assert generate_kfs(sample_loan())["penal_rate_annual_pct"] == Decimal("36.00")


def test_digital_loans_get_cooling_off_window():
    assert cooling_off_days(sample_loan()) == 3


def test_sanction_letter_charges_match_kfs():
    assert charges_match_kfs(sample_loan())


def test_kfs_text_names_the_amount_the_borrower_receives():
    assert "Amount you receive" in render_kfs_text(sample_loan())


def test_kfs_discloses_a_penal_charge_illustration():
    illustration = generate_kfs(sample_loan())["penal_illustration"]
    assert illustration["months_missed"] == 3
    assert illustration["amount_due"] > 0
