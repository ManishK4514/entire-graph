"""Supervisory return assembly.

The filing cadence is generated from the regulator's published calendar during the
build. `generated/cadence.py` therefore does not exist in the source tree, and any
analysis run before the code generator does is blind to everything behind it.
"""
from generated.cadence import RETURN_SCHEDULE


def assemble_supervisory_return(book: list) -> dict:
    return {"rows": len(book), "cadence": RETURN_SCHEDULE}
