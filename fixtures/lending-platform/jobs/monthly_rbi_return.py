"""Scheduled job: file the monthly regulatory return."""
from reporting.rbi_return import build_return

JOB_NAME = "monthly_rbi_return"
SCHEDULE = "0 3 1 * *"


def run(loans: list) -> dict:
    return build_return(loans)
