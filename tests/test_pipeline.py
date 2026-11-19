"""Tests for the data pipeline (F1) and analytics. Run: python -m pytest -q"""
from __future__ import annotations

import math

import pandas as pd
import pytest

from scripts import check_dev_answers
from src.pipeline import analytics as A
from src.pipeline import config, labels, load
from src.pipeline.run import build, load_prepared, write_outputs
from tests.fixtures import make_all


@pytest.fixture(scope="session")
def data(tmp_path_factory):
    raw = make_all(tmp_path_factory.mktemp("raw"))
    return build(raw)


# ---------------------------------------------------------------- labels
@pytest.mark.parametrize("raw,expected", [
    ("1.1", "01.1"), ("01.1", "01.1"), ("4", "04"), ("1.1.2", "01.1.2"),
    ("10", "10"), ("12.1", "12.1"), ("0", "0"), ("00", "0"), (" 7 ", "07"), ("", None),
])
def test_code_normalisation(raw, expected):
    assert labels.normalise_code(raw) == expected


def test_headline_labels_recognised():
    for label in ["Consumers Price Index - CPI", "Consumer Price Indexs", "CPI"]:
        assert labels.resolve_code(None, label) == "0"


def test_header_line_breaks_removed():
    assert load.normalise_header("COICOP \nDivision & Group") == "coicop division & group"


@pytest.mark.parametrize("raw,expected", [("01 January", 1), ("09 September", 9), ("May", 5),
                                          ("8", 8), ("02 March", None)])
def test_month_labels(raw, expected):
    assert load.parse_month(raw) == expected


# ---------------------------------------------------------------- F1 preparation
def test_one_series_per_code_after_repadding(data):
    nat = data.cpi[(data.cpi["population"] == "National") & (data.cpi["source"] == "D1")]
    assert not any(c in set(nat["code"]) for c in ["1", "1.1", "4.5"])
    # every code has every month: re-padding joined pre/post June 2023 rows
    assert nat.groupby("code")["period"].nunique().eq(116).all()   # Jan 2017 - Aug 2026


def test_headline_single_code_and_name(data):
    head = data.cpi[data.cpi["code"] == "0"]
    assert head["name"].nunique() == 1
    assert set(head["population"]) == {"National", "Bahraini", "Non-Bahraini"}


def test_misspelling_not_used_as_name(data):
    assert data.cpi.loc[data.cpi["code"] == "06", "name"].unique().tolist() == ["Health"]


def test_missing_value_kept_missing_and_logged(data):
    v = data.cpi[(data.cpi["code"] == "08") & (data.cpi["period"] == "2024-05-01")
                 & (data.cpi["population"] == "National")]["index"]
    assert len(v) == 1 and math.isnan(v.iloc[0])
    q = data.quality
    assert (q["check"].str.contains("Missing") & (q["source"] == "D1")).any()
    with pytest.raises(A.DataUnavailable):
        A.index_value(data.cpi, "08", "2024-05")


def test_cutoff_to_august_2026(data):
    assert data.cpi["period"].max() == pd.Timestamp("2026-08-01")
    q = data.quality
    assert q["check"].str.contains("cut-off").sum() == 2


def test_zero_placeholder_becomes_missing(data):
    with pytest.raises(A.DataUnavailable):
        A.index_value(data.cpi, "04.2", "2018-06")
    assert A.index_value(data.cpi, "04.2", "2019-05") > 0


def test_table_201_crosscheck_and_table1_2020_explained(data):
    q = data.quality.set_index("check")
    assert q.loc["Dataset 1 values match iGA Table 2.01 (all codes, overlapping months)", "status"] == "ok"
    row = q.loc["Table 1 headline matches Dataset 1 where both exist"]
    assert row["status"] == "info" and "2020" in row["detail"]


def test_stored_precision_kept(data):
    assert A.index_value(data.cpi, "04.5", "2025-08") == pytest.approx(76.02)


def test_weights_loaded_in_percent(data):
    w = data.weights[data.weights["level"] == 1]
    assert len(w) == 12 and w["weight"].sum() == pytest.approx(100, abs=0.1)


def test_history_only_2011_2016(data):
    hist = data.cpi[data.cpi["source"] == "D3"]
    assert hist["period"].min() == pd.Timestamp("2011-01-01")
    assert hist["period"].max() == pd.Timestamp("2016-12-01")


def test_round_trip_processed_files(data, tmp_path):
    write_outputs(data, tmp_path)
    again = load_prepared(tmp_path)
    assert len(again.cpi) == len(data.cpi)
    assert again.cpi["code"].str.match(r"^(0|\d{2}(\.\d+)*)$").all()


# ---------------------------------------------------------------- analytics
def test_three_readings_differ_and_are_labelled(data):
    figs = {m: A.change(data.cpi, "04.5", "2026-08", m) for m in ("mom", "yoy", "base")}
    assert figs["mom"].compared_with == "2026-07"
    assert figs["yoy"].compared_with == "2025-08"
    assert figs["base"].compared_with == "2019-04"
    assert len({round(f.value, 1) for f in figs.values()}) == 3


def test_nationality_comparison_declines_before_may_2019(data):
    t = A.compare_populations(data.cpi, "01", "2019-03", "index")
    assert t.loc[t["population"] == "Bahraini", "display"].iloc[0] == "not available"


def test_annual_average_refuses_incomplete_year(data):
    with pytest.raises(A.DataUnavailable):
        A.annual_average(data.cpi, "0", 2026)   # data end in August


def test_forecast_months_unavailable(data):
    with pytest.raises(A.DataUnavailable):
        A.index_value(data.cpi, "0", "2026-12")


def test_filters_drive_every_display(data):
    f = A.Filters(pd.Timestamp("2024-01-01"), pd.Timestamp("2025-06-01"), ["01", "07"], "Bahraini")
    sel = A.apply_filters(data.cpi, f)
    assert set(sel["code"]) == {"01", "07"} and set(sel["population"]) == {"Bahraini"}
    assert sel["period"].min() == f.start and sel["period"].max() == f.end


def test_priority_table_has_all_divisions(data):
    t = A.priority_table(data.cpi, data.weights, "2026-08")
    assert len(t) == 12 and t["criteria_met"].between(0, 4).all()
    assert t.loc[t["code"] == "04", "flag_large_weight"].item()


def test_contributions_cover_divisions(data):
    c = A.contributions(data.cpi, data.weights, "2026-08")
    assert len(c) == 12 and "headline_yoy" in c.attrs


# ---------------------------------------------------------------- answer checker
PLANTED_QUESTIONS = {8, 10, 12, 13, 23, 26, 28, 30}


def test_dev_checker_passes_on_planted_values(data):
    results = check_dev_answers.run(data, verbose=False)
    planted = [r for r in results if r["question"] in PLANTED_QUESTIONS]
    assert planted and all(r["pass"] for r in planted), [r for r in planted if not r["pass"]]


def test_checker_excludes_held_out():
    held_out = {1, 3, 5, 9, 11, 14, 15, 17, 18, 22, 24, 27, 29, 31}
    assert not {c.question for c in check_dev_answers.CHECKS} & held_out


# ---------------------------------------------------------------- dashboard data (F2/F3)
from src.dashboard import chart_data as cd  # noqa: E402


@pytest.fixture
def filt():
    return A.Filters(pd.Timestamp("2024-09-01"), pd.Timestamp("2026-08-01"), ["0", "01", "04.5"], "National", "yoy")


def test_trend_respects_time_and_categories(data, filt):
    t = cd.trend(data.cpi, filt)
    assert set(t["code"]) == {"0", "01", "04.5"}
    assert t["period"].min() == filt.start and t["period"].max() == filt.end


def test_groups_dropped_for_nationality(data, filt):
    filt.population = "Bahraini"
    keep, dropped = cd.usable_codes(data.cpi, filt)
    assert keep == ["0", "01"] and dropped == ["04.5"]
    assert set(cd.trend(data.cpi, filt)["code"]) == {"0", "01"}


def test_comparison_uses_end_month(data, filt):
    c = cd.comparison(data.cpi, filt)
    expected = A.change(data.cpi, "04.5", "2026-08", "yoy").value
    assert c.loc[c["code"] == "04.5", "value"].item() == pytest.approx(expected)
    by_nat = cd.comparison(data.cpi, filt, by_nationality=True)
    assert set(by_nat["group"]) == {"National", "Bahraini", "Non-Bahraini"}


def test_composition_responds_to_selection(data, filt):
    comp = cd.composition(data.cpi, data.weights, filt)
    assert set(comp["code"]) == {"01", "04", "rest"}          # 04.5 belongs to division 04
    assert comp["weight"].sum() == pytest.approx(100, abs=0.1)


def test_changing_end_month_changes_every_chart(data, filt):
    a = (cd.comparison(data.cpi, filt)["value"].tolist(),
         cd.composition(data.cpi, data.weights, filt)["contribution_pts"].dropna().tolist())
    filt.end = pd.Timestamp("2025-12-01")
    b = (cd.comparison(data.cpi, filt)["value"].tolist(),
         cd.composition(data.cpi, data.weights, filt)["contribution_pts"].dropna().tolist())
    assert a[0] != b[0] and a[1] != b[1]
