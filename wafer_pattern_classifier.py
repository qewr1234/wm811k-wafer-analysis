# wafer_pattern_classifier.py
# 웨이퍼 불량 패턴 규칙 기반 분류기
#
# 원본 대비 수정 사항
#   [버그] SCRATCH 미검출 — 중심을 지나는 선은 불량이 정반대 두 방향으로
#          퍼져 원형 평균이 상쇄된다. 각도를 2배로 접는 축(axial) 통계로 교체.
#   [버그] 오답에 최고 점수 — confidence = 1 - angle_concentration 이라
#          스크래치일 때 RANDOM 점수가 오히려 최대가 됐다.
#   [버그] fail_radius_std < 20 등 mm 절대값 임계 → 반경 비율로 전환.
#   [버그] wafer_radius 기본값 150 고정 → 미지정 시 데이터에서 추정.
#          WM-811K는 실제 mm 크기를 알 수 없어 자동 추정이 필수.
#   [제거] spatial_autocorr — 분류에 미사용이고, 10mm 격자에서는 값이
#          거의 항상 1-die/R 로 고정되어 판별력이 없었다. 또한 fail²
#          거리 행렬이라 다이 수가 늘면 메모리를 잡아먹는다.
#   [개명] confidence → score. 확률이 아니라 임의 공식의 휴리스틱 점수다.
#   [확장] EDGE_LOC, DONUT, LOC, NEAR_FULL 추가 (WM-811K 라벨 8종 대응).
#   [버그] CENTER 판정이 평균 반경 기반이라 외곽 이상치 몇 개로 뒤집혔다.
#          → 중앙값으로 교체 (CENTER, DONUT).
#   [버그] LOC이 전부 SCRATCH로 흡수됐다. 국소 클러스터도 축 집중도가
#          높기 때문. SCRATCH에 방향 집중도 상한을 추가해 구분.
#
# 주의: 아래 임계값은 합성 데이터 기준으로 정한 미교정(uncalibrated) 값이다.
#       실측에 적용할 때는 학습 분할에서만 교정하고 평가 분할은 건드리지 말 것.

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

Pattern = Literal[
    "CLEAN", "EDGE_RING", "EDGE_LOC", "CENTER",
    "DONUT", "SCRATCH", "LOC", "RANDOM", "NEAR_FULL",
]

ACTIONS: dict[str, str] = {
    "CLEAN": "조치 불필요. 추세 모니터링.",
    "EDGE_RING": "엣지 링 불량. 증착/식각 균일도 점검 및 Edge exclusion 기준 재검토.",
    "EDGE_LOC": "엣지 국소 불량. 척 엣지 접촉 상태, 가스 흐름 비대칭 점검.",
    "CENTER": "중심부 불량. 척 온도 프로파일, 중심 가스 플로우 점검.",
    "DONUT": "환형 불량. 회전 도포(스핀 코팅) 균일도, RF 정재파 확인.",
    "SCRATCH": "선형 스크래치. CMP 패드 상태, 슬러리 파티클 오염, 핸들링 확인.",
    "LOC": "국소 클러스터 불량. 해당 좌표 계측 및 파티클 소스 추적.",
    "RANDOM": "랜덤 불량. 파티클 카운트, 노광 오차 통계 확인.",
    "NEAR_FULL": "전면 불량. 공정 중단 여부 판단 및 장비 상태 긴급 점검.",
}

# ── 임계값 (모두 유효 반경 R 또는 비율 기준) ──
CLEAN_FAIL_FRAC = 0.02      # 불량 비율 이하면 CLEAN
NEAR_FULL_FRAC = 0.60       # 불량 비율 이상이면 NEAR_FULL
CENTER_R_MAX = 0.30         # 중심 불량: 평균 반경 / R
EDGE_R_MIN = 0.70           # 엣지 계열: 평균 반경 / R
RING_STD_MAX = 0.15         # 전둘레 링: 반경 표준편차 / R
RING_DIR_MAX = 0.45         # 전둘레 링: 방향 집중도 상한 (넘으면 국소)
DONUT_R_RANGE = (0.35, 0.70)
DONUT_STD_MAX = 0.16
SCRATCH_AXIAL_MIN = 0.50
SCRATCH_DIR_MAX = 0.35      # 중심을 지나는 선은 양방향 → 방향 집중도가 낮다
LOC_DIR_MIN = 0.50


@dataclass
class WaferPatternResult:
    pattern: Pattern
    score: float                    # 휴리스틱 점수 (확률 아님)
    yield_pct: float
    fail_count: int
    fail_fraction: float
    wafer_radius: float             # 사용된 정규화 반경
    fail_radius_mean: float
    fail_radius_std: float
    fail_radius_median: float
    r_mean_norm: float              # fail_radius_mean / wafer_radius
    r_med_norm: float               # 이상치에 강건 — CENTER/DONUT 판정에 사용
    r_std_norm: float
    dir_concentration: float        # 방향 집중도 (한쪽 치우침)
    axial_concentration: float      # 축 집중도 (선형성)
    recommended_action: str = field(default="")


# 합성 생성기의 defect_mode → 분류기가 내야 할 클래스
EXPECTED_BY_MODE: dict[str, str] = {
    "ring": "EDGE_RING", "center": "CENTER", "scratch": "SCRATCH",
    "random": "RANDOM", "donut": "DONUT", "edge_loc": "EDGE_LOC",
    "clean": "CLEAN",
}


def expected_patterns(defect_mode: str, noise: float = 0.0) -> frozenset[str]:
    """합성 웨이퍼에서 정답으로 인정할 클래스 집합.

    clean 모드에 noise를 주면 다이의 약 noise 비율이 FAIL로 뒤집힌다.
    뒤집힌 비율은 웨이퍼마다 CLEAN_FAIL_FRAC(2%) 근처에서 흔들리므로,
    규칙상 CLEAN과 RANDOM(산발 불량) 둘 다 그 맵을 옳게 읽은 것이다.
    CLEAN만 기대하면 자체 검증이 코딩 오류가 아닌 MISS를 낸다.
    """
    if defect_mode == "clean" and noise > 0:
        return frozenset({"CLEAN", "RANDOM"})
    return frozenset({EXPECTED_BY_MODE[defect_mode]})


def _circular_stats(angles_deg: np.ndarray) -> tuple[float, float]:
    """방향 집중도와 축 집중도를 반환.

    방향 집중도는 평균 벡터 길이. 한쪽으로 치우친 국소 불량에서 커진다.
    축 집중도는 각도를 2배로 접어 계산한다. θ와 θ+180°가 같은 값이 되므로
    중심을 지나는 선형 패턴에서도 상쇄되지 않는다.
    """
    a = np.radians(angles_deg)
    dir_c = float(np.hypot(np.mean(np.sin(a)), np.mean(np.cos(a))))
    axial_c = float(np.hypot(np.mean(np.sin(2 * a)), np.mean(np.cos(2 * a))))
    return dir_c, axial_c


def _infer_radius(df: pd.DataFrame) -> float:
    """정규화용 반경을 데이터에서 추정한다.

    WM-811K는 맵 크기가 329종이고 실제 mm 크기를 알 수 없으므로,
    관측된 최대 반경을 웨이퍼 반경의 대리값으로 쓴다.
    """
    r_max = float(df["radius"].max())
    return r_max if r_max > 0 else 1.0


def classify_wafer_pattern(
    df: pd.DataFrame,
    wafer_radius: float | None = None,
) -> WaferPatternResult:
    """웨이퍼 다이 DataFrame(die_x, die_y, radius, angle_deg, status)을
    분석해 불량 패턴을 분류한다.

    wafer_radius를 주지 않으면 데이터의 최대 반경으로 추정한다.
    모든 판정은 반경 비율로 이루어지므로 맵 크기에 무관하다.
    """
    total = len(df)
    if total == 0:
        raise ValueError("빈 DataFrame")

    R = wafer_radius if wafer_radius else _infer_radius(df)

    is_fail = (df["status"] == "FAIL").to_numpy()
    fail_count = int(is_fail.sum())
    fail_frac = fail_count / total
    yield_pct = (1.0 - fail_frac) * 100.0

    def result(pattern: Pattern, score: float, **kw) -> WaferPatternResult:
        base = dict(
            yield_pct=yield_pct, fail_count=fail_count, fail_fraction=fail_frac,
            wafer_radius=R, fail_radius_mean=0.0, fail_radius_std=0.0,
            fail_radius_median=0.0,
            r_mean_norm=0.0, r_med_norm=0.0, r_std_norm=0.0,
            dir_concentration=0.0, axial_concentration=0.0,
        )
        base.update(kw)
        return WaferPatternResult(
            pattern=pattern, score=float(np.clip(score, 0.0, 1.0)),
            recommended_action=ACTIONS[pattern], **base,
        )

    # ── 불량이 거의 없음 ──
    if fail_frac <= CLEAN_FAIL_FRAC:
        return result("CLEAN", 1.0 - fail_frac / max(CLEAN_FAIL_FRAC, 1e-9))

    r = df.loc[is_fail, "radius"].to_numpy()
    ang = df.loc[is_fail, "angle_deg"].to_numpy()

    r_mean = float(r.mean())
    # 중앙값은 소수의 외곽 이상치에 강건하다. 평균만 쓰면 중심 불량 웨이퍼에
    # 산발적 외곽 불량 몇 개가 붙는 것만으로 판정이 뒤집힌다.
    r_med = float(np.median(r))
    # ddof=0 — 불량 1개일 때 NaN이 나오지 않게 한다
    r_std = float(r.std(ddof=0))
    r_mean_n = r_mean / R
    r_med_n = r_med / R
    r_std_n = r_std / R
    dir_c, axial_c = _circular_stats(ang)

    stats = dict(
        fail_radius_mean=r_mean, fail_radius_std=r_std,
        fail_radius_median=r_med,
        r_mean_norm=r_mean_n, r_med_norm=r_med_n, r_std_norm=r_std_n,
        dir_concentration=dir_c, axial_concentration=axial_c,
    )

    # ── 판정 순서: 특이한 것부터 좁혀 들어간다 ──

    # 거의 전면 불량
    if fail_frac >= NEAR_FULL_FRAC:
        return result("NEAR_FULL", fail_frac, **stats)

    # 중심부 (방향성이 없어야 함)
    if r_med_n <= CENTER_R_MAX and dir_c < LOC_DIR_MIN:
        return result("CENTER", 1.0 - r_med_n / CENTER_R_MAX, **stats)

    # 엣지 계열 — 전둘레인지 국소인지로 갈린다
    if r_mean_n >= EDGE_R_MIN:
        if r_std_n <= RING_STD_MAX and dir_c <= RING_DIR_MAX:
            score = r_mean_n * (1.0 - r_std_n / max(RING_STD_MAX, 1e-9) * 0.5)
            return result("EDGE_RING", score, **stats)
        return result("EDGE_LOC", max(dir_c, r_mean_n), **stats)

    # 환형 — 중간 반경에 좁은 띠, 방향성 없음
    if (DONUT_R_RANGE[0] <= r_med_n <= DONUT_R_RANGE[1]
            and r_std_n <= DONUT_STD_MAX and dir_c <= RING_DIR_MAX):
        return result("DONUT", 1.0 - r_std_n / max(DONUT_STD_MAX, 1e-9), **stats)

    # 선형 스크래치 — 축 집중도는 높고 방향 집중도는 낮아야 한다.
    # 국소 클러스터(LOC)도 축 집중도가 높으므로 dir_c 상한이 없으면
    # LOC 전부가 SCRATCH로 흡수된다.
    if axial_c >= SCRATCH_AXIAL_MIN and dir_c <= SCRATCH_DIR_MAX:
        return result("SCRATCH", axial_c * (1.0 - dir_c), **stats)

    # 국소 클러스터
    if dir_c >= LOC_DIR_MIN:
        return result("LOC", dir_c, **stats)

    # 나머지
    return result("RANDOM", 1.0 - max(dir_c, axial_c), **stats)


# ──────────────────────────────────────────
if __name__ == "__main__":
    from wafer_map_visualizer import generate_sample_wafer_data

    # 합성 데이터로 로직 검증.
    # 생성기와 분류기가 같은 규칙을 공유하므로 전부 맞히는 것은 성능이 아니라
    # 코딩 오류가 없다는 확인까지다. 실제 정확도는 WM-811K로 재야 한다.
    modes = ["ring", "center", "scratch", "random", "donut", "edge_loc", "clean"]

    n_miss_total = 0
    for noise in (0.0, 0.03):
        print(f"\n{'=' * 62}")
        print(f"noise = {noise}")
        print(f"{'=' * 62}")
        n_ok = 0
        for mode in modes:
            df = generate_sample_wafer_data(defect_mode=mode, noise=noise)
            res = classify_wafer_pattern(df)
            exp = expected_patterns(mode, noise)
            ok = res.pattern in exp
            n_ok += ok
            print(f"\n[{mode.upper()}] → {res.pattern}  {'OK' if ok else 'MISS'}")
            print(f"  score {res.score:.3f} | 수율 {res.yield_pct:.1f}% | "
                  f"불량 {res.fail_count}개 ({res.fail_fraction:.1%})")
            print(f"  r_mean/R {res.r_mean_norm:.3f} | r_med/R {res.r_med_norm:.3f} | "
                  f"r_std/R {res.r_std_norm:.3f} | "
                  f"dir {res.dir_concentration:.3f} | axial {res.axial_concentration:.3f}")
            if not ok:
                print(f"  기대: {'/'.join(sorted(exp))}")
        print(f"\n일치 {n_ok}/{len(modes)}")
        n_miss_total += len(modes) - n_ok

    # 자체 검증이 깨지면 종료 코드로 알린다 (CI 등에서 잡을 수 있게)
    raise SystemExit(1 if n_miss_total else 0)
