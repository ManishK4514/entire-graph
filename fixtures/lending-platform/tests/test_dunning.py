from recovery.dunning import compute_overdue, build_reminder, _format_sms_text
from tests.test_fees import sample_loan


def test_overdue_total_includes_penal_charges():
    due = compute_overdue(sample_loan(), 2)
    assert due["total_due"] == due["instalments_due"] + due["penal_charges"]


def test_reminder_mentions_the_borrower():
    assert "Asha" in build_reminder(sample_loan(), "Asha", 1)


def test_sms_text_formats_amount():
    assert "Rs 500" in _format_sms_text("Asha", 500)
