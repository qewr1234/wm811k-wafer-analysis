# tests/test_features_snapshot.py
# 특징값 스냅샷 — README 수치 불변 규칙의 자동 감시
#
# README 의 실측 수치(macro-F1 0.907 ± 0.008 등)는 LSWMD.pkl 로 낸 것이라 CI 에서 재측정할
# 수 없다. 대신 특징 계산 코드(wafermap_to_df, classify_wafer_pattern 의 전역 통계,
# structural_features, largest_component_features, robust_features)가 합성 고정 맵 3장에서
# 내는 값을 소수 6자리로 고정해 둔다. 리팩터가 값을 바꾸면 이 테스트가 CI 에서 알린다.
#
# 'README 수치 불변 규칙': 아래 특징 함수·임계값 상수·CLASSES 순서를 바꾸는 변경은
# 실데이터로 results/ 를 다시 만들어 같은 커밋에 넣지 않는 한 금지다. 이 테스트가 깨졌다면
# (1) 생성기가 바뀐 것인지(맵 해시 단언이 먼저 깨진다) (2) 특징 코드가 바뀐 것인지 구분한 뒤,
# 후자라면 README 수치를 다시 재야 한다. 스냅샷 값을 고쳐서 통과시키는 것은 답이 아니다.
#
# 합성 맵의 라벨(ring/scratch/loc)은 값의 출처 표시일 뿐이다. 미교정 규칙이 그 맵을 무엇으로
# 판정하는지는 여기서 보지 않는다(합성 결과는 로직 확인이지 성능이 아니다).

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from synthetic_wm811k import make_wafermap  # noqa: E402
from wafer_map_visualizer import wafermap_to_df  # noqa: E402
from wafer_pattern_classifier import classify_wafer_pattern  # noqa: E402
from wm811k_improve import FEATS_ALL, ROBUST_FEATURES, robust_features  # noqa: E402
from wm811k_structural import (  # noqa: E402
    ALL_FEATURES, CLASSES, GLOBAL_FEATURES, STRUCT_FEATURES, structural_features,
)
from wm811k_validate import FEATS_B, NEW_FEATURES, largest_component_features  # noqa: E402

# 생성기 호출 순서가 값을 정한다: 하나의 rng 로 ring(11) -> scratch(12) -> loc(13) 순.
RNG_SEED = 20261015
MAPS = [("ring", 11), ("scratch", 12), ("loc", 13)]

# 맵 자체의 해시. 이것이 먼저 깨지면 특징 코드가 아니라 생성기(tests/synthetic_wm811k.py,
# wafer_map_visualizer.generate_sample_wafer_data)가 바뀐 것이다.
MAP_SHA1 = {
    "ring": "4b1c3b12e32a6c81e26abbd656ea3aec4c44d4c1",
    "scratch": "b3e456839558e0f4042b99eb77f7b577783a1480",
    "loc": "1d7452601172066ea94b5b3f9651159266627a8c",
}

# 전역 6 + 구조 11 + 위치 3 + 강건 8 = 28 (소수 6자리)
SNAPSHOT = {
    "ring": {
        "fail_frac": 0.304508, "r_mean": 0.885762, "r_med": 0.922911,
        "r_std": 0.146013, "dir_c": 0.012955, "axial_c": 0.016363,
        "n_comp": 39.0, "largest_frac": 0.893204, "elongation": 1.008345,
        "comp_size_mean": 10.564103, "outer_cover": 1.0, "outer_rate": 0.568598,
        "prof0": 0.072977, "prof1": 0.177512, "prof2": 0.225112,
        "prof3": 0.158601, "prof4": 1.967557,
        "big_r": 0.018022, "big_span": 358.025066, "big_r_min": 0.806226,
        "isolated_frac": 0.07767, "n_comp_sig": 1.0, "sig_frac": 0.893204,
        "second_frac": 0.005435, "fail_nb_mean": 5.135922, "big_extent": 0.218917,
        "big_len": 2.059437, "big_edge_touch": 0.296196,
    },
    "scratch": {
        "fail_frac": 0.119869, "r_mean": 0.551104, "r_med": 0.574367,
        "r_std": 0.281192, "dir_c": 0.097748, "axial_c": 0.57201,
        "n_comp": 19.0, "largest_frac": 0.753425, "elongation": 10.794995,
        "comp_size_mean": 3.842105, "outer_cover": 0.458333, "outer_rate": 0.075949,
        "prof0": 3.972603, "prof1": 1.349517, "prof2": 1.21661,
        "prof3": 0.855638, "prof4": 0.576873,
        "big_r": 0.092361, "big_span": 358.781125, "big_r_min": 0.0,
        "isolated_frac": 0.246575, "n_comp_sig": 1.0, "sig_frac": 0.753425,
        "second_frac": 0.018182, "fail_nb_mean": 3.232877, "big_extent": 0.146667,
        "big_len": 2.098748, "big_edge_touch": 0.054545,
    },
    "loc": {
        "fail_frac": 0.151079, "r_mean": 0.654934, "r_med": 0.669113,
        "r_std": 0.205873, "dir_c": 0.235769, "axial_c": 0.249492,
        "n_comp": 65.0, "largest_frac": 0.326531, "elongation": 1.139667,
        "comp_size_mean": 2.261538, "outer_cover": 0.916667, "outer_rate": 0.125,
        "prof0": 0.715573, "prof1": 0.674162, "prof2": 1.337893,
        "prof3": 1.383489, "prof4": 0.776308,
        "big_r": 0.623978, "big_span": 69.227745, "big_r_min": 0.470588,
        "isolated_frac": 0.278912, "n_comp_sig": 8.0, "sig_frac": 0.503401,
        "second_frac": 0.145833, "fail_nb_mean": 2.285714, "big_extent": 0.4,
        "big_len": 0.670116, "big_edge_touch": 0.0,
    },
}
TOL = 2e-6     # 소수 6자리 반올림 오차


def _fixed_maps() -> dict[str, np.ndarray]:
    rng = np.random.default_rng(RNG_SEED)
    return {mode: make_wafermap(mode, seed, rng) for mode, seed in MAPS}


def _all_features(arr: np.ndarray) -> dict[str, float]:
    r = classify_wafer_pattern(wafermap_to_df(arr))
    glob = {"fail_frac": r.fail_fraction, "r_mean": r.r_mean_norm, "r_med": r.r_med_norm,
            "r_std": r.r_std_norm, "dir_c": r.dir_concentration, "axial_c": r.axial_concentration}
    st = structural_features(arr)
    return {**glob, **{k: st[k] for k in STRUCT_FEATURES},
            **largest_component_features(arr), **robust_features(arr)}


def test_feature_name_sets_are_fixed():
    """특징 이름·개수·순서. 모델 입력 열 순서가 바뀌면 RF 결과가 달라질 수 있다."""
    assert GLOBAL_FEATURES == ["fail_frac", "r_mean", "r_med", "r_std", "dir_c", "axial_c"]
    assert len(STRUCT_FEATURES) == 11 and len(NEW_FEATURES) == 3 and len(ROBUST_FEATURES) == 8
    assert ALL_FEATURES == GLOBAL_FEATURES + STRUCT_FEATURES
    assert FEATS_B == ALL_FEATURES + NEW_FEATURES and len(FEATS_B) == 20
    assert set(FEATS_B) == {
        "fail_frac", "r_mean", "r_med", "r_std", "dir_c", "axial_c",
        "n_comp", "largest_frac", "elongation", "comp_size_mean", "outer_cover", "outer_rate",
        "prof0", "prof1", "prof2", "prof3", "prof4", "big_r", "big_span", "big_r_min",
    }
    assert set(ROBUST_FEATURES) == {"isolated_frac", "n_comp_sig", "sig_frac", "fail_nb_mean",
                                    "big_extent", "big_len", "big_edge_touch", "second_frac"}
    assert FEATS_ALL == FEATS_B + ROBUST_FEATURES and len(FEATS_ALL) == 28
    assert CLASSES == ["CENTER", "DONUT", "EDGE_LOC", "EDGE_RING",
                       "LOC", "NEAR_FULL", "RANDOM", "SCRATCH"]
    assert set(SNAPSHOT["ring"]) == set(FEATS_ALL)


def test_fixed_maps_unchanged():
    """스냅샷 입력 맵 자체가 같은지. 여기서 깨지면 특징 코드가 아니라 생성기가 바뀐 것."""
    for mode, arr in _fixed_maps().items():
        h = hashlib.sha1(np.ascontiguousarray(arr, dtype=np.uint8).tobytes()).hexdigest()
        assert h == MAP_SHA1[mode], (
            f"{mode}: 합성 맵이 달라졌다 (생성기 변경). 특징 스냅샷 비교는 의미가 없으니 "
            f"생성기 변경을 먼저 되돌리거나, 의도한 변경이면 MAP_SHA1 과 SNAPSHOT 을 함께 갱신하라.")


@pytest.mark.parametrize("mode", [m for m, _ in MAPS])
def test_feature_values_snapshot(mode):
    """전역 6 + 구조 11 + 위치 3 + 강건 8 특징값이 소수 6자리에서 고정값과 같다.

    깨졌다면 README 수치 불변 규칙에 따라 (a) 변경을 되돌리거나 (b) 실데이터로 results/ 를
    다시 만들고 README 수치와 이 스냅샷을 같은 커밋에서 갱신해야 한다.
    """
    arr = _fixed_maps()[mode]
    got = _all_features(arr)
    exp = SNAPSHOT[mode]
    assert set(got) == set(exp)
    diffs = {k: (round(float(got[k]), 6), exp[k]) for k in exp
             if abs(float(got[k]) - exp[k]) > TOL}
    assert not diffs, f"{mode}: 특징값이 스냅샷과 다르다 (got, expected): {diffs}"
