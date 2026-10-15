# tests/test_scratch_shape.py
# wm811k_scratch_shape 의 직선/원 적합·모양 판정·로트 재현성 판정의 코딩 오류를 잡는다.
# 전부 합성 데이터다. 판정이 맞는 것은 로직 확인이지 성능이 아니다.

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

import wm811k_scratch_shape as ss  # noqa: E402
from synthetic_wm811k import make_wafermap  # noqa: E402


# ──────────────────────────────────────────
# 적합
# ──────────────────────────────────────────
def test_fit_line_recovers_angle_and_zero_residual():
    t = np.linspace(-1, 1, 30)
    for ang in (0.0, 30.0, -60.0, 89.0):
        xy = np.column_stack([t * np.cos(np.radians(ang)), t * np.sin(np.radians(ang))])
        r = ss.fit_line(xy)
        assert r["sigma"] == pytest.approx(0.0, abs=1e-9)
        assert r["angle_deg"] == pytest.approx(ang, abs=1e-6)
    r = ss.fit_line(np.column_stack([np.zeros(10), np.linspace(-1, 1, 10)]))    # 수직선 -> 90 (경계)
    assert r["angle_deg"] == pytest.approx(90.0)
    assert np.isnan(ss.fit_line(np.zeros((1, 2)))["angle_deg"])


def test_fit_circle_kasa_recovers_circle():
    th = np.linspace(0.2, 2.0, 40)
    cx, cy, R = 1.3, -0.4, 1.7
    xy = np.column_stack([cx + R * np.cos(th), cy + R * np.sin(th)])
    r = ss.fit_circle_kasa(xy)
    assert r["sigma"] == pytest.approx(0.0, abs=1e-9)
    assert (r["cx"], r["cy"], r["r"]) == pytest.approx((cx, cy, R), abs=1e-6)
    # 공선 / 점 부족은 inf 로 안전하게
    assert ss.fit_circle_kasa(np.column_stack([np.linspace(0, 1, 5), np.zeros(5)]))["sigma"] == np.inf
    assert ss.fit_circle_kasa(np.zeros((2, 2)))["r"] == np.inf


# ──────────────────────────────────────────
# 맵 한 장의 모양
# ──────────────────────────────────────────
def test_synthetic_line_is_line_with_notch_relative_angle():
    s = ss.scratch_shape(ss.synthetic_scratch_map("line", 1, angle_deg=30.0))
    assert s["shape"] == "line" and s["ratio"] <= 0.5 and s["n"] >= 6
    assert s["line_angle_deg"] == pytest.approx(-60.0, abs=4.0)      # 30 - (-90) = 120 -> 축 접기 -60
    s0 = ss.scratch_shape(ss.synthetic_scratch_map("line", 1, angle_deg=30.0), notch_deg=0.0)
    assert s0["line_angle_deg"] == pytest.approx(30.0, abs=4.0)
    assert s["length_norm"] > 0.4


def test_synthetic_arc_is_arc():
    for seed in (1, 2, 4):
        s = ss.scratch_shape(ss.synthetic_scratch_map("arc", seed))
        assert s["shape"] == "arc", s
        assert s["ratio"] >= 2.0 and 0.3 <= s["arc_r_norm"] <= 5.0
        assert s["arc_center_outside"] is True                       # 원 중심이 웨이퍼 밖
        assert -180.0 < s["arc_center_deg"] <= 180.0
    for seed in (1, 2, 3):                                            # 노이즈 없으면 항상 호
        assert ss.scratch_shape(ss.synthetic_scratch_map("arc", seed, noise=0.0))["shape"] == "arc"


def test_broken_arc_is_documented_limitation():
    """seed 3 의 노이즈 뒤집기가 폭 1다이 호를 끊어 반 토막(길이 약 1R)만 최대 성분이 된다.
    짧은 조각은 곡률이 작아 ambiguous 로 떨어진다 - 모듈 머리말 '한계'에 적은 그 경우다."""
    s = ss.scratch_shape(ss.synthetic_scratch_map("arc", 3, noise=0.02))
    full = ss.scratch_shape(ss.synthetic_scratch_map("arc", 3, noise=0.0))
    assert s["shape"] in ("ambiguous", "arc") and s["n"] < full["n"] and full["shape"] == "arc"


def test_blob_is_too_short_or_ambiguous():
    s = ss.scratch_shape(ss.synthetic_scratch_map("blob", 1))
    assert s["shape"] in ("too_short", "ambiguous")
    rng = np.random.default_rng(0)
    for i in range(3):
        s = ss.scratch_shape(make_wafermap("loc", 50 + i, rng))
        assert s["shape"] in ("too_short", "ambiguous"), s


def test_scratch_shape_edge_cases():
    arr = ss.synthetic_scratch_map("line", 1)
    arr[arr == 2] = 1
    s = ss.scratch_shape(arr)
    assert s["shape"] == "too_short" and s["n"] == 0 and np.isnan(s["ratio"])
    # min_len_frac 를 아주 크게 주면 전부 too_short
    assert ss.scratch_shape(ss.synthetic_scratch_map("line", 1), min_len_frac=10.0)["shape"] == "too_short"
    assert set(ss.scratch_shape(ss.synthetic_scratch_map("arc", 1))) >= {
        "shape", "ratio", "line_angle_deg", "arc_r_norm", "arc_center_outside", "arc_center_deg",
        "length_norm", "n", "sigma_line", "sigma_circle"}


# ──────────────────────────────────────────
# 로트 요약
# ──────────────────────────────────────────
def test_axial_consistency_folds_180():
    r = ss.axial_consistency([10.0, 12.0, 8.0, -170.0 + 180.0, 190.0 - 180.0])   # 전부 같은 축
    assert r["r_bar"] > 0.99 and abs(r["mean_axis_deg"] - 10.0) < 2.0 and r["p"] < 0.05
    r = ss.axial_consistency([-72.0, -36.0, 0.0, 36.0, 72.0])                     # 고르게 벌림
    assert r["r_bar"] < 0.05
    r = ss.axial_consistency([89.0, -89.0, 88.0, -88.0])                           # 경계 양쪽은 같은 축
    assert r["r_bar"] > 0.99


@pytest.fixture(scope="module")
def demo_df():
    return ss.demo_records(seed=0)


def test_lot_verdicts_on_synthetic_lots(demo_df):
    lots = ss.lot_scratch_summary(demo_df, notch_deg=-90.0, min_n=3)
    assert list(lots.columns) == ["lot", "n_scratch", "n_line", "n_arc", "n_ambiguous", "n_too_short",
                                  "angle_consistency", "mean_axis_deg", "p_axial", "verdict"]
    v = dict(zip(lots["lot"], lots["verdict"]))
    assert v == {"demoL": "reproducible_line", "demoM": "random",
                 "demoN": "random", "demoS": "insufficient"}
    L = lots.set_index("lot")
    assert L.loc["demoL", "n_line"] == 5 and L.loc["demoL", "angle_consistency"] > 0.9
    assert abs(L.loc["demoL", "mean_axis_deg"] - (-60.0)) < 5.0
    assert L.loc["demoN", "n_line"] == 0 and L.loc["demoN", "n_arc"] >= 3
    assert L.loc["demoS", "n_scratch"] == 2
    p = L["p_axial"].dropna()
    assert np.all((p >= 0.0) & (p <= 1.0))


def test_lot_summary_uses_y_pred_and_only_scratch(demo_df):
    df = demo_df.copy()
    df["y_pred"] = "LOC"
    assert ss.lot_scratch_summary(df).empty
    df.loc[df["lot"] == "demoL", "y_pred"] = "SCRATCH"
    lots = ss.lot_scratch_summary(df)
    assert lots["lot"].tolist() == ["demoL"] and lots["verdict"].iloc[0] == "reproducible_line"
    w = ss.wafer_scratch_table(df)
    assert len(w) == 5 and set(w["shape"]) == {"line"}


def test_cli_demo_writes_outputs(tmp_path):
    out = tmp_path / "demo"
    res = ss.main(["--demo", "--output", str(out)])
    for f in ("scratch_wafers.csv", "scratch_lots.csv", "scratch_fits.png"):
        assert (out / f).exists()
    assert len(pd.read_csv(out / "scratch_lots.csv")) == 4 and len(res["wafers"]) == 16
