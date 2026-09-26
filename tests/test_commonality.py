# tests/test_commonality.py
# commonality 분석(wm811k_commonality.py)의 코딩 오류를 잡는다. 심은 원인을 찾는지가 기준이며,
# 합성 이력이라 실제 팹에서의 탐지 성능 주장이 아니다.

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import wm811k_commonality as cm  # noqa: E402


def _analyse(pred, hist, pattern="EDGE_RING"):
    rates = cm.lot_rates(pred, pattern)
    T = cm.commonality(rates, hist)
    return rates, cm.confounding_check(rates, hist, T)


def test_bh_adjust_known_values():
    p = np.array([0.01, 0.04, 0.03, 0.2, np.nan])
    adj = cm.bh_adjust(p)
    assert np.isnan(adj[4])
    # m=4. 정렬 0.01, 0.03, 0.04, 0.2 → p·m/rank = 0.04, 0.06, 0.0533, 0.2
    # 뒤에서부터 누적 최소로 단조화 → 0.04, 0.0533, 0.0533, 0.2
    assert adj[0] == pytest.approx(0.04)
    assert adj[2] == pytest.approx(0.04 * 4 / 3)
    assert adj[1] == pytest.approx(0.04 * 4 / 3)
    assert adj[3] == pytest.approx(0.2)
    assert np.all(adj[~np.isnan(adj)] >= p[~np.isnan(p)])


def test_planted_cause_ranks_first_and_confound_is_flagged():
    pred, hist = cm.demo_data(seed=0)
    _, T = _analyse(pred, hist)
    top = T.iloc[0]
    assert (top["step"], top["tool"]) == cm.DEMO_CAUSE
    assert top["p_adj"] < 0.01
    conf = T.set_index(["step", "tool"]).loc[cm.DEMO_CONFOUND]
    assert conf["p_adj"] < 0.05                      # 교락 장비도 유의하게 잡히지만
    assert conf["confounded_with"] == f"{cm.DEMO_CAUSE[0]}/{cm.DEMO_CAUSE[1]}"   # 1위를 빼면 죽는다
    assert top["confounded_with"] == ""


def test_null_history_has_no_significant_tool():
    pred, hist = cm.demo_data(seed=3, effect=0.0)
    _, T = _analyse(pred, hist)
    assert (T["p_adj"].dropna() >= 0.05).all()


def test_lot_is_the_unit_not_wafer():
    """웨이퍼를 두 배로 복제해도 로트별 비율이 같으므로 p 값이 변하면 안 된다."""
    pred, hist = cm.demo_data(seed=0)
    _, T1 = _analyse(pred, hist)
    doubled = pd.concat([pred, pred], ignore_index=True)
    _, T2 = _analyse(doubled, hist)
    a = T1.set_index(["step", "tool"])["p"].dropna()
    b = T2.set_index(["step", "tool"])["p"].reindex(a.index)
    assert np.allclose(a.to_numpy(), b.to_numpy())


def test_small_tools_are_held_not_judged():
    pred, hist = cm.demo_data(seed=0)
    hist = hist.copy()
    few = hist["lot"].unique()[:3]
    hist.loc[hist["lot"].isin(few) & (hist["step"] == "CMP"), "tool"] = "CMP-99"
    _, T = _analyse(pred, hist)
    row = T.set_index(["step", "tool"]).loc[("CMP", "CMP-99")]
    assert row["n_lots"] == 3 and np.isnan(row["p"]) and np.isnan(row["p_adj"])


def test_run_writes_outputs(tmp_path):
    pred, hist = cm.demo_data(seed=0)
    T = cm.run(pred, hist, "EDGE_RING", cm.ALPHA, cm.MIN_LOTS, tmp_path, "t")
    assert not T.empty
    assert (tmp_path / "t_EDGE_RING.csv").exists() and (tmp_path / "t_EDGE_RING.png").exists()


def test_history_with_split_lot_is_rejected(tmp_path):
    h = pd.DataFrame({"lot": ["a", "a"], "step": ["ETCH", "ETCH"], "tool": ["E1", "E2"]})
    h.to_csv(tmp_path / "h.csv", index=False)
    with pytest.raises(SystemExit):
        cm.load_history(tmp_path / "h.csv")
