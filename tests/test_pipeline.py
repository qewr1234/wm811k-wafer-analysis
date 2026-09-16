# tests/test_pipeline.py
# 합성 데이터로 특징 추출과 파이프라인의 코딩 오류를 잡는다. 성능 테스트가 아니다.
# 실행: pytest -q

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from synthetic_wm811k import df_to_wafermap, make_lswmd, make_wafermap  # noqa: E402
from wafer_map_visualizer import generate_sample_wafer_data, wafermap_to_df  # noqa: E402
from wafer_pattern_classifier import (  # noqa: E402
    EXPECTED_BY_MODE, classify_wafer_pattern, expected_patterns,
)
from wm811k_improve import ROBUST_FEATURES, robust_features  # noqa: E402
from wm811k_structural import STRUCT_FEATURES, structural_features  # noqa: E402
from wm811k_validate import NEW_FEATURES, largest_component_features  # noqa: E402


@pytest.mark.parametrize("mode", list(EXPECTED_BY_MODE))
@pytest.mark.parametrize("noise", [0.0, 0.03])
def test_classifier_matches_generator(mode, noise):
    df = generate_sample_wafer_data(defect_mode=mode, noise=noise)
    assert classify_wafer_pattern(df).pattern in expected_patterns(mode, noise)


@pytest.mark.parametrize("mode", ["ring", "center", "scratch", "donut", "edge_loc"])
def test_wafermap_roundtrip_keeps_pattern(mode):
    """DataFrame → 2D 배열 → DataFrame 을 거쳐도 같은 판정이 나와야 한다."""
    df = generate_sample_wafer_data(defect_mode=mode)
    arr = df_to_wafermap(df, 10.0)
    assert set(np.unique(arr)) <= {0, 1, 2}
    assert int((arr == 2).sum()) == int((df["status"] == "FAIL").sum())
    assert classify_wafer_pattern(wafermap_to_df(arr)).pattern == EXPECTED_BY_MODE[mode]


def _arr(mode, seed=0):
    return df_to_wafermap(generate_sample_wafer_data(defect_mode=mode, noise=0.02, seed=seed), 10.0)


def test_feature_keys_and_ranges():
    for mode in EXPECTED_BY_MODE:
        arr = _arr(mode)
        st, nf, rb = structural_features(arr), largest_component_features(arr), robust_features(arr)
        assert set(STRUCT_FEATURES) <= set(st)
        assert set(NEW_FEATURES) <= set(nf)
        assert set(ROBUST_FEATURES) <= set(rb)
        for k in ("largest_frac", "outer_cover", "outer_rate"):
            assert 0.0 <= st[k] <= 1.0, (mode, k, st[k])
        for k in ("isolated_frac", "sig_frac", "big_extent", "big_edge_touch", "second_frac"):
            assert 0.0 <= rb[k] <= 1.0, (mode, k, rb[k])
        assert all(np.isfinite(v) for d in (st, nf, rb) for v in d.values())


def test_no_fail_map_is_safe():
    arr = _arr("clean")
    arr[arr == 2] = 1
    assert structural_features(arr)["n_comp"] == 0
    assert largest_component_features(arr)["big_r"] == 0.0
    assert robust_features(arr)["isolated_frac"] == 0.0


def test_features_point_the_intended_way():
    """설계 단계에서 정한 방향이 합성 데이터에서 성립하는지. 크기가 아니라 부호만 본다."""
    ring, edge_loc, scratch, random_ = (_arr(m) for m in ("ring", "edge_loc", "scratch", "random"))
    rng = np.random.default_rng(0)
    loc = make_wafermap("loc", 1, rng)

    assert structural_features(ring)["outer_cover"] > structural_features(edge_loc)["outer_cover"]
    assert structural_features(scratch)["elongation"] > structural_features(loc)["elongation"]
    assert robust_features(random_)["isolated_frac"] > robust_features(scratch)["isolated_frac"]
    assert robust_features(edge_loc)["big_edge_touch"] > robust_features(loc)["big_edge_touch"]
    assert robust_features(scratch)["big_len"] > robust_features(loc)["big_len"]
    assert robust_features(loc)["big_extent"] > robust_features(scratch)["big_extent"]


def test_pipeline_end_to_end(tmp_path, monkeypatch):
    """prepare → 특징 추출 → 5회 분할 비교가 끝까지 도는지. 숫자는 보지 않는다."""
    import wm811k_evaluate as ev
    import wm811k_improve as imp

    src = tmp_path / "LSWMD.pkl"
    make_lswmd(n_lots=40, n_unlabeled=5, seed=1).to_pickle(src)

    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "prepare_wm811k.py"), str(src), str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    defects = tmp_path / "wm811k_defects.pkl"
    assert defects.exists()

    df = ev.load_data(defects)
    assert set(df["y_true"]) <= set(ev.CLASSES)
    res = ev.classify_all(df)
    m = ev.report(res, "synthetic")
    assert 0.0 <= m["macro_f1"] <= 1.0

    # 캐시와 결과 파일을 저장소가 아니라 임시 폴더에 쓰게 한다
    monkeypatch.setattr(imp, "CACHE3", tmp_path / "ext3.csv")
    monkeypatch.setattr(imp, "HERE", tmp_path)
    monkeypatch.setattr(imp, "SEEDS", [42, 0])
    imp.main(defects)
    assert (tmp_path / "wm811k_improve_results.csv").exists()
