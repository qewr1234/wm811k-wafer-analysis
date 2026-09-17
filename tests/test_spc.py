# tests/test_spc.py
# SPC 규칙과 관리도 계산의 코딩 오류를 잡는다. 탐지 성능 주장이 아니다.

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import wm811k_spc as spc  # noqa: E402


def test_western_electric_rules_fire_where_expected():
    z = np.zeros(20)
    z[5] = 3.5                                  # R1
    z[10], z[11] = 2.5, 2.5                     # R2: 3점 중 2점 2σ 밖 (같은 쪽)
    r = spc.western_electric(z)
    assert r["R1"][5] and r["R1"].sum() == 1
    assert r["R2"][11]
    assert not r["R2"][10]                      # 창이 완성되는 점에서만 표시

    z = np.full(12, 0.5)                        # R4: 8점 연속 같은 쪽
    r = spc.western_electric(z)
    assert not r["R4"][6] and r["R4"][7] and r["R4"][11]

    z = np.array([1.5, 1.5, -0.2, 1.5, 1.5])    # R3: 5점 중 4점 1σ 밖
    assert spc.western_electric(z)["R3"][4]
    assert not spc.western_electric(-z)["R2"].any()


def test_western_electric_sides_do_not_mix():
    z = np.array([2.5, -2.5, 0.1])              # 2σ 밖 2점이 서로 반대쪽 → R2 아님
    assert not spc.western_electric(z)["R2"].any()
    z = np.array([2.5, -2.5, 2.5])              # 가운데가 반대쪽이어도 같은 쪽 2점 → R2
    assert spc.western_electric(z)["R2"][2]


def test_ewma_limits_grow_to_asymptote():
    e, lim = spc.ewma_chart(np.zeros(200))
    assert np.all(np.diff(lim) >= 0)
    assert lim[-1] == pytest.approx(spc.EWMA_L * np.sqrt(spc.EWMA_LAMBDA / (2 - spc.EWMA_LAMBDA)), rel=1e-3)
    assert np.all(e == 0)


def test_chunk_ids_fixed_and_by_lot():
    df = pd.DataFrame({"lot": ["a"] * 10 + ["b"] * 30 + ["c"] * 8 + ["d"] * 3})
    gid = spc.chunk_ids(df, 25, by_lot=False)
    assert gid[:25].tolist() == [0] * 25 and gid[25:50].tolist() == [1] * 25
    assert (gid[50:] == -1).all()               # 꼬리 1장은 버린다
    gid = spc.chunk_ids(df, 25, by_lot=True)
    assert (gid[:40] == 0).all()                # a+b 를 합쳐 40장 ≥ 25
    assert (gid[40:] == -1).all()               # c+d 11장 < 25/2 → 버림


def test_p_chart_center_from_baseline_only():
    S = pd.DataFrame({"n": [25] * 10, "count": [5] * 5 + [20] * 5, "end_idx": np.arange(25, 251, 25)})
    ch = spc.p_chart("X", S, n_base=5, laney=False)
    assert ch.center == pytest.approx(0.2)
    assert ch.alarms["R1"][5:].all() and not ch.alarms["R1"][:5].any()
    assert (ch.ucl <= 1).all() and (ch.lcl >= 0).all()


def test_laney_widens_limits_under_overdispersion():
    rng = np.random.default_rng(0)
    n = np.full(60, 100)
    # 부분군마다 p 자체가 크게 흔들리는 과산포 시퀀스
    p_true = np.clip(rng.normal(0.3, 0.12, 60), 0.02, 0.98)
    count = rng.binomial(n, p_true)
    S = pd.DataFrame({"n": n, "count": count, "end_idx": np.cumsum(n) - 1})
    plain = spc.p_chart("X", S, n_base=30, laney=False)
    laney = spc.p_chart("X", S, n_base=30, laney=True)
    assert laney.sigma_z > 1.5
    assert laney.alarms["R1"].sum() < plain.alarms["R1"].sum()


def test_demo_detects_injected_shifts(tmp_path):
    df = spc.demo_predictions()
    charts, sizes, dropped = spc.build_charts(df, spc.CLASSES, 25, False, len(df) // 2, 0.7)
    by_name = {ch.name: ch for ch in charts}
    assert "EDGE_RING" in by_name and "SCRATCH" in by_name and "LOW_CONFIDENCE" in by_name
    alarms = spc.alarm_table(charts)
    fd = spc.first_detection(alarms).set_index(["chart", "rule"])["first_wafer_idx"]
    # 심은 시점 이후에 잡혀야 한다 (SCRATCH 계단 4125, 저신뢰 3750)
    assert 4125 <= fd[("SCRATCH", "EWMA")] <= 4125 + 600
    assert 3750 <= fd[("LOW_CONFIDENCE", "EWMA")] <= 3750 + 600
    # 감시 구간 알람 수가 baseline 알람 수보다 훨씬 많아야 한다
    assert (alarms["phase"] == "monitor").sum() > 5 * (alarms["phase"] == "baseline").sum()
    spc.plot_charts(charts, len(df) // 2, tmp_path / "demo.png", "t")
    assert (tmp_path / "demo.png").exists()
