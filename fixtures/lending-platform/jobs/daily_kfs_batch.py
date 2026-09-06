"""Scheduled job: regenerate KFS documents for the day's sanctioned loans."""
from disclosure.kfs import render_kfs_text
from disclosure.sanction_letter import generate_sanction_letter

JOB_NAME = "daily_kfs_batch"
SCHEDULE = "0 2 * * *"


def run(loans: list) -> list:
    return [
        {"kfs": render_kfs_text(loan), "letter": generate_sanction_letter(loan)}
        for loan in loans
    ]
