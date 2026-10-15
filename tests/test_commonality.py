# tests/test_commonality.py
# 장비 공통성 분석(wm811k_commonality.py)의 코딩 오류를 잡는다. 전부 합성·가상 ID 다.
# 심은 장비가 1위로 뜨고 심지 않은 단계가 조용한지의 로직 확인이지 성능이 아니다.

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import wm811k_commonality as cm  # noqa: E402
from synthetic_wm811k import make_lswmd  # noqa: E402

PLANTED = {"ETCH_M1": "ETCH-02"}


@pytest.fixture(scope="module")
def planted():
    lots = [f"L{i:04d}" for i in range(200)]
    hist = cm.synthetic_history(lots, seed=0, planted=PLANTED)
    preds = cm.synthetic_predictions(hist, "EDGE_LOC", PLANTED, seed=0)
    status = cm.lot_pattern_status(preds, "EDGE_LOC")
    return dict(hist=hist, preds=preds, status=status, table=cm.commonality_table(hist, status))


# ──────────────────────────────────────────
# 스키마
# ──────────────────────────────────────────
def test_schema_missing_required_raises(tmp_path):
    with pytest.raises(ValueError, match="필수 열"):
        cm.validate_history(pd.DataFrame({"lot": ["a"], "step": ["S"]}))
    p = tmp_path / "h.csv"
    pd.DataFrame({"lot": ["a"], "tool": ["T"]}).to_csv(p, index=False)
    with pytest.raises(ValueError, match="step"):
        cm.load_lot_history(p)


def test_schema_optional_columns_and_warnings(tmp_path, capsys):
    df = pd.DataFrame({"lot": ["a", "a", "b", None], "step": ["S1", "S1", "S1", "S1"],
                       "tool": ["T1", "T1", "T2", "T1"], "start_time": ["2026-01-01", "bad", "2026-01-03", "x"]})
    h = cm.validate_history(df)
    out = capsys.readouterr().out
    assert "chamber" in h.columns and (h["chamber"] == "").all()
    assert len(h) == 3 and "결측 행 1개" in out and "재작업" in out
    assert str(h["start_time"].dtype).startswith("datetime") and int(h["start_time"].isna().sum()) == 1
    p = tmp_path / "ok.lot_history.csv"
    df.to_csv(p, index=False)
    assert len(cm.load_lot_history(p, verbose=False)) == 3


# ──────────────────────────────────────────
# 로트 양성 정의
# ──────────────────────────────────────────
def test_lot_pattern_status_min_frac_and_min_n():
    preds = pd.DataFrame({"lot": ["a"] * 4 + ["b"] * 2 + ["c"] * 1 + ["d"] * 3,
                          "y_pred": ["EDGE_LOC", "EDGE_LOC", "LOC", "LOC",      # a: 0.5
                                     "LOC", "LOC",                              # b: 0.0
                                     "EDGE_LOC",                                # c: 1.0 (1장)
                                     "EDGE_LOC", "LOC", "LOC"]})                # d: 0.33
    s = cm.lot_pattern_status(preds, "EDGE_LOC", min_frac=0.3, min_n=1)
    assert s.to_dict() == {"a": True, "b": False, "c": True, "d": True} and s.attrs["n_dropped"] == 0
    s = cm.lot_pattern_status(preds, "EDGE_LOC", min_frac=0.4, min_n=2)
    assert s.to_dict() == {"a": True, "b": False, "d": False} and s.attrs["n_dropped"] == 1   # c 는 1장이라 제외
    assert s.attrs["table"].loc["d", "frac"] == pytest.approx(1 / 3)
    with pytest.raises(ValueError, match="y_pred"):
        cm.lot_pattern_status(preds.drop(columns="y_pred"), "EDGE_LOC")


# ──────────────────────────────────────────
# 공통성 표
# ──────────────────────────────────────────
def test_planted_tool_ranks_first_and_other_steps_quiet(planted):
    t = planted["table"]
    assert list(t.columns[:3]) == ["step", "tool", "chamber"]
    top = t.iloc[0]
    assert (top["step"], top["tool"]) == ("ETCH_M1", "ETCH-02") and top["q_bh"] < 0.05 and top["note"] == "top candidate"
    assert top["rate_ratio"] > 2 and top["ci_lo"] > 1
    # ETCH-02 의 두 챔버 모두 유의, 같은 단계의 다른 장비는 유의하지 않음
    etch = t[t["step"] == "ETCH_M1"]
    assert (etch.loc[etch["tool"] == "ETCH-02", "q_bh"] < 0.05).all()
    assert (etch.loc[etch["tool"] != "ETCH-02", "q_bh"] > 0.05).all()
    # 심지 않은 단계는 전부 q > 0.05
    other = t[t["step"] != "ETCH_M1"]
    assert len(other) and (other["q_bh"] > 0.05).all()
    assert not other["note"].str.startswith("routing").any()
    # 2x2 합: 단위 + 나머지 = 단계 전체 로트
    assert (t["n_lots"] + t["n_other"] == 200).all() and (t["n_bad"] + t["bad_other"] == t.attrs["n_bad_total"]).all()
    assert ((t["p_fisher"] >= 0) & (t["p_fisher"] <= 1) & (t["q_bh"] >= t["p_fisher"] - 1e-12)).all()


def test_overlap_with_top_and_routing_confound_flag():
    """손으로 만든 이력: S2 의 X 를 지난 로트는 전부 S1 의 T1 도 지난다 -> overlap 1.0, 혼입 경고."""
    lots = [f"l{i}" for i in range(16)]
    rows = []
    for i, L in enumerate(lots):
        t1 = "T1" if i < 8 else "T2"            # S1: 앞 8 로트는 T1
        x = "X" if i < 8 else "Y"               # S2: 완전히 묶인 라우팅
        rows += [{"lot": L, "step": "S1", "tool": t1, "chamber": "A"},
                 {"lot": L, "step": "S2", "tool": x, "chamber": "A"},
                 {"lot": L, "step": "S3", "tool": "Z1" if i % 2 else "Z2", "chamber": "A"}]   # S3: 독립
    hist = pd.DataFrame(rows)
    status = pd.Series([i < 7 or i == 15 for i in range(16)], index=lots)   # T1 로트 7/8 양성, T2 1/8
    t = cm.commonality_table(hist, status, min_lots=5)
    t = t.set_index(["step", "tool"])
    assert t.loc[("S1", "T1"), "overlap_with_top"] == pytest.approx(1.0) and t.loc[("S1", "T1"), "note"] == "top candidate"
    assert t.loc[("S2", "X"), "overlap_with_top"] == pytest.approx(1.0)
    assert t.loc[("S2", "X"), "note"].startswith("routing overlap 1.00")
    assert t.loc[("S1", "T2"), "overlap_with_top"] == pytest.approx(0.0)
    assert 0.0 < t.loc[("S3", "Z1"), "overlap_with_top"] < 1.0 and t.loc[("S3", "Z1"), "note"] == ""
    assert t.loc[("S2", "X"), "q_bh"] < 0.05 and t.loc[("S2", "X"), "evidence"] == "ok"


def test_insufficient_evidence_flag_and_sort():
    rows = [{"lot": f"l{i}", "step": "S1", "tool": "big", "chamber": ""} for i in range(20)]
    rows += [{"lot": f"m{i}", "step": "S1", "tool": "tiny", "chamber": ""} for i in range(3)]
    hist = pd.DataFrame(rows)
    status = pd.Series([True] * 3 + [False] * 17 + [True] * 3, index=[f"l{i}" for i in range(20)] + [f"m{i}" for i in range(3)])
    t = cm.commonality_table(hist, status, by=("step", "tool"), min_lots=5)
    assert "chamber" in t.columns                                   # by 에 없어도 열은 채운다
    tiny = t[t["tool"] == "tiny"].iloc[0]
    assert tiny["evidence"] == "insufficient" and "insufficient" in tiny["note"] and tiny["p_fisher"] < 0.05
    assert t.iloc[0]["tool"] == "big" and t.iloc[-1]["tool"] == "tiny"    # 근거 부족은 뒤로
    assert t.iloc[0]["note"] == "top candidate"


def test_bh_adjust_monotone_and_nan_safe():
    q = cm.bh_adjust(np.array([0.01, 0.04, 0.03, np.nan, 0.5]))
    # m=4: 0.01*4/1=0.04, 0.03*4/2=0.06, 0.04*4/3=0.0533, 0.5 -> 오른쪽부터 누적 최소: 0.04, 0.0533, 0.0533, 0.5
    assert np.isnan(q[3]) and q[0] == pytest.approx(0.04) and q[4] == pytest.approx(0.5)
    assert q[1] == pytest.approx(0.04 * 4 / 3) and q[2] == pytest.approx(0.04 * 4 / 3)
    assert (q[[0, 2, 1, 4]][1:] >= q[[0, 2, 1, 4]][:-1]).all()        # p 순으로 단조
    assert np.isnan(cm.bh_adjust(np.array([np.nan]))).all()


def test_rate_ratio_ci_zero_cell_correction():
    rr, lo, hi = cm._rate_ratio_ci(0, 10, 5, 10)
    assert 0 < lo < rr < hi and rr < 1
    rr, lo, hi = cm._rate_ratio_ci(8, 10, 2, 10)
    assert rr == pytest.approx(4.0) and lo < 4.0 < hi
    assert all(np.isnan(v) for v in cm._rate_ratio_ci(1, 0, 1, 5))


def test_no_overlapping_lots_raises(planted):
    status = pd.Series([True, False], index=["nope1", "nope2"])
    with pytest.raises(ValueError, match="겹치지"):
        cm.commonality_table(planted["hist"], status)


def test_pm_age_summary(planted):
    t = planted["table"].iloc[0]
    pm = cm.pm_age_summary(planted["hist"], planted["status"], t["step"], t["tool"], t["chamber"])
    assert pm and pm["n_bad"] + pm["n_good"] == t["n_lots"] and np.isfinite(pm["median_days_bad"])
    assert cm.pm_age_summary(planted["hist"].drop(columns="pm_date"), planted["status"], t["step"], t["tool"]) is None


def test_works_with_synthetic_lswmd_lots():
    """tests/synthetic_wm811k.make_lswmd 의 로트명·라벨을 예측으로 쓰고 이력은 합성으로 붙인다."""
    raw = make_lswmd(n_lots=40, n_unlabeled=0, seed=7)
    lab = raw["failureType"].apply(lambda a: a.reshape(-1)[0])
    preds = pd.DataFrame({"lot": raw["lotName"], "wafer_index": raw["waferIndex"],
                          "y_pred": lab.map({"Edge-Loc": "EDGE_LOC"}).fillna("OTHER")})
    hist = cm.synthetic_history(preds["lot"].unique(), seed=1)
    status = cm.lot_pattern_status(preds, "EDGE_LOC", min_n=3)
    t = cm.commonality_table(hist, status)
    assert len(t) and set(t["step"]) == {s for s, _ in cm.DEFAULT_STEPS}
    assert (t["n_lots"] + t["n_other"] == len(status)).all()


# ──────────────────────────────────────────
# 그림 / CLI
# ──────────────────────────────────────────
def test_run_writes_outputs_and_summary(planted, tmp_path, capsys):
    res = cm.run(planted["preds"], planted["hist"], "EDGE_LOC", tmp_path, label="t")
    assert (tmp_path / "commonality_EDGE_LOC.csv").exists() and (tmp_path / "commonality_EDGE_LOC.png").stat().st_size > 5_000
    text = (tmp_path / "commonality_EDGE_LOC_summary.txt").read_text(encoding="utf-8")
    assert "top candidate ETCH_M1 ETCH-02" in text and "PM age" in text and "Correlation, not cause" in text
    assert res["table"].iloc[0]["tool"] == "ETCH-02"


def test_main_csv_path_and_demo(planted, tmp_path, capsys):
    p, h = tmp_path / "preds.csv", tmp_path / "x.lot_history.csv"
    planted["preds"].to_csv(p, index=False)
    planted["hist"].to_csv(h, index=False)
    cm.main([str(p), "--history", str(h), "--pattern", "EDGE_LOC", "--by", "step", "tool",
             "--output", str(tmp_path / "o")])
    t = pd.read_csv(tmp_path / "o" / "commonality_EDGE_LOC.csv")
    assert t.iloc[0]["tool"] == "ETCH-02" and t["chamber"].isna().all()       # tool 단위 집계
    cm.main(["--demo", "--output", str(tmp_path / "d")])
    out = capsys.readouterr().out
    assert "all as expected" in out and "WARNING routing confound" in out
    assert (tmp_path / "d" / "coupled_routing_0.9" / "commonality_EDGE_LOC.png").exists()


def test_main_requires_history(tmp_path):
    p = tmp_path / "preds.csv"
    pd.DataFrame({"lot": ["a"], "y_pred": ["EDGE_LOC"]}).to_csv(p, index=False)
    with pytest.raises(SystemExit):
        cm.main([str(p)])
