# tests/test_detect.py
# 1단계 검출(wm811k_detect.py)의 코딩 오류를 잡는다. 합성 데이터라 성능 주장이 아니다.

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import wm811k_detect as det  # noqa: E402
from synthetic_wm811k import make_none_wafermap, make_wafermap  # noqa: E402


def test_extract_features_has_all_stage_columns():
    rng = np.random.default_rng(0)
    for arr in (make_none_wafermap(0, rng), make_wafermap("ring", 1, rng), make_wafermap("loc", 2, rng)):
        f = det.extract_features(arr)
        assert f is not None
        assert set(det.STAGE1_FEATURES) <= set(f)
        assert set(det.STAGE2_FEATURES) <= set(f)
        assert all(np.isfinite(v) for v in f.values())


def test_extract_features_rejects_tiny_or_bad_maps():
    assert det.extract_features(np.zeros((5, 5), dtype=np.uint8)) is None
    assert det.extract_features(np.ones((3, 3, 3), dtype=np.uint8)) is None


def test_none_wafer_looks_like_noise_not_pattern():
    """정상 웨이퍼는 고립 불량 비율이 높고 큰 성분 비율이 낮아야 한다. 부호만 본다."""
    rng = np.random.default_rng(1)
    none = det.extract_features(make_none_wafermap(5, rng))
    ring = det.extract_features(make_wafermap("ring", 6, rng))
    assert none["sig_frac"] < ring["sig_frac"]
    assert none["fail_nb_mean"] < ring["fail_nb_mean"]


def test_choose_threshold_meets_far_on_same_data():
    rng = np.random.default_rng(0)
    is_defect = np.r_[np.zeros(1000, bool), np.ones(300, bool)]
    p = np.r_[rng.beta(1.5, 6, 1000), rng.beta(6, 1.5, 300)]
    for far in (0.005, 0.02, 0.10):
        t = det.choose_threshold(p, is_defect, far)
        assert (p[~is_defect] > t).mean() <= far + 1e-9
        # 바로 아래 값으로 내리면 FAR 을 넘겨야 한다 (가장 느슨한 임계값인지 확인)
        below = p[~is_defect][p[~is_defect] < t].max()
        assert (p[~is_defect] > below).mean() > far - 1 / 1000


def test_choose_threshold_without_normals_falls_back():
    assert det.choose_threshold(np.array([0.9, 0.8]), np.array([True, True]), 0.02) == 0.5


def test_oof_probability_uses_lot_groups():
    """같은 로트가 train 과 val 양쪽에 있으면 안 된다. 로트별로 확률이 out-of-fold 인지 확인."""
    rng = np.random.default_rng(0)
    n = 400
    lots = np.repeat(np.arange(20), n // 20)
    X = rng.normal(size=(n, 4))
    y = X[:, 0] + rng.normal(scale=0.3, size=n) > 0
    p = det.oof_probability(X, y, lots, n_splits=4)
    assert p.shape == (n,) and np.all((p >= 0) & (p <= 1))
    # 신호가 있으니 OOF 확률도 라벨과 같은 방향이어야 한다
    assert p[y].mean() > p[~y].mean()


def test_recall_at_far_is_monotone():
    rng = np.random.default_rng(0)
    is_defect = np.r_[np.zeros(500, bool), np.ones(200, bool)]
    p = np.r_[rng.uniform(0, 0.7, 500), rng.uniform(0.3, 1.0, 200)]
    grid = np.logspace(-3, -0.5, 30)
    r = det.recall_at_far(p, is_defect, grid)
    assert np.all(np.diff(r) >= -1e-12) and 0 <= r[0] <= r[-1] <= 1
