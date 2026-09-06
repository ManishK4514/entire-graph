"""Nightly KFS batch. Unattended: nobody reads its output before the borrower does.

The renderer is named in job configuration rather than imported, so operations can
repoint the batch without a deploy. The cost is that the edge from this job to the
document it renders does not exist in any static graph.
"""
import importlib

RENDERER_MODULE = "disclosure.kfs"
RENDERER_FUNCTION = "render_kfs_document"


def run_batch(loans: list) -> list:
    module = importlib.import_module(RENDERER_MODULE)
    render = getattr(module, RENDERER_FUNCTION)
    return [render(loan) for loan in loans]
