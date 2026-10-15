# tests/test_slot.py
# 슬롯 의존성 검정(wm811k_slot.py)의 코딩 오류를 잡는다. 전부 합성 데이터다.
# 심은 효과가 잡히고 효과 없는 데이터에서 울리지 않는지의 로직 확인이지 탐지 성능이 아니다.

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

import wm811k_slot as slot  # noqa: E402
from synthetic_wm811k import make_lswmd  # noqa: E402

N_PERM = 500            # 테스트용 순열 수 (기본 2000 보다 적게 - 30초 제한)


@pytest.fixture(scope="module")
def planted():
    return slot.synthetic_slot_predictions(1000, seed=1, end_effect=0.5)


@pytest.fixture(scope="module")
def null():
    return slot.synthetic_slot_predictions(1000, seed=2, end_effect=0.0)


# ──────────────────────────────────────────
# 표 / Wilson 구간
# ──────────────────────────────────────────
def test_slot_rate_table_columns_and_wilson_bounds(planted):
    t = slot.slot_rate_table(planted, "EDGE_RING")
    assert list(t.columns) == ["slot", "n", "k", "rate", "wilson_lo", "wilson_hi", "ratio_to_overall"]
    assert t["slot"].tolist() == list(range(1, 26))
    assert int(t["n"].sum()) == len(planted) and int(t["k"].sum()) == int((planted["y_pred"] == "EDGE_RING").sum())
    assert ((t["wilson_lo"] >= 0) & (t["wilson_lo"] <= t["rate"]) & (t["rate"] <= t["wilson_hi"]) & (t["wilson_hi"] <= 1)).all()
    overall = (planted["y_pred"] == "EDGE_RING").mean()
    assert t["ratio_to_overall"].to_numpy() == pytest.approx((t["rate"] / overall).to_numpy())
    assert t.attrs["overall_rate"] == pytest.approx(overall)


def test_wilson_interval_edge_cases():
    lo, hi = slot.wilson_interval(np.array([0, 10, 5, 0]), np.array([10, 10, 10, 0]))
    assert lo[0] == 0.0 and hi[1] == 1.0                       # k=0 / k=n
    assert 0 < lo[2] < 0.5 < hi[2] < 1
    assert lo[3] == 0.0 and hi[3] == 1.0                       # n=0 -> [0, 1]
    assert hi[0] < 0.35 and lo[1] > 0.65                       # 0/10 상한 ~0.28, 10/10 하한 ~0.72


# ──────────────────────────────────────────
# 끝 슬롯 검정
# ──────────────────────────────────────────
def test_end_slot_effect_detected(planted):
    r = slot.end_slot_test(planted, "EDGE_RING", n_perm=N_PERM)
    assert r["odds_ratio"] > 1.3
    assert r["p_pooled"] < 0.01 and r["test_pooled"] == "chi2"
    assert r["p_cluster"] < 0.01 and r["n_lots_informative"] == 40
    assert r["n_end"] == 240 and r["n_mid"] == 760 and r["k_end"] + r["k_mid"] == int((planted["y_pred"] == "EDGE_RING").sum())
    assert r["end_slots"] == (1, 2, 3, 23, 24, 25)


def test_no_effect_stays_quiet(null):
    r = slot.end_slot_test(null, "EDGE_RING", n_perm=N_PERM)
    assert r["p_pooled"] > 0.05 and r["p_cluster"] > 0.05
    assert 0.6 < r["odds_ratio"] < 1.6
    t = slot.slot_trend_test(null, "EDGE_RING")
    assert t["p"] > 0.05


def test_lot_confound_splits_pooled_and_cluster_p():
    """로트 효과 + 치우친 표본: 풀링은 울리고 로트 층화 순열은 울리지 않아야 한다."""
    df = slot.synthetic_confounded_predictions(40, seed=3)
    r = slot.end_slot_test(df, "EDGE_RING", n_perm=N_PERM)
    assert r["p_pooled"] < 1e-6
    assert r["p_cluster"] > 0.05
    assert 0 < r["n_lots_informative"] < 40                  # 양성 로트(끝 슬롯만)는 기여하지 않는다
    assert "lot effect" in slot._verdict(r, slot.slot_trend_test(df, "EDGE_RING"))


def test_cluster_p_is_nan_when_no_lot_is_informative():
    df = pd.DataFrame({"lot": ["a", "b", "c", "d"], "wafer_index": [1, 10, 2, 12],
                       "y_pred": ["EDGE_RING", "LOC", "EDGE_RING", "LOC"]})
    r = slot.end_slot_test(df, "EDGE_RING", n_perm=50)
    assert np.isnan(r["p_cluster"]) and r["n_lots_informative"] == 0
    assert r["test_pooled"] == "fisher"                       # 기대도수 < 5
    assert "not possible" in slot._verdict(r, {"rho": np.nan, "p": np.nan, "n": 4})


def test_pooled_uses_fisher_for_small_tables():
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"lot": [f"l{i // 5}" for i in range(30)], "wafer_index": rng.integers(1, 26, 30),
                       "y_pred": np.where(rng.random(30) < 0.1, "EDGE_RING", "LOC")})
    r = slot.end_slot_test(df, "EDGE_RING", n_perm=50)
    assert r["test_pooled"] in ("fisher", "degenerate") and (np.isnan(r["p_pooled"]) or 0 <= r["p_pooled"] <= 1)


# ──────────────────────────────────────────
# 추세 검정
# ──────────────────────────────────────────
def test_trend_detects_monotone_gradient():
    df = slot.synthetic_slot_predictions(1500, seed=4, end_effect=0.0, trend=1.5, base_rate=0.15)
    t = slot.slot_trend_test(df, "EDGE_RING")
    assert t["rho"] > 0.1 and t["p"] < 0.01 and t["n"] == 1500
    assert "gradient" in slot._verdict(slot.end_slot_test(df, "EDGE_RING", n_perm=50), t)


def test_trend_nan_when_degenerate():
    df = pd.DataFrame({"lot": ["a"] * 4, "wafer_index": [1, 1, 1, 1], "y_pred": ["EDGE_RING", "LOC", "LOC", "LOC"]})
    assert np.isnan(slot.slot_trend_test(df, "EDGE_RING")["rho"])
    df["wafer_index"] = [1, 2, 3, 4]
    assert np.isnan(slot.slot_trend_test(df, "CENTER")["rho"])     # 발생 전무


# ──────────────────────────────────────────
# 입력 / 끝 슬롯 자동 결정
# ──────────────────────────────────────────
def test_missing_columns_raise():
    df = pd.DataFrame({"lot": ["a"], "y_pred": ["EDGE_RING"]})
    with pytest.raises(ValueError, match="wafer_index"):
        slot.slot_rate_table(df, "EDGE_RING")
    with pytest.raises(ValueError, match="lot"):
        slot.end_slot_test(df.assign(wafer_index=[1]).drop(columns="lot"), "EDGE_RING", n_perm=10)


def test_prepare_drops_nan_slots_and_skipped_rows():
    df = pd.DataFrame({"lot": ["a", "a", "b", "b"], "wafer_index": [1, np.nan, 3, 4],
                       "y_pred": ["EDGE_RING", "EDGE_RING", "LOC", "EDGE_RING"],
                       "skipped": [False, False, True, False]})
    t = slot.slot_rate_table(df, "EDGE_RING")
    assert t["slot"].tolist() == [1, 4] and t["k"].tolist() == [1, 1]


def test_resolve_end_slots_outside_25_range():
    ends, note = slot.resolve_end_slots(np.arange(1, 26))
    assert ends == (1, 2, 3, 23, 24, 25) and note.startswith("25-slot")
    ends, note = slot.resolve_end_slots(np.arange(0, 100))          # 0..99 (100 매)
    assert ends == (0, 1, 2, 97, 98, 99) and "outside" in note
    ends, _ = slot.resolve_end_slots(np.array([0, 1, 2, 3]))         # 아주 짧은 범위
    assert len(ends) == 2


def test_works_on_synthetic_lswmd_wafer_index():
    """tests/synthetic_wm811k.make_lswmd 의 waferIndex(0 부터) 를 그대로 넣어도 돈다 (라벨을 y_pred 로)."""
    raw = make_lswmd(n_lots=30, n_unlabeled=0, seed=5)
    lab = raw["failureType"].apply(lambda a: a.reshape(-1)[0])
    df = pd.DataFrame({"lot": raw["lotName"], "wafer_index": raw["waferIndex"],
                       "y_pred": lab.map({"Edge-Ring": "EDGE_RING"}).fillna("OTHER")})
    ends, note = slot.resolve_end_slots(df["wafer_index"].to_numpy())
    assert "outside" in note and len(ends) == 6                     # 합성 waferIndex 는 0 부터 -> 양끝 3개씩으로 대체
    assert ends[0] == 0 and ends[-1] == int(df["wafer_index"].max())
    r = slot.end_slot_test(df, "EDGE_RING", ends, n_perm=50)
    assert r["n_end"] + r["n_mid"] == len(df)
    assert np.isnan(r["p_cluster"]) or 0 <= r["p_cluster"] <= 1


# ──────────────────────────────────────────
# 그림 / CLI
# ──────────────────────────────────────────
def test_plot_and_run_write_outputs(planted, tmp_path):
    res = slot.run(planted, "EDGE_RING", tmp_path, n_perm=50, label="t")
    assert (tmp_path / "slot_EDGE_RING_table.csv").exists()
    assert (tmp_path / "slot_EDGE_RING.png").stat().st_size > 5_000
    text = (tmp_path / "slot_EDGE_RING_summary.txt").read_text(encoding="utf-8")
    assert "p_cluster" in text and "wafer_index" in text and "verdict" in text
    assert res["end"]["p_pooled"] < 0.01


def test_main_demo_and_csv_path(tmp_path, capsys, planted):
    p = tmp_path / "preds.csv"
    planted.to_csv(p, index=False)
    slot.main([str(p), "--pattern", "EDGE_RING", "--n-perm", "50", "--output", str(tmp_path / "o")])
    assert (tmp_path / "o" / "slot_EDGE_RING.png").exists()
    out = capsys.readouterr().out
    assert "odds_ratio" in out
    # --demo: 3 시나리오 모두 기대와 일치해야 종료 코드 0
    slot.main(["--demo", "--n-perm", "100", "--output", str(tmp_path / "d")])
    out = capsys.readouterr().out
    assert "all scenarios as expected" in out and (tmp_path / "d" / "slot_demo.png").exists()


def test_main_rejects_csv_without_slot_column(tmp_path):
    p = tmp_path / "bad.csv"
    pd.DataFrame({"lot": ["a"], "y_pred": ["EDGE_RING"]}).to_csv(p, index=False)
    with pytest.raises(SystemExit):
        slot.main([str(p)])
