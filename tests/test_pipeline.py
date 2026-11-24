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
PLANTED_QUESTIONS = {8, 10, 12, 13, 16, 19, 20, 23, 26, 28, 30}


def test_dev_checker_passes_on_planted_values(data):
    results = check_dev_answers.run(data, verbose=False)
    planted = [r for r in results if r["question"] in PLANTED_QUESTIONS]
    assert planted and all(r["pass"] for r in planted), [r for r in planted if not r["pass"]]


def test_checker_excludes_held_out():
    held_out = {1, 3, 5, 7, 9, 11, 14, 15, 17, 18, 22, 24, 27, 29, 31}
    assert not {c.question for c in check_dev_answers.CHECKS} & held_out


def test_checker_covers_every_development_question_that_uses_data():
    data_dev = {8, 10, 12, 13, 16, 19, 20, 21, 23, 26, 28, 30}   # 2, 4, 6, 25 are document-only
    assert {c.question for c in check_dev_answers.CHECKS} == data_dev


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


def test_basket_highlights_the_selection(data, filt):
    comp = cd.basket(data.cpi, data.weights, filt)
    assert len(comp) == 12 and comp["weight"].sum() == pytest.approx(100, abs=0.1)
    assert set(comp.loc[comp["selected"], "code"]) == {"01", "04"}     # 04.5 belongs to division 04


def test_changing_end_month_changes_every_chart(data, filt):
    a = (cd.comparison(data.cpi, filt)["value"].tolist(),
         cd.basket(data.cpi, data.weights, filt)["contribution_pts"].dropna().tolist())
    filt.end = pd.Timestamp("2025-12-01")
    b = (cd.comparison(data.cpi, filt)["value"].tolist(),
         cd.basket(data.cpi, data.weights, filt)["contribution_pts"].dropna().tolist())
    assert a[0] != b[0] and a[1] != b[1]


# ---------------------------------------------------------------- Dataset 3 download check
def test_download_check_accepts_expected_layout(tmp_path):
    from scripts import download_sources
    raw = make_all(tmp_path / "raw")
    assert download_sources.check(raw / config.RAW_FILES["D3"])   # sheets present; hash differs -> warning only


def test_headline_history_reaches_2011(data):
    h = data.cpi[(data.cpi["code"] == "0") & (data.cpi["population"] == config.NATIONAL)]
    assert h[h["source"] == "D3"]["period"].min() == pd.Timestamp("2011-01-01")   # published
    assert "Dataset 3" in A.change(data.cpi, "0", "2017-01", "yoy").sources


# ---------------------------------------------------------------- 2010 derived (proposal Section 1, Q20)
def test_2010_derived_from_12_month_changes(data):
    h = data.cpi[(data.cpi["code"] == "0") & (data.cpi["population"] == config.NATIONAL)].set_index("period")
    derived = h[h["source"] == "D3-derived"]
    assert list(derived.index) == list(pd.date_range("2010-01-01", "2010-12-01", freq="MS"))
    # the fixture's hidden 2010 values were 84.1 ... 85.2; the derivation recovers them
    assert abs(derived.loc["2010-03-01", "index"] - 84.3) < 1e-6
    assert "derived" in A.change(data.cpi, "0", "2010-03", "index").sources
    with pytest.raises(A.DataUnavailable):                      # nothing before 2010 (Q20)
        A.index_value(data.cpi, "0", "2009-12")
    q = data.quality.set_index("check")
    assert q.loc["2010 headline derived from Table 1's 12-month changes", "status"] == "ok"


def test_dataset3_fingerprint_recorded(data):
    q = data.quality.set_index("check")
    assert q.loc[config.D3_FINGERPRINT_CHECK, "status"] == "warning"   # the fixture is not iGA's file


# ---------------------------------------------------------------- data caution (audit bug 1 and 2)
def _f(start, end, codes, pop, measure):
    return A.Filters(pd.Timestamp(start), pd.Timestamp(end), codes, pop, measure)


def test_caution_covers_yoy_computed_from_flagged_month(data):
    # Jan-Jun 2023 year-on-year compares with Jan-Jun 2022; Jan 2022 is the planted discrepancy
    flags = cd.flagged_values(data.discrepancies, _f("2023-01-01", "2023-06-01", ["07"], "Non-Bahraini", "yoy"))
    assert (pd.Timestamp("2022-01-01") in set(flags["period"])) and set(flags["code"]) == {"07"}
    assert "year-on-year" in cd.caution_text(flags)


def test_caution_covers_mom_comparison_month(data):
    flags = cd.flagged_values(data.discrepancies, _f("2022-02-01", "2022-04-01", ["07"], "Non-Bahraini", "mom"))
    assert pd.Timestamp("2022-01-01") in set(flags["period"])


def test_no_caution_when_no_flagged_value_is_used(data):
    assert cd.flagged_values(data.discrepancies, _f("2023-01-01", "2023-06-01", ["07"], "Non-Bahraini", "index")).empty
    assert cd.flagged_values(data.discrepancies, _f("2022-01-01", "2022-06-01", ["07"], "National", "yoy")).empty


def test_caution_for_household_comparison_chart(data):
    f = _f("2021-06-01", "2022-01-01", ["07"], "National", "index")
    assert cd.flagged_values(data.discrepancies, f).empty
    assert not cd.flagged_values(data.discrepancies, f, by_nationality=True).empty


def test_priority_table_caution_uses_end_and_year_before(data):
    assert not cd.priority_flagged(data.discrepancies, _f("2022-06-01", "2023-01-01", ["0"], "National", "yoy")).empty
    assert cd.priority_flagged(data.discrepancies, _f("2023-06-01", "2023-08-01", ["0"], "National", "yoy")).empty


# ---------------------------------------------------------------- model tools (audit integration risks 4, 5)
@pytest.fixture(scope="session")
def tools(data):
    from src.pipeline.tools import Toolbox
    return Toolbox(data)


@pytest.mark.parametrize("args,code", [
    ({"category": "4.5"}, "04.5"), ({"category": "04.5"}, "04.5"), ({"category": "transport"}, "07"),
    ({"category": "Headline"}, "0"), ({"category": "07"}, "07"),
])
def test_tools_resolve_categories(tools, args, code):
    r = tools.call("get_index", {**args, "month": "2026-08"})
    assert r["status"] == "ok" and r["code"] == code


@pytest.mark.parametrize("month", ["2026-08", "2026/8", "08/2026", "Aug 2026", "August 2026", "2026 August", "latest"])
def test_tools_read_months(tools, month):
    assert tools.call("get_index", {"category": "0", "month": month})["period"] == "2026-08"


def test_tools_households_and_refusal_types(tools):
    assert tools.call("get_index", {"category": "11", "month": "2026-08", "household": "non bahraini"})["value"] == 101.6
    assert tools.call("get_index", {"category": "0", "month": "2026-08",
                                    "household": "Muharraq Governorate"})["status"] == "not_available"
    assert tools.call("get_index", {"category": "0", "month": "2009-12"})["status"] == "not_available"
    assert tools.call("get_index", {"category": "0", "month": "last month"})["status"] == "bad_input"
    assert tools.call("get_index", {"category": "0", "date": "2026-08"})["status"] == "bad_input"
    assert tools.call("no_such_tool", {})["status"] == "bad_input"


def test_tools_return_plain_json_with_caution(tools):
    import json
    from src.pipeline.tools import TOOL_DECLARATIONS
    for decl in TOOL_DECLARATIONS:
        assert decl["name"] in tools._tools
    r = tools.call("get_change", {"category": "07", "month": "2023-01", "measure": "yoy", "household": "Non-Bahraini"})
    assert r["status"] == "ok" and "caution" in r
    for name, args in [("rank_categories", {"month": "2026-08", "measure": "yoy"}),
                       ("get_priorities", {"month": "2026-08"}), ("get_contributions", {"month": "2026-08"}),
                       ("compare_households", {"category": "11", "month": "2026-08"}),
                       ("get_series", {"category": "0", "start_month": "2025-01", "end_month": "2025-12"}),
                       ("list_categories", {"level": 1}), ("data_coverage", {})]:
        out = tools.call(name, args)
        assert out["status"] == "ok", (name, out)
        json.dumps(out, allow_nan=False)


def test_series_colours_never_cycle():
    import ast
    src = (config.REPO_ROOT / "src" / "dashboard" / "page.py").read_text()
    tree = ast.parse(src)
    values = {t.id: n.value for n in tree.body if isinstance(n, ast.Assign) for t in n.targets
              if isinstance(t, ast.Name) and t.id in ("SERIES", "MAX_CATEGORIES")}
    assert len(ast.literal_eval(values["SERIES"])) >= ast.literal_eval(values["MAX_CATEGORIES"])


# ---------------------------------------------------------------- empty selections (bug found in fresh test)
def test_comparison_with_nothing_available_is_empty_not_error(data):
    f = A.Filters(pd.Timestamp("2023-09-01"), pd.Timestamp("2026-08-01"), ["01.1"], "Non-Bahraini", "yoy")
    out = cd.comparison(data.cpi, f)
    assert out.empty and "value" in out.columns
    assert cd.trend(data.cpi, f).empty


def test_labels_record_which_households_have_each_code(data):
    nat_only = data.labels.loc[data.labels["code"] == "01.1", "populations"].item()
    assert "Non-Bahraini" not in nat_only
    assert "Non-Bahraini" in data.labels.loc[data.labels["code"] == "01", "populations"].item()


# ---------------------------------------------------------------- every display responds to filters (F2)
def test_priority_table_follows_category_and_household_filters(data):
    full = A.priority_table(data.cpi, data.weights, "2026-08")
    some = A.priority_table(data.cpi, data.weights, "2026-08", codes=["0", "01", "04.5"])
    assert set(some["code"]) == {"01", "04"}
    # ranks are taken across all 12 divisions, so a flag never changes when rows are hidden
    merged = some.merge(full, on="code", suffixes=("", "_all"))
    assert (merged["flag_rising_fastest"] == merged["flag_rising_fastest_all"]).all()
    bh = A.priority_table(data.cpi, data.weights, "2026-08", population="Bahraini")
    assert bh.set_index("code")["yoy"].round(4).to_dict() != full.set_index("code")["yoy"].round(4).to_dict()


def test_summary_covers_every_selected_category(data, filt):
    out = cd.selection_summary(data.cpi, filt)
    assert list(out["code"]) == ["0", "01", "04.5"]
    assert out.loc[out["code"] == "04.5", "yoy"].item() == pytest.approx(
        A.change(data.cpi, "04.5", "2026-08", "yoy").value)


def test_change_over_period_starts_at_first_month_with_data(data):
    f = A.Filters(pd.Timestamp("2011-01-01"), pd.Timestamp("2026-08-01"), ["0", "01"], "Non-Bahraini", "yoy")
    out = cd.selection_summary(data.cpi, f).set_index("code")
    assert out.loc["0", "range_start"] == "2019-05"           # nationality data start, not Jan 2011
    expected = (A.index_value(data.cpi, "0", "2026-08", "Non-Bahraini")
                / A.index_value(data.cpi, "0", "2019-05", "Non-Bahraini") - 1) * 100
    assert out.loc["0", "over_range"] == pytest.approx(expected)


# ---------------------------------------------------------------- Dataset 2 vs iGA Table 3
def test_table3_crosscheck_finds_the_planted_discrepancy(data):
    d = data.discrepancies
    assert len(d) == 1
    row = d.iloc[0]
    assert (row["code"], row["population"], f"{row['period']:%Y-%m}") == ("07", "Non-Bahraini", "2022-01")
    assert row["difference"] == pytest.approx(40.0, abs=0.01)
    q = data.quality.set_index("check")
    assert q.loc["Dataset 2 matches iGA Table 3 (nationality, overlapping months)", "status"] == "warning"


def test_dashboard_flags_only_selections_that_include_the_discrepancy(data):
    hit = A.Filters(pd.Timestamp("2021-06-01"), pd.Timestamp("2022-06-01"), ["0", "07"], "Non-Bahraini", "yoy")
    miss = A.Filters(pd.Timestamp("2023-06-01"), pd.Timestamp("2026-08-01"), ["0", "07"], "Non-Bahraini", "yoy")
    other = A.Filters(pd.Timestamp("2021-06-01"), pd.Timestamp("2022-06-01"), ["0", "07"], "Bahraini", "yoy")
    assert len(cd.flagged_in_selection(data.discrepancies, hit)) == 1
    assert cd.flagged_in_selection(data.discrepancies, miss).empty
    assert cd.flagged_in_selection(data.discrepancies, other).empty


# ---------------------------------------------------------------- fresh server (Streamlit Cloud)
def test_dataset3_is_fetched_from_a_link_and_checked(tmp_path, monkeypatch):
    from scripts import download_sources
    src = make_all(tmp_path / "src") / config.RAW_FILES["D3"]
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "server_raw")
    monkeypatch.setattr(config, "D3_DOWNLOAD_URL", src.resolve().as_uri())
    ok, msg = download_sources.ensure_dataset3(verbose=False)
    assert ok and msg == "downloaded" and (tmp_path / "server_raw" / config.RAW_FILES["D3"]).exists()


def test_failed_download_leaves_no_file_and_does_not_crash(tmp_path, monkeypatch):
    from scripts import download_sources
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "server_raw")
    monkeypatch.setattr(config, "D3_DOWNLOAD_URL", (tmp_path / "missing.xlsx").as_uri())
    ok, msg = download_sources.ensure_dataset3(verbose=False)
    assert not ok and "failed" in msg
    assert not (tmp_path / "server_raw" / config.RAW_FILES["D3"]).exists()
