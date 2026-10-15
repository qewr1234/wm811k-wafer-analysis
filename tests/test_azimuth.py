# tests/test_azimuth.py
# wm811k_azimuth 의 각도 규약·Rayleigh 검정·로트 판정·로즈 그림의 코딩 오류를 잡는다.
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

import wm811k_azimuth as az  # noqa: E402
from synthetic_wm811k import df_to_wafermap, make_wafermap  # noqa: E402
from wafer_map_visualizer import generate_sample_wafer_data  # noqa: E402


# ──────────────────────────────────────────
# 각도 규약
# ──────────────────────────────────────────
def test_notch_relative_angle_convention():
    assert az.notch_relative_angle(-90, -90) == 0.0
    assert az.notch_relative_angle(0, -90) == 90.0
    assert az.notch_relative_angle(90, -90) == 180.0          # 경계는 +180 쪽 (-180, 180]
    assert az.notch_relative_angle(-180, -90) == -90.0
    assert az.notch_relative_angle(270, -90) == 0.0           # 360 주기
    out = az.notch_relative_angle(np.array([-90.0, 0.0, 90.0, 180.0]), -90.0)
    assert isinstance(out, np.ndarray)
    assert out.tolist() == [0.0, 90.0, 180.0, -90.0]
    assert np.all((out > -180.0) & (out <= 180.0))
    # 노치를 다른 곳에 두면 그만큼 평행 이동
    assert az.notch_relative_angle(0, 0) == 0.0 and az.notch_relative_angle(45, 90) == -45.0


def test_component_azimuth_of_generator_edge_loc():
    """생성기 edge_loc 은 맵 좌표 45도 호 -> 노치(-90) 기준 135도, 외곽, 폭 약 70도."""
    df = generate_sample_wafer_data(defect_mode="edge_loc", noise=0.0)
    r = az.component_azimuth(df_to_wafermap(df, 10.0), notch_deg=-90.0)
    assert abs(r["theta_deg"] - 135.0) < 6.0
    assert r["r_centroid"] > 0.7
    assert 40.0 < r["span_deg"] < 100.0
    assert r["size"] > 10
    # notch_deg 를 바꾸면 theta 만 그만큼 움직인다
    r2 = az.component_azimuth(df_to_wafermap(df, 10.0), notch_deg=0.0)
    assert abs(r2["theta_deg"] - 45.0) < 6.0 and r2["span_deg"] == r["span_deg"]


def test_component_azimuth_no_fail_is_safe():
    arr = df_to_wafermap(generate_sample_wafer_data(defect_mode="clean"), 10.0)
    r = az.component_azimuth(arr)
    assert np.isnan(r["theta_deg"]) and r["size"] == 0 and r["span_deg"] == 0.0


# ──────────────────────────────────────────
# Rayleigh
# ──────────────────────────────────────────
def test_rayleigh_mean_crosses_zero_boundary():
    r = az.rayleigh_test([-170.0, 175.0])
    assert abs(abs(r["mean_deg"]) - 180.0) < 5.0            # 산술 평균(2.5도)이 아니라 약 -177.5도
    assert r["r_bar"] > 0.99 and 0.0 <= r["p"] <= 1.0


def test_rayleigh_p_in_unit_interval_and_direction():
    rng = np.random.default_rng(0)
    for n in (2, 3, 5, 12, 49, 50, 200):
        same = np.full(n, 30.0)                                 # r_bar = 1: 근사식이 음수가 되던 경우
        r = az.rayleigh_test(same)
        assert 0.0 <= r["p"] <= 1.0 and r["r_bar"] == pytest.approx(1.0)
        if n >= 3:
            assert r["p"] < 0.05
        r = az.rayleigh_test(rng.uniform(-180, 180, n))
        assert 0.0 <= r["p"] <= 1.0
    assert az.rayleigh_test([]) == {"n": 0, "r_bar": pytest.approx(np.nan, nan_ok=True),
                                    "mean_deg": pytest.approx(np.nan, nan_ok=True), "p": 1.0}
    assert az.rayleigh_test([10.0])["p"] == 1.0
    assert az.rayleigh_test([10.0, np.nan, 20.0])["n"] == 2
    # 집중된 각도는 p 작고, 균일 난수 큰 표본은 p 크다 (대부분)
    assert az.rayleigh_test(45 + rng.normal(0, 8, 12))["p"] < 0.01
    assert az.rayleigh_test(rng.uniform(-180, 180, 500))["p"] > 0.05


def test_rayleigh_permutation_is_deterministic():
    th = [10.0, 40.0, -20.0, 100.0]
    assert az.rayleigh_test(th, seed=1) == az.rayleigh_test(th, seed=1)


# ──────────────────────────────────────────
# 로트 판정
# ──────────────────────────────────────────
@pytest.fixture(scope="module")
def demo_df():
    return az.demo_records(seed=0)


def test_lot_verdicts_on_synthetic_lots(demo_df):
    lots = az.lot_azimuth_summary(demo_df, classes=("EDGE_LOC", "LOC"), min_n=3, notch_deg=-90.0)
    assert list(lots.columns) == ["lot", "n", "r_bar", "mean_deg", "span_med", "p", "verdict"]
    v = dict(zip(lots["lot"], lots["verdict"]))
    assert v == {"demoA": "fixed_angle", "demoB": "scattered",
                 "demoC": "insufficient", "demoD": "scattered"}
    a = lots.set_index("lot").loc["demoA"]
    assert a["n"] == 8 and a["r_bar"] > 0.9 and abs(a["mean_deg"] - 135.0) < 8.0
    assert np.all((lots["p"].dropna() >= 0.0) & (lots["p"].dropna() <= 1.0))


def test_lot_summary_prefers_y_pred_and_filters_classes(demo_df):
    df = demo_df.copy()
    df["y_pred"] = "RANDOM"                                   # 예측이 있으면 예측을 쓴다 -> 대상 없음
    assert az.lot_azimuth_summary(df).empty
    df.loc[df["lot"] == "demoA", "y_pred"] = "EDGE_LOC"
    lots = az.lot_azimuth_summary(df)
    assert lots["lot"].tolist() == ["demoA"] and lots["verdict"].iloc[0] == "fixed_angle"
    assert az.lot_azimuth_summary(demo_df, classes=("LOC",))["lot"].tolist() == ["demoC", "demoD"]


def test_min_n_controls_insufficient(demo_df):
    lots = az.lot_azimuth_summary(demo_df, min_n=9)
    assert set(lots["verdict"]) == {"insufficient"}
    lots = az.lot_azimuth_summary(demo_df, min_n=2)
    assert lots.set_index("lot").loc["demoC", "verdict"] in ("fixed_angle", "scattered")


def test_line_summary_one_vote_per_lot():
    s = pd.DataFrame({"lot": list("abcdef"), "n": [4, 4, 4, 1, 1, 2],
                      "mean_deg": [100, 105, 95, 102, 98, 101], "r_bar": 1.0, "p": 0.0,
                      "span_med": 50.0, "verdict": "fixed_angle"})
    r = az.line_azimuth_summary(s)
    assert r["n_lots"] == 6 and r["verdict"] == "line_fixed_angle" and abs(r["mean_deg"] - 100) < 3
    r = az.line_azimuth_summary(s, min_lot_n=3)
    assert r["n_lots"] == 3
    r = az.line_azimuth_summary(s.head(2))
    assert r["verdict"] == "insufficient"
    s["mean_deg"] = [0, 60, 120, 180, -120, -60]
    assert az.line_azimuth_summary(s)["verdict"] == "line_scattered"


# ──────────────────────────────────────────
# 입력 결합 / 그림 / CLI
# ──────────────────────────────────────────
def test_load_records_merges_predictions(tmp_path):
    rng = np.random.default_rng(3)
    rows = []
    for lot in ("lot1", "lot2"):
        for w in range(3):
            rows.append({"waferMap": make_wafermap("edge_loc", 10 * len(rows) + w, rng), "dieSize": 1.0,
                         "lotName": lot, "waferIndex": w, "trianTestLabel": np.array([["Training"]]),
                         "failureType": np.array([["Edge-Loc"]])})
    pkl = tmp_path / "rec.pkl"
    pd.DataFrame(rows).to_pickle(pkl)
    rec = az.load_records(pkl)
    assert list(rec.columns) == ["waferMap", "lot", "wafer_index", "y_true"] and len(rec) == 6
    assert set(rec["y_true"]) == {"EDGE_LOC"}

    pred = pd.DataFrame({"lot": ["lot1"] * 3 + ["lot2"] * 2, "wafer_index": [0, 1, 2, 0, 2],
                         "y_pred": ["LOC"] * 5, "confidence": 0.9})
    pred.to_csv(tmp_path / "pred.csv", index=False)
    rec = az.load_records(pkl, tmp_path / "pred.csv")
    assert len(rec) == 5 and set(rec["y_pred"]) == {"LOC"} and "confidence" in rec.columns
    assert az.label_column(rec) == "y_pred"


def test_rose_plot_and_cli_demo(tmp_path):
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(subplot_kw={"projection": "polar"})
    az.plot_azimuth_rose([10, 20, 30, np.nan], ax, notch_deg=-90.0, title="t")
    assert ax.get_title().startswith("t") and "n=3" in ax.get_title()
    plt.close(fig)

    out = tmp_path / "demo"
    res = az.main(["--demo", "--output", str(out)])
    for f in ("azimuth_wafers.csv", "azimuth_lots.csv", "azimuth_line.txt", "azimuth_rose.png"):
        assert (out / f).exists()
    lots = pd.read_csv(out / "azimuth_lots.csv")
    assert len(lots) == 4 and res["line"]["n_lots"] == 4
    assert "notch_deg=-90" in (out / "azimuth_line.txt").read_text(encoding="utf-8")
