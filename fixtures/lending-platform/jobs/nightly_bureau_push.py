"""Scheduled job: push DPD records to the credit bureau."""
from reporting.bureau import bureau_record

JOB_NAME = "nightly_bureau_push"
SCHEDULE = "30 1 * * *"


def run(loans: list) -> list:
    return [bureau_record(loan, 0) for loan in loans]
