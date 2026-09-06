"""The verification path for the dynamic route.

Static analysis cannot prove that `late_payment_charge` reaches the KFS. A test can, by
executing the dispatch. This is what "safe fallback or verification path" means
in practice: where the graph goes quiet, run the thing.
"""
from decimal import Decimal

from disclosure.kfs import render_kfs_document

LOAN = {
    "loan_id": "LN-DYN-1",
    "overdue_amount": "1000.00",
    "sanctioned_amount": "50000.00",
    "outstanding": "20000.00",
    "applicable_charges": ["penal", "processing"],
}


def test_penal_charge_reaches_the_key_fact_statement():
    """The edge no static resolver in this project can derive."""
    kfs = render_kfs_document(LOAN)
    assert kfs["charges"]["penal"] == Decimal("20.00")


def test_kfs_renders_every_applicable_charge():
    kfs = render_kfs_document(LOAN)
    assert set(kfs["charges"]) == {"penal", "processing"}
