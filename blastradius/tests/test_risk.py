"""The risk model is the trust claim. It gets the most tests."""
from types import SimpleNamespace

from blastradius.core.risk import score_change, band_for


def surface(sid, severity="critical"):
    return SimpleNamespace(id=sid, severity=severity)


def job(name):
    return SimpleNamespace(name=name, schedule="0 2 * * *")


def base(**kw):
    args = dict(
        critical_surfaces=[], high_surfaces=[], scheduled_jobs=[],
        hop1_symbols=[], deeper_symbols=[],
        changed_symbols_without_tests=[], all_surfaces_have_tests=False,
    )
    args.update(kw)
    return score_change(**args)


def test_a_change_that_touches_nothing_is_low():
    result = base()
    assert result.score == 0 and result.band == "LOW"


def test_reaching_a_critical_regulated_surface_dominates_the_score():
    result = base(critical_surfaces=[surface("kfs-generator")])
    assert result.score == 40 and result.band == "MEDIUM"


def test_scoring_is_deterministic():
    args = dict(critical_surfaces=[surface("kfs")], scheduled_jobs=[job("daily")],
                hop1_symbols=["a", "b"], deeper_symbols=["c"])
    assert [base(**args).score for _ in range(20)].count(base(**args).score) == 20


def test_every_term_is_explained():
    result = base(critical_surfaces=[surface("kfs")], scheduled_jobs=[job("daily")])
    assert all(t.because for t in result.terms)
    assert sum(t.contribution for t in result.terms) == result.score


def test_test_coverage_reduces_the_score():
    args = dict(critical_surfaces=[surface("kfs")], hop1_symbols=["a"])
    assert base(**args, all_surfaces_have_tests=True).score < base(**args).score


def test_untested_change_is_penalised():
    assert base(changed_symbols_without_tests=["pricing.fees.x"]).score == 15


def test_score_is_clamped_to_a_hundred():
    result = base(
        critical_surfaces=[surface(f"s{i}") for i in range(5)],
        scheduled_jobs=[job(f"j{i}") for i in range(20)],
    )
    assert result.score == 100


def test_bands_have_no_gaps():
    assert [band_for(s) for s in (0, 19, 20, 49, 50, 74, 75, 100)] == [
        "LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH", "CRITICAL", "CRITICAL"
    ]
