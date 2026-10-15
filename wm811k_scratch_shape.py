# wm811k_scratch_shape.py
# 스크래치 모양 판별 - 최대 성분에 직선과 원을 적합해 직선 / 호(弧) / 애매 / 너무 짧음 을 가른다
#
# 배경
#   docs/defect_signatures.md SCRATCH 행은 "선의 모양이 원인 구분의 단서"라고 적는다:
#   웨이퍼와 패드가 모두 회전하는 CMP 에서 패드에 박힌 입자가 남기는 궤적은 흔히 호(弧) 모양이고,
#   반송 중 끌림(EFEM 로봇·엔드이펙터·FOUP/카세트 슬롯 - 모든 TEL 장비에 공통인 반송계)은 직선인
#   경우가 많다. 그런데 분류기의 특징은 세장비(elongation)·주축 길이(big_len)뿐이라 모양을
#   구분하지 못했다. 이 모듈은 그 구분을 기하 적합으로 계산한다.
#
#   '호 = CMP(타사 장비), 직선 = 반송계(TEL 공통)' 는 경험칙이지 절대 규칙이 아니다. 인과를
#   적은 공개 자료를 찾지 못했고, 2차 자료는 scratch 를 '방향·위치 무관한 직선 또는 곡선'으로만
#   정의한다. 더 확실한 구분은 로트 안 재현성이다: 핸들링 접촉은 노치 기준 같은 방향·위치에
#   반복되고(고정 접촉점), CMP 입자는 매번 다르다. lot_scratch_summary 가 그 재현성을 판정한다.
#   TEL 은 CMP 장비를 만들지 않으므로 호 판정은 '타사 장비 인계' 후보이고, 직선 + 로트 내 재현은
#   TEL 장비 반송계(로봇 티칭, 엔드이펙터 패드, 슬롯) 점검 후보다.
#
# 무엇을 하나
#   fit_line(xy)            PCA. 부축 표준편차 sigma(직선에서의 흩어짐), 주축 각도 angle_deg (-90, 90].
#   fit_circle_kasa(xy)     Kasa 대수 원 적합 (x^2 + y^2 + D x + E y + F = 0 최소제곱).
#                           sigma(반경 잔차 RMS), 중심 cx, cy, 반경 r. 단위는 입력 좌표 그대로.
#   scratch_shape(arr)      최대 성분(8-이웃)을 단위원 좌표(반경 1 = 다이 bbox 반폭)로 바꿔 두 적합을
#                           비교한다. ratio = sigma_line / sigma_circle.
#                             길이 < min_len_frac * 반경 또는 다이 < 6     -> too_short
#                             ratio >= 2 이고 0.3 <= r_circle <= 5         -> arc
#                             ratio <= 0.5                                 -> line
#                             그 사이                                       -> ambiguous
#                           line_angle_deg(노치 기준, 축 각도), arc_r_norm, arc_center_outside
#                           (원 중심이 웨이퍼 밖 = 패드 회전축이 캐리어 바깥에 있는 CMP 흔적과 부합),
#                           arc_center_deg, length_norm, n 도 돌려준다.
#   lot_scratch_summary(df) 로트별 n_scratch, n_line, n_arc, angle_consistency(직선 각도의 축 집중도 =
#                           각도를 2배로 접은 Rayleigh r_bar), p_axial, verdict:
#                             n_scratch < min_n                                   -> insufficient
#                             n_line >= min_n 이고 consistency >= 0.7 이고 p < 0.05 -> reproducible_line
#                                                                                   (고정 접촉 의심)
#                             그 외                                               -> random
#
# 왜 이 적합인가
#   두께 1~2다이의 짧은 선은 직선·원 둘 다 잘 맞아 구분이 안 되므로 길이 하한(too_short)을 둔다.
#   Kasa 적합은 노이즈가 있으면 반경을 작게 추정하는 편향이 있지만, 여기서는 '어느 모델의 잔차가
#   작은가'의 비교에만 쓰므로 반경의 정밀도는 중요하지 않다. 비교의 안전 여유(2배 / 0.5배)가 그
#   편향을 흡수한다.
#
# 한계
#   - WM-811K SCRATCH 1,193장 / 로트당 평균 3.2장이라 로트 재현성 판정은 대부분 insufficient 다.
#     --demo 와 tests/ 의 합성 결과는 로직 확인이지 성능이 아니다.
#   - 최대 성분 하나만 본다. 스크래치가 산발 불량에 끊겨 여러 성분이 되면 가장 큰 조각만 적합한다.
#   - 노치 방향(기본 -90도)은 wm811k_azimuth 와 같은 가정이다. 같은 로트 안의 상대 각도 비교는
#     이 가정과 무관하다.
#   - 분류는 입력(y_pred 또는 y_true)을 믿는다. SCRATCH 가 아닌 웨이퍼는 보지 않는다.
#
# 사용법
#   python wm811k_scratch_shape.py --demo                                 # 합성 직선/호/덩어리
#   python wm811k_scratch_shape.py data/wm811k_defects.pkl --pred test_predictions.csv
#   python wm811k_scratch_shape.py records.pkl --notch-deg -90 --output scratch_out
#   입력 df 는 waferMap, lot, (y_pred 또는 y_true) 열. 출력: scratch_wafers.csv, scratch_lots.csv,
#   scratch_fits.png (적합 결과 겹쳐 그린 맵, 최대 8장)

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from wm811k_azimuth import (
    DEFAULT_NOTCH_DEG, label_column, largest_component_xy, load_records,
    notch_relative_angle, rayleigh_test,
)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DEFAULT_MIN_LEN_FRAC = 0.4      # 최대 성분 주축 길이 / 반경. 미만이면 too_short
MIN_POINTS = 6                  # 적합에 필요한 최소 다이 수
RATIO_ARC = 2.0                 # sigma_line / sigma_circle 이 이 이상이면 호 후보
RATIO_LINE = 0.5                # 이 이하이면 직선
ARC_R_RANGE = (0.3, 5.0)        # 호로 인정하는 원 반경 범위 (웨이퍼 반경 배수)
DEFAULT_MIN_N = 3
CONSISTENCY_FIXED = 0.7
P_ALPHA = 0.05
SHAPES = ("line", "arc", "ambiguous", "too_short")


# ──────────────────────────────────────────
# 1. 적합
# ──────────────────────────────────────────
def fit_line(xy: np.ndarray) -> dict:
    """PCA 직선 적합. xy 는 (n, 2), x 오른쪽 / y 위.

    Returns
    -------
    dict(sigma, angle_deg)
        sigma      부축(주축에 수직) 표준편차 = 직선 모델의 잔차 RMS.
        angle_deg  주축 각도, (-90, 90] (선은 방향이 없으므로 180도 접음). n < 2 면 NaN.
    """
    p = np.asarray(xy, dtype=float)
    if len(p) < 2:
        return {"sigma": 0.0, "angle_deg": float("nan")}
    u = p - p.mean(axis=0)
    cov = (u.T @ u) / len(u)
    ev, evec = np.linalg.eigh(cov)
    major = evec[:, 1]
    ang = np.degrees(np.arctan2(major[1], major[0]))
    ang = ((ang + 90.0) % 180.0) - 90.0          # [-90, 90)
    if ang == -90.0:
        ang = 90.0
    return {"sigma": float(np.sqrt(max(ev[0], 0.0))), "angle_deg": float(ang)}


def fit_circle_kasa(xy: np.ndarray) -> dict:
    """Kasa 대수 원 적합: x^2 + y^2 + D x + E y + F = 0 을 최소제곱으로.

    Returns
    -------
    dict(sigma, cx, cy, r)
        sigma  반경 잔차 |dist - r| 의 RMS. 적합 불가(점 3개 미만, 공선)면 inf.
        cx, cy, r  원 중심과 반경(입력 좌표 단위). 적합 불가면 NaN / inf.
    """
    p = np.asarray(xy, dtype=float)
    bad = {"sigma": float("inf"), "cx": float("nan"), "cy": float("nan"), "r": float("inf")}
    if len(p) < 3:
        return bad
    x, y = p[:, 0], p[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = -(x ** 2 + y ** 2)
    sol, _, rank, _ = np.linalg.lstsq(A, b, rcond=None)
    if rank < 3:
        return bad
    D, E, F = sol
    cx, cy = -D / 2.0, -E / 2.0
    r2 = cx ** 2 + cy ** 2 - F
    if not np.isfinite(r2) or r2 <= 0:
        return bad
    r = float(np.sqrt(r2))
    res = np.hypot(x - cx, y - cy) - r
    return {"sigma": float(np.sqrt(np.mean(res ** 2))), "cx": float(cx), "cy": float(cy), "r": r}


# ──────────────────────────────────────────
# 2. 맵 한 장의 모양 판정
# ──────────────────────────────────────────
def scratch_shape(arr: np.ndarray, min_len_frac: float = DEFAULT_MIN_LEN_FRAC,
                  notch_deg: float = DEFAULT_NOTCH_DEG) -> dict:
    """최대 연결 성분의 모양: line / arc / ambiguous / too_short.

    Returns
    -------
    dict
        shape               SHAPES 중 하나.
        ratio               sigma_line / sigma_circle. 클수록 원이 더 잘 맞는다. too_short 면 NaN.
        line_angle_deg      직선 주축 각도, 노치 기준 (-90, 90]. 방향 없는 축 각도.
        arc_r_norm          원 적합 반경 / 웨이퍼 반경(단위원이라 반경 1).
        arc_center_outside  원 중심이 웨이퍼 밖(|c| > 1)인가. 패드 회전축이 캐리어 밖에 있는
                            CMP 궤적이면 참인 경우가 많다 (경험칙).
        arc_center_deg      원 중심의 방위각, 노치 기준 (-180, 180]. 적합 불가면 NaN.
        length_norm         주축 사영 범위 / 웨이퍼 반경 (지름 전체를 지나면 약 2).
        n                   성분 다이 수.
        sigma_line, sigma_circle  두 모델의 잔차 RMS.
    """
    xy = largest_component_xy(arr)
    n = int(len(xy))
    out = {"shape": "too_short", "ratio": float("nan"), "line_angle_deg": float("nan"),
           "arc_r_norm": float("nan"), "arc_center_outside": False, "arc_center_deg": float("nan"),
           "length_norm": 0.0, "n": n, "sigma_line": float("nan"), "sigma_circle": float("nan")}
    if n == 0:
        return out
    ln = fit_line(xy)
    if n >= 2:
        u = xy - xy.mean(axis=0)
        major = np.array([np.cos(np.radians(ln["angle_deg"])), np.sin(np.radians(ln["angle_deg"]))])
        proj = u @ major
        out["length_norm"] = float(proj.max() - proj.min())
    if np.isfinite(ln["angle_deg"]):
        # 축 각도는 180도 주기: 노치 기준으로 옮긴 뒤 다시 (-90, 90] 로 접는다
        a = notch_relative_angle(ln["angle_deg"], notch_deg)
        a = ((a + 90.0) % 180.0) - 90.0
        out["line_angle_deg"] = 90.0 if a == -90.0 else float(a)
    out["sigma_line"] = ln["sigma"]
    if n < MIN_POINTS or out["length_norm"] < min_len_frac:
        return out

    ci = fit_circle_kasa(xy)
    out["sigma_circle"] = ci["sigma"]
    if np.isfinite(ci["r"]):
        out["arc_r_norm"] = ci["r"]
        out["arc_center_outside"] = bool(np.hypot(ci["cx"], ci["cy"]) > 1.0)
        out["arc_center_deg"] = notch_relative_angle(
            np.degrees(np.arctan2(ci["cy"], ci["cx"])), notch_deg)

    sl, sc = ln["sigma"], ci["sigma"]
    if not np.isfinite(sc):                     # 원 적합 불가 (완전 공선) -> 직선
        ratio = 0.0
    elif sl < 1e-9 and sc < 1e-9:
        ratio = 1.0
    else:
        ratio = sl / max(sc, 1e-9)
    out["ratio"] = float(ratio)

    if ratio >= RATIO_ARC and ARC_R_RANGE[0] <= out["arc_r_norm"] <= ARC_R_RANGE[1]:
        out["shape"] = "arc"
    elif ratio <= RATIO_LINE:
        out["shape"] = "line"
    else:
        out["shape"] = "ambiguous"
    return out


# ──────────────────────────────────────────
# 3. 로트 요약
# ──────────────────────────────────────────
def wafer_scratch_table(df: pd.DataFrame, notch_deg: float = DEFAULT_NOTCH_DEG,
                        min_len_frac: float = DEFAULT_MIN_LEN_FRAC,
                        scratch_label: str = "SCRATCH") -> pd.DataFrame:
    """SCRATCH 로 판정된 웨이퍼마다 scratch_shape 결과를 모은 표.

    열: lot, wafer_index, shape, ratio, line_angle_deg, arc_r_norm, arc_center_outside,
        arc_center_deg, length_norm, n.
    """
    col = label_column(df)
    sub = df[df[col] == scratch_label]
    rows = []
    for _, r in sub.iterrows():
        s = scratch_shape(np.asarray(r["waferMap"]), min_len_frac, notch_deg)
        rows.append({"lot": str(r["lot"]), "wafer_index": r.get("wafer_index", np.nan),
                     **{k: s[k] for k in ("shape", "ratio", "line_angle_deg", "arc_r_norm",
                                          "arc_center_outside", "arc_center_deg", "length_norm", "n")}})
    cols = ["lot", "wafer_index", "shape", "ratio", "line_angle_deg", "arc_r_norm",
            "arc_center_outside", "arc_center_deg", "length_norm", "n"]
    return pd.DataFrame(rows, columns=cols)


def axial_consistency(angles_deg, n_perm: int = 2000, seed: int = 0) -> dict:
    """축 각도(180도 주기)의 집중도. 각도를 2배로 접어 Rayleigh 를 돌린다.

    Returns dict(n, r_bar, mean_axis_deg, p). mean_axis_deg 는 (-90, 90].
    """
    a = np.asarray(angles_deg, dtype=float).ravel()
    a = a[np.isfinite(a)]
    rt = rayleigh_test(2.0 * a, n_perm=n_perm, seed=seed)
    mean_axis = rt["mean_deg"] / 2.0 if np.isfinite(rt["mean_deg"]) else float("nan")
    return {"n": rt["n"], "r_bar": rt["r_bar"], "mean_axis_deg": mean_axis, "p": rt["p"]}


def lot_scratch_summary(df: pd.DataFrame, notch_deg: float = DEFAULT_NOTCH_DEG,
                        min_n: int = DEFAULT_MIN_N, min_len_frac: float = DEFAULT_MIN_LEN_FRAC,
                        n_perm: int = 2000, seed: int = 0) -> pd.DataFrame:
    """로트별 스크래치 모양 집계와 재현성 판정.

    Returns
    -------
    DataFrame(lot, n_scratch, n_line, n_arc, n_ambiguous, n_too_short, angle_consistency,
              mean_axis_deg, p_axial, verdict)
        angle_consistency  직선 웨이퍼들의 축 각도 집중도 (2배 접은 Rayleigh r_bar). 직선 < 2장이면 NaN.
        verdict            reproducible_line(노치 기준 같은 방향의 직선이 반복 - 고정 접촉점 의심:
                           로봇 엔드이펙터·슬롯) / random(모양·방향이 제각각 - 산발 입자·CMP 쪽) /
                           insufficient(n_scratch < min_n).
    """
    tab = wafer_scratch_table(df, notch_deg, min_len_frac)
    rows = []
    for lot, g in tab.groupby("lot", sort=True):
        n = int(len(g))
        cnt = g["shape"].value_counts()
        lines = g.loc[g["shape"] == "line", "line_angle_deg"].to_numpy()
        n_line = int(cnt.get("line", 0))
        if n_line >= 2:
            ac = axial_consistency(lines, n_perm=n_perm, seed=seed)
            cons, mean_axis, p = ac["r_bar"], ac["mean_axis_deg"], ac["p"]
        else:
            cons, mean_axis, p = float("nan"), (float(lines[0]) if n_line == 1 else float("nan")), float("nan")
        if n < min_n:
            verdict = "insufficient"
        elif n_line >= min_n and np.isfinite(cons) and cons >= CONSISTENCY_FIXED and p < P_ALPHA:
            verdict = "reproducible_line"
        else:
            verdict = "random"
        rows.append({"lot": lot, "n_scratch": n, "n_line": n_line, "n_arc": int(cnt.get("arc", 0)),
                     "n_ambiguous": int(cnt.get("ambiguous", 0)),
                     "n_too_short": int(cnt.get("too_short", 0)),
                     "angle_consistency": cons, "mean_axis_deg": mean_axis, "p_axial": p,
                     "verdict": verdict})
    cols = ["lot", "n_scratch", "n_line", "n_arc", "n_ambiguous", "n_too_short",
            "angle_consistency", "mean_axis_deg", "p_axial", "verdict"]
    return pd.DataFrame(rows, columns=cols)


# ──────────────────────────────────────────
# 4. 그림
# ──────────────────────────────────────────
def plot_scratch_fit(arr: np.ndarray, ax=None, title: str = "", notch_deg: float = DEFAULT_NOTCH_DEG,
                     min_len_frac: float = DEFAULT_MIN_LEN_FRAC):
    """맵 위에 최대 성분(노란색)과 적합한 직선·원을 겹쳐 그린다. 판정 확인용."""
    if ax is None:
        _, ax = plt.subplots(figsize=(4, 4))
    a = np.asarray(arr)
    from wm811k_azimuth import wafer_frame
    img = np.full(a.shape + (3,), 1.0)
    img[a == 1] = (0.80, 0.90, 0.80)
    img[a == 2] = (0.90, 0.35, 0.30)
    xy = largest_component_xy(a)
    s = scratch_shape(a, min_len_frac, notch_deg)
    ax.imshow(img, interpolation="nearest")
    if len(xy):
        cy, cx, ry, rx = wafer_frame(a)
        px, py = xy[:, 0] * rx + cx, -xy[:, 1] * ry + cy
        ax.scatter(px, py, s=6, c="#FFC107", marker="s", linewidths=0)
        if s["shape"] != "too_short":
            ln = fit_line(xy)
            t = np.linspace(-1.6, 1.6, 50)
            mx, my = xy.mean(axis=0)
            dx, dy = np.cos(np.radians(ln["angle_deg"])), np.sin(np.radians(ln["angle_deg"]))
            ax.plot((mx + t * dx) * rx + cx, -(my + t * dy) * ry + cy, "-", color="#1565C0", lw=1)
            ci = fit_circle_kasa(xy)
            if np.isfinite(ci["r"]):
                th = np.linspace(0, 2 * np.pi, 200)
                ax.plot((ci["cx"] + ci["r"] * np.cos(th)) * rx + cx,
                        -(ci["cy"] + ci["r"] * np.sin(th)) * ry + cy, "--", color="#2E7D32", lw=1)
        ax.set_xlim(-0.5, a.shape[1] - 0.5)
        ax.set_ylim(a.shape[0] - 0.5, -0.5)
    sub = f"{s['shape']}  ratio={s['ratio']:.2f}  len={s['length_norm']:.2f}R  n={s['n']}"
    if s["shape"] == "line":
        sub += f"\nangle={s['line_angle_deg']:.0f}deg (notch ref)"
    elif s["shape"] == "arc":
        sub += f"\nr={s['arc_r_norm']:.2f}R  center {'outside' if s['arc_center_outside'] else 'inside'}"
    ax.set_title(f"{title}\n{sub}" if title else sub, fontsize=8)
    ax.set_xticks([]); ax.set_yticks([])
    return ax


# ──────────────────────────────────────────
# 5. 합성 데모 (로직 확인용 - 성능 아님)
# ──────────────────────────────────────────
def synthetic_scratch_map(kind: str, seed: int, angle_deg: float = 30.0, width_mm: float = 6.0,
                          noise: float = 0.02, diameter_mm: float = 300.0, die_mm: float = 10.0,
                          arc_center=(170.0, -55.0), arc_r: float = 180.0) -> np.ndarray:
    """합성 스크래치 맵. kind: 'line'(중심을 지나는 직선, angle_deg 는 맵 좌표 +x 기준),
    'arc'(중심이 웨이퍼 밖인 원의 일부, 폭 1~2다이), 'blob'(덩어리). noise 는 다이 뒤집기 확률.

    폭 width_mm 는 선 중심선에서의 거리 상한(다이 10mm 에서 6 -> 폭 1~2다이). 원 반경 180mm 는
    웨이퍼 반경의 약 1.2배. 반경이 커질수록(곡률이 작을수록) 직선과의 잔차 비가 2 근처로 내려와
    ambiguous 가 늘어난다 - 그것이 이 판별의 한계다 (r=210mm, 폭 8mm, 노이즈 0.02 에서 비 1.9 관측)."""
    sys.path.insert(0, str(HERE / "tests"))
    from synthetic_wm811k import df_to_wafermap  # noqa: E402
    from wafer_map_visualizer import generate_sample_wafer_data  # noqa: E402

    df = generate_sample_wafer_data(wafer_diameter_mm=diameter_mm, die_size_mm=die_mm,
                                    defect_mode="clean", noise=0.0, seed=seed)
    x, y = df["die_x"].to_numpy(), df["die_y"].to_numpy()
    R = float(df["radius"].max())
    if kind == "line":
        th = np.radians(angle_deg)
        fail = np.abs(-np.sin(th) * x + np.cos(th) * y) <= width_mm
    elif kind == "arc":
        cx, cy = arc_center
        fail = (np.abs(np.hypot(x - cx, y - cy) - arc_r) <= width_mm) & (y > -0.8 * R)
    elif kind == "blob":
        fail = np.hypot(x - 0.4 * R, y - 0.2 * R) <= 0.15 * R
    else:
        raise ValueError(f"kind must be line/arc/blob, got {kind!r}")
    rng = np.random.default_rng(seed)
    flip = rng.random(len(df)) < noise
    fail = np.where(flip, ~fail, fail)
    df["status"] = np.where(fail, "FAIL", "PASS")
    return df_to_wafermap(df, die_mm)


def demo_records(seed: int = 0) -> pd.DataFrame:
    """합성 로트 4개 (waferMap, lot, wafer_index, y_true=SCRATCH).

    L  직선 5장, 같은 각도 30도                        -> reproducible_line 기대
    M  직선 5장, 각도를 36도 간격으로 고르게 벌림      -> random 기대 (축 집중도 ~ 0)
    N  호 4장 (원 중심 방위를 바꿔 가며)              -> random 기대 (n_line=0)
    S  직선 1장 + 호 1장                               -> insufficient 기대
    M 의 각도를 난수로 뽑지 않는 이유: n=5 에서는 균일 난수도 3~4% 확률로 축 집중도가 0.7 을
    넘어 reproducible_line 이 나올 수 있다 (seed 0 에서 실제로 관측). 데모는 결정적으로 둔다.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for w in range(5):
        rows.append({"waferMap": synthetic_scratch_map("line", 500 + w, angle_deg=30.0,
                                                       noise=float(rng.uniform(0.01, 0.03))),
                     "lot": "demoL", "wafer_index": w, "y_true": "SCRATCH"})
    for w, ang in enumerate((-72.0, -36.0, 0.0, 36.0, 72.0)):
        rows.append({"waferMap": synthetic_scratch_map("line", 600 + w, angle_deg=ang,
                                                       noise=float(rng.uniform(0.01, 0.03))),
                     "lot": "demoM", "wafer_index": w, "y_true": "SCRATCH"})
    for w in range(4):
        ang = rng.uniform(0, 2 * np.pi)
        c = (float(180 * np.cos(ang)), float(180 * np.sin(ang)))
        rows.append({"waferMap": synthetic_scratch_map("arc", 700 + w, arc_center=c, arc_r=180.0,
                                                       noise=float(rng.uniform(0.01, 0.03))),
                     "lot": "demoN", "wafer_index": w, "y_true": "SCRATCH"})
    rows.append({"waferMap": synthetic_scratch_map("line", 800, angle_deg=-45.0), "lot": "demoS",
                 "wafer_index": 0, "y_true": "SCRATCH"})
    rows.append({"waferMap": synthetic_scratch_map("arc", 801), "lot": "demoS",
                 "wafer_index": 1, "y_true": "SCRATCH"})
    return pd.DataFrame(rows)


# ──────────────────────────────────────────
# 6. CLI
# ──────────────────────────────────────────
def run(df: pd.DataFrame, out_dir: Path, notch_deg: float = DEFAULT_NOTCH_DEG,
        min_n: int = DEFAULT_MIN_N, min_len_frac: float = DEFAULT_MIN_LEN_FRAC,
        max_fig: int = 8, label: str = "") -> dict:
    """표 2개 + 적합 그림을 out_dir 에 저장하고 요약 dict 를 돌려준다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    col = label_column(df)
    wafers = wafer_scratch_table(df, notch_deg, min_len_frac)
    lots = lot_scratch_summary(df, notch_deg, min_n, min_len_frac)
    wafers.to_csv(out_dir / "scratch_wafers.csv", index=False, encoding="utf-8-sig")
    lots.to_csv(out_dir / "scratch_lots.csv", index=False, encoding="utf-8-sig")

    print(f"\n{'=' * 74}\n스크래치 모양 판별{(' - ' + label) if label else ''}\n{'=' * 74}")
    print(f"  라벨 열: {col}   min_n: {min_n}   min_len_frac: {min_len_frac}   "
          f"노치 기준 각도 (가정: notch_deg={notch_deg:g})")
    vc = wafers["shape"].value_counts()
    print(f"  SCRATCH 웨이퍼 {len(wafers)}장: " + ", ".join(f"{k} {int(vc.get(k, 0))}" for k in SHAPES))
    lv = lots["verdict"].value_counts()
    print(f"  로트 {len(lots)}개 판정: " + ", ".join(
        f"{k} {int(lv.get(k, 0))}" for k in ("reproducible_line", "random", "insufficient")))
    if len(lots):
        show = lots.sort_values(["verdict", "n_scratch"], ascending=[False, False]).head(20)
        print("\n  " + show.to_string(index=False, float_format=lambda v: f"{v:.3f}").replace("\n", "\n  "))
    print("\n  판정 읽기: reproducible_line = 노치 기준 같은 방향의 직선이 로트 안에서 반복 -> 고정 접촉점"
          "(EFEM 로봇 엔드이펙터·FOUP/카세트 슬롯, TEL 장비 공통 반송계) 점검, 로봇 티칭·슬롯 맵 로그와 대조."
          "\n            arc 가 많으면 CMP(타사 장비) 인계 후보 - 경험칙이며 절대 규칙이 아니다."
          "\n            random = 모양·방향 제각각(산발 입자·이벤트). insufficient = 로트 안 장수 부족.")

    # 그림: 모양별로 골고루 최대 max_fig 장
    sub = df[df[col] == "SCRATCH"].reset_index(drop=True)
    pick = []
    for shp in SHAPES:
        idx = wafers.index[wafers["shape"] == shp].tolist()
        pick += idx[: max(1, max_fig // len(SHAPES))]
    pick = pick[:max_fig]
    if pick:
        n = len(pick)
        ncol = min(4, n)
        nrow = int(np.ceil(n / ncol))
        fig, axes = plt.subplots(nrow, ncol, figsize=(3.4 * ncol, 4.3 * nrow))
        axes = np.atleast_1d(axes).ravel()
        for ax, i in zip(axes, pick):
            r = wafers.iloc[i]
            plot_scratch_fit(np.asarray(sub.iloc[i]["waferMap"]), ax,
                             title=f"lot {r['lot']} w{r['wafer_index']}", notch_deg=notch_deg,
                             min_len_frac=min_len_frac)
        for ax in axes[n:]:
            ax.axis("off")
        fig.suptitle("Largest component (yellow), PCA line (blue), Kasa circle (green dashed)", fontsize=9)
        fig.tight_layout()
        fig.savefig(out_dir / "scratch_fits.png", dpi=110)
        plt.close(fig)
    print(f"\n  저장: {out_dir / 'scratch_wafers.csv'}, {out_dir / 'scratch_lots.csv'}"
          + (f", {out_dir / 'scratch_fits.png'}" if pick else ""))
    return {"wafers": wafers, "lots": lots}


def _cli(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="SCRATCH 최대 성분에 직선·원을 적합해 직선/호를 가르고, 로트 안에서 직선 방향이 "
                    "재현되는지(고정 접촉) 판정한다.")
    ap.add_argument("path", nargs="?", type=Path, default=None,
                    help="records.pkl 또는 wm811k_defects.pkl (waferMap, lotName, failureType)")
    ap.add_argument("--pred", type=Path, default=None,
                    help="예측 CSV (lot, y_pred, 선택 wafer_index). 있으면 y_true 대신 y_pred 로 판정")
    ap.add_argument("--min-n", type=int, default=DEFAULT_MIN_N,
                    help=f"로트 판정에 필요한 최소 SCRATCH 장수 (기본 {DEFAULT_MIN_N})")
    ap.add_argument("--min-len-frac", type=float, default=DEFAULT_MIN_LEN_FRAC,
                    help=f"too_short 기준: 주축 길이 / 반경 (기본 {DEFAULT_MIN_LEN_FRAC})")
    ap.add_argument("--notch-deg", type=float, default=DEFAULT_NOTCH_DEG,
                    help=f"맵 좌표계에서 노치 방향(도). 기본 {DEFAULT_NOTCH_DEG:g} 는 가정이다")
    ap.add_argument("--output", type=Path, default=None,
                    help="출력 폴더 (기본: HERE/scratch_out, --demo 는 HERE/scratch_demo)")
    ap.add_argument("--demo", action="store_true", help="합성 직선/호/덩어리로 판정 로직 확인 (성능 아님)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> dict:
    a = _cli(argv)
    if a.demo:
        print("[demo] 합성 맵 3종(직선·호·덩어리)과 합성 로트 4개. 로직 확인이지 성능이 아니다.")
        for kind in ("line", "arc", "blob"):
            s = scratch_shape(synthetic_scratch_map(kind, 1), a.min_len_frac, a.notch_deg)
            print(f"  {kind:4s} -> {s['shape']:9s} ratio={s['ratio']:.2f} len={s['length_norm']:.2f}R "
                  f"n={s['n']} line_angle={s['line_angle_deg']:.0f}deg arc_r={s['arc_r_norm']:.2f}R "
                  f"center_outside={s['arc_center_outside']}")
        out = a.output or HERE / "scratch_demo"
        res = run(demo_records(), out, a.notch_deg, a.min_n, a.min_len_frac, label="demo (synthetic)")
        exp = {"demoL": "reproducible_line", "demoM": "random", "demoN": "random", "demoS": "insufficient"}
        got = dict(zip(res["lots"]["lot"], res["lots"]["verdict"]))
        ok = all(got.get(k) == v for k, v in exp.items())
        print(f"\n[demo] 기대 판정과 {'일치' if ok else '불일치'}: " +
              ", ".join(f"{k}={got.get(k)}(기대 {v})" for k, v in exp.items()))
        if not ok:
            sys.exit(1)
        return res
    if a.path is None:
        sys.exit("입력 pkl 경로가 필요하다 (또는 --demo).")
    df = load_records(a.path, a.pred)
    out = a.output or HERE / "scratch_out"
    return run(df, out, a.notch_deg, a.min_n, a.min_len_frac, label=a.path.name)


if __name__ == "__main__":
    matplotlib.use("Agg")
    main()
