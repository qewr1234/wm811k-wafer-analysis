# wm811k_azimuth.py
# 방위각 분석 - 로트 안에서 EDGE_LOC / LOC 의 위치가 노치 기준 같은 각도에 반복되는가
#
# 배경
#   docs/defect_signatures.md 의 EDGE_LOC 점검과 현장 순서 3번은 "불량 호의 방위각을 노치
#   기준으로 재서, 같은 챔버를 거친 웨이퍼에서 같은 각도면 챔버 비대칭(배기구·가스구 방향),
#   각도가 제각각이면 핸들링(로봇 센터링)·이벤트"라고 적고 있는데 그 계산이 코드에 없었다.
#   이 모듈은 웨이퍼마다 최대 연결 성분의 무게중심 방위각을 재고, 로트 안에서 그 각도들이
#   한 방향으로 모이는지를 원형 통계(Rayleigh 검정)로 판정한다.
#
# 무엇을 하나
#   notch_relative_angle   wafermap_to_df 규약(+x = 0도, 반시계 양수)의 각도를 노치 = 0도 로 옮긴다.
#   component_azimuth      맵 한 장: 최대 성분(8-이웃)의 방위각·각도 폭·무게중심 반경·크기.
#   rayleigh_test          각도 집합의 평균 벡터 길이 r_bar, 평균각, 균일성 검정 p.
#                          n < 50 이면 균일 분포에서 n 개를 뽑는 순열(Monte Carlo) p,
#                          n >= 50 이면 근사식(0~1 로 clip). 근사식은 r_bar ~ 1 에서 음수가 되므로
#                          작은 n 에서는 쓰지 않는다.
#   lot_azimuth_summary    로트별 n, r_bar, mean_deg, span_med, p, verdict.
#                          verdict: n >= min_n 이고 p < 0.05 이고 r_bar >= 0.7 -> fixed_angle
#                                   (챔버/스테이션의 고정 요소 의심)
#                                   n >= min_n 이고 그 외             -> scattered (핸들링·이벤트)
#                                   n <  min_n                        -> insufficient
#   line_azimuth_summary   로트별 평균각(로트당 1표)을 모아 다시 Rayleigh - 라인 전체에서
#                          특정 각도로 계속 나오는가.
#   plot_azimuth_rose      노치 0도 로즈 다이어그램(matplotlib polar). 노치가 그림상 notch_deg
#                          방향에 오도록 축을 돌려 plot_wafer_map 과 같은 방향으로 보인다.
#   load_records           pkl(waferMap, lotName, waferIndex, failureType) + 예측 CSV(y_pred) 결합.
#
# 왜
#   같은 패턴이라도 "어느 각도에" 나오는지가 장비 측 증거(배기구 위치, 로봇 티칭 로그)와
#   맞대는 첫 단서다. 각도는 0/360 경계가 있어 산술 평균이 틀리므로 원형 통계를 쓴다.
#
# 한계 (중요)
#   - 노치 방향은 가정이다. WM-811K 배열이 물리 노치와 어떻게 정렬돼 있는지는 데이터셋 문서에
#     없다. 기본값 -90도 는 plot_wafer_map 이 노치를 그리는 위치(그림 아래)일 뿐이며, 모든 출력에
#     '노치 기준 각도(가정: notch_deg=-90)' 라고 적는다. 실제 장비 데이터에서는 --notch-deg 로
#     맵 좌표계와 노치의 대응을 넣어야 한다. 같은 로트 안의 '상대 각도'는 이 가정과 무관하다.
#   - WM-811K 결함 부분집합은 로트당 평균 3.2장(25,519 / 8,047)이라 대부분 로트가 insufficient 다.
#     이 모듈의 쓸모는 실측 검증이 아니라, 로트 단위 웨이퍼가 충분한 실제 팹 데이터에서의
#     판정 절차를 코드로 고정한 것이다.
#   - --demo 와 tests/ 의 합성 결과는 로직 확인이지 성능이 아니다.
#   - 방위각은 최대 연결 성분 하나만 본다. 혼합 패턴(센터 + 엣지 국소)은 큰 쪽만 잡힌다.
#   - 분류는 입력(y_pred 또는 y_true)을 그대로 믿는다. 오분류된 웨이퍼의 각도는 걸러지지 않는다.
#
# 사용법
#   python wm811k_azimuth.py --demo                               # 합성 로트 4개로 판정 확인
#   python wm811k_azimuth.py data/wm811k_defects.pkl              # y_true 기준 (라벨 pkl)
#   python wm811k_azimuth.py data/wm811k_defects.pkl --pred test_predictions.csv --notch-deg -90
#   python wm811k_azimuth.py records.pkl --classes EDGE_LOC --min-n 3 --output azimuth_out
#   입력 df 는 waferMap, lot, (y_pred 또는 y_true) 열. 예측 CSV 는 lot, y_pred (선택: wafer_index).
#   출력: azimuth_wafers.csv, azimuth_lots.csv, azimuth_line.txt, azimuth_rose.png

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import ndimage

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DEFAULT_NOTCH_DEG = -90.0            # plot_wafer_map 이 노치를 그리는 방향 (가정)
DEFAULT_CLASSES = ("EDGE_LOC", "LOC")
DEFAULT_MIN_N = 3
P_ALPHA = 0.05
R_BAR_FIXED = 0.7
RAYLEIGH_PERM_MAX_N = 50             # 이 미만이면 순열 p, 이상이면 근사식
_EIGHT = np.ones((3, 3), dtype=int)

LABEL_MAP = {
    "Edge-Ring": "EDGE_RING", "Edge-Loc": "EDGE_LOC", "Center": "CENTER",
    "Loc": "LOC", "Scratch": "SCRATCH", "Random": "RANDOM",
    "Donut": "DONUT", "Near-full": "NEAR_FULL", "none": "CLEAN",
}

NOTCH_NOTE = ("노치 기준 각도 (가정: notch_deg={notch:g}; WM-811K 배열과 물리 노치의 대응은 "
              "데이터셋 문서에 없다. 같은 로트 안의 상대 각도는 이 가정과 무관)")


# ──────────────────────────────────────────
# 1. 각도 규약
# ──────────────────────────────────────────
def notch_relative_angle(angle_deg, notch_deg: float = DEFAULT_NOTCH_DEG):
    """wafermap_to_df 규약(+x = 0도, 반시계 양수)의 각도를 노치 = 0도 기준 (-180, 180] 로 옮긴다.

    notch_deg 는 '맵 좌표계에서 노치가 있는 방향'이다. 기본값 -90도 는 plot_wafer_map 이 노치를
    그림 아래(0, -R)에 그리기 때문이며, WM-811K 배열이 실제로 그렇게 정렬돼 있다는 근거는 없다
    (가정). 반시계 양수는 유지된다. 스칼라를 주면 float, 배열을 주면 ndarray 를 돌려준다.

    예: notch_relative_angle(-90, -90) == 0, notch_relative_angle(0, -90) == 90.
    """
    a = np.asarray(angle_deg, dtype=float)
    d = np.mod(a - notch_deg, 360.0)
    d = np.where(d > 180.0, d - 360.0, d)
    if a.ndim == 0:
        return float(d)
    return d


def wafer_frame(arr: np.ndarray) -> tuple[float, float, float, float]:
    """다이 영역 bounding box 의 중심(cy, cx)과 축별 반폭(ry, rx).

    wm811k_validate.largest_component_features 와 같은 정규화 방식(배열 중심이 아니라 다이
    bbox 중심, 축별 반폭)을 여기서 따로 구현한다. 그 함수는 README 수치의 전제라 건드리지 않는다.
    """
    die = np.asarray(arr) > 0
    ys, xs = np.nonzero(die)
    if len(ys) == 0:
        raise ValueError("다이가 없는 맵이다 (모든 셀이 0).")
    cy, cx = (ys.min() + ys.max()) / 2.0, (xs.min() + xs.max()) / 2.0
    ry = max((ys.max() - ys.min()) / 2.0, 1e-9)
    rx = max((xs.max() - xs.min()) / 2.0, 1e-9)
    return cy, cx, ry, rx


def largest_component_xy(arr: np.ndarray) -> np.ndarray:
    """최대 연결 성분(8-이웃)의 다이 좌표를 단위원 좌표 (x 오른쪽, y 위) 의 (n, 2) 배열로.

    반경 1 = 다이 영역 bbox 의 축별 반폭. 불량이 없으면 (0, 2) 배열.
    """
    a = np.asarray(arr)
    fail = a == 2
    if not fail.any():
        return np.zeros((0, 2), dtype=float)
    cy, cx, ry, rx = wafer_frame(a)
    lab, n = ndimage.label(fail, structure=_EIGHT)
    sizes = np.bincount(lab.ravel())[1:]
    big = int(sizes.argmax()) + 1
    py, px = np.nonzero(lab == big)
    ux = (px - cx) / rx
    uy = -(py - cy) / ry                    # 배열 행은 아래로 증가 -> y 축 위가 +
    return np.column_stack([ux, uy])


# ──────────────────────────────────────────
# 2. 맵 한 장의 방위각
# ──────────────────────────────────────────
def component_azimuth(arr: np.ndarray, notch_deg: float = DEFAULT_NOTCH_DEG) -> dict:
    """최대 연결 성분의 방위각 요약.

    Returns
    -------
    dict
        theta_deg   무게중심 방위각, 노치 기준 (-180, 180]. 불량 없으면 NaN.
        span_deg    성분이 차지하는 각도 폭(도). 0/360 경계를 넘는 호도 원형 통계로 올바르게 잰다.
        r_centroid  무게중심의 정규화 반경 (0 = 중심, 1 = 다이 bbox 가장자리).
        size        성분의 다이 수.
    """
    xy = largest_component_xy(arr)
    if len(xy) == 0:
        return {"theta_deg": float("nan"), "span_deg": 0.0, "r_centroid": 0.0, "size": 0}
    ux, uy = xy[:, 0], xy[:, 1]
    ang = np.arctan2(uy, ux)
    mx, my = ux.mean(), uy.mean()
    theta = np.degrees(np.arctan2(my, mx))
    # 각도 폭: 평균각 기준 편차의 범위 (경계 넘는 호 대응)
    mean_ang = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
    dev = np.angle(np.exp(1j * (ang - mean_ang)))
    span = float(np.degrees(dev.max() - dev.min())) if len(dev) > 1 else 0.0
    return {
        "theta_deg": notch_relative_angle(theta, notch_deg),
        "span_deg": span,
        "r_centroid": float(np.hypot(mx, my)),
        "size": int(len(xy)),
    }


# ──────────────────────────────────────────
# 3. Rayleigh 검정
# ──────────────────────────────────────────
def _resultant(theta_rad: np.ndarray) -> tuple[float, float]:
    c, s = np.cos(theta_rad).mean(), np.sin(theta_rad).mean()
    return float(np.hypot(c, s)), float(np.degrees(np.arctan2(s, c)))


def rayleigh_test(theta_deg, n_perm: int = 2000, seed: int = 0) -> dict:
    """각도 집합이 한 방향으로 모이는가 (Rayleigh 균일성 검정).

    Parameters
    ----------
    theta_deg : 각도(도). NaN 은 제외한다.
    n_perm    : n < 50 일 때 순열(Monte Carlo) 반복 수.
    seed      : 순열 난수 시드.

    Returns
    -------
    dict(n, r_bar, mean_deg, p)
        r_bar     평균 벡터 길이 (0 = 균일, 1 = 전부 같은 각도)
        mean_deg  평균각 (-180, 180]. 0/360 경계를 넘어도 맞다 (예: -170, 175 -> 약 -177.5).
        p         균일 가설의 p 값, 항상 [0, 1]. n < 50 은 순열(균일 분포에서 n 개 추출한 r_bar
                  가 관측값 이상인 비율, +1 보정), n >= 50 은 근사식을 [0, 1] 로 clip.
                  n < 2 이면 p = 1.0 (검정 불가).
    """
    th = np.asarray(theta_deg, dtype=float).ravel()
    th = th[np.isfinite(th)]
    n = int(len(th))
    if n == 0:
        return {"n": 0, "r_bar": float("nan"), "mean_deg": float("nan"), "p": 1.0}
    rad = np.radians(th)
    r_bar, mean_deg = _resultant(rad)
    if n < 2:
        return {"n": n, "r_bar": r_bar, "mean_deg": mean_deg, "p": 1.0}

    if n < RAYLEIGH_PERM_MAX_N:
        rng = np.random.default_rng(seed)
        u = rng.uniform(-np.pi, np.pi, size=(int(n_perm), n))
        r_perm = np.hypot(np.cos(u).mean(axis=1), np.sin(u).mean(axis=1))
        p = (float((r_perm >= r_bar - 1e-12).sum()) + 1.0) / (n_perm + 1.0)
    else:
        z = n * r_bar ** 2
        p = np.exp(-z) * (1.0 + (2.0 * z - z ** 2) / (4.0 * n)
                          - (24.0 * z - 132.0 * z ** 2 + 76.0 * z ** 3 - 9.0 * z ** 4)
                          / (288.0 * n ** 2))
        p = float(np.clip(p, 0.0, 1.0))
    return {"n": n, "r_bar": r_bar, "mean_deg": mean_deg, "p": float(min(max(p, 0.0), 1.0))}


def azimuth_verdict(n: int, p: float, r_bar: float, min_n: int = DEFAULT_MIN_N) -> str:
    """fixed_angle / scattered / insufficient 판정 (lot_azimuth_summary 와 line 요약이 공유)."""
    if n < min_n:
        return "insufficient"
    if np.isfinite(p) and np.isfinite(r_bar) and p < P_ALPHA and r_bar >= R_BAR_FIXED:
        return "fixed_angle"
    return "scattered"


# ──────────────────────────────────────────
# 4. 입력 결합 / 로트 요약
# ──────────────────────────────────────────
def label_column(df: pd.DataFrame) -> str:
    """판정에 쓸 라벨 열. y_pred 가 있으면 예측, 없으면 y_true."""
    for c in ("y_pred", "y_true"):
        if c in df.columns:
            return c
    raise ValueError("y_pred 또는 y_true 열이 필요하다.")


def load_records(path: Path, pred: Path | None = None) -> pd.DataFrame:
    """pkl(LSWMD 형식 또는 prepare_wm811k 출력) 을 읽고, 있으면 예측 CSV 의 y_pred 를 붙인다.

    반환 열: waferMap, lot, wafer_index, y_true, (y_pred, confidence).
    예측 CSV 와의 결합은 양쪽에 wafer_index 가 있으면 (lot, wafer_index) 키, 없으면 행 수가 같을
    때 행 순서. 어느 쪽도 안 되면 ValueError.
    """
    df = pd.read_pickle(path)
    if "waferMap" not in df.columns:
        raise ValueError(f"{path.name}: waferMap 열이 없다.")
    out = pd.DataFrame({"waferMap": df["waferMap"].to_numpy()})
    out["lot"] = (df["lotName"] if "lotName" in df.columns else df.get("lot", "unknown")).astype(str).to_numpy()
    if "wafer_index" in df.columns:
        out["wafer_index"] = pd.to_numeric(df["wafer_index"], errors="coerce").to_numpy()
    elif "waferIndex" in df.columns:
        out["wafer_index"] = pd.to_numeric(df["waferIndex"], errors="coerce").to_numpy()
    else:
        out["wafer_index"] = np.nan
    if "y_true" in df.columns:
        out["y_true"] = df["y_true"].to_numpy()
    else:
        raw = df["ftype"] if "ftype" in df.columns else df.get("failureType")
        if raw is not None:
            ft = raw.apply(lambda v: str(np.asarray(v).reshape(-1)[0]) if np.asarray(v).size else None)
            out["y_true"] = ft.map(lambda s: LABEL_MAP.get(s, s)).to_numpy()
    out = out[out["waferMap"].apply(lambda m: np.ndim(m) == 2 and np.asarray(m).size > 0)].reset_index(drop=True)

    if pred is not None:
        p = pd.read_csv(pred)
        if "y_pred" not in p.columns or "lot" not in p.columns:
            raise ValueError(f"{pred.name}: lot, y_pred 열이 필요하다.")
        p["lot"] = p["lot"].astype(str)
        keep = [c for c in ("y_pred", "confidence") if c in p.columns]
        if "wafer_index" in p.columns and out["wafer_index"].notna().all():
            p["wafer_index"] = pd.to_numeric(p["wafer_index"], errors="coerce")
            p = p.drop_duplicates(["lot", "wafer_index"])
            out = out.merge(p[["lot", "wafer_index"] + keep], on=["lot", "wafer_index"], how="left")
        elif len(p) == len(out):
            for c in keep:
                out[c] = p[c].to_numpy()
        else:
            raise ValueError("예측 CSV 를 결합할 수 없다: wafer_index 가 없고 행 수도 다르다 "
                             f"({len(p)} vs {len(out)}).")
        out = out[out["y_pred"].notna()].reset_index(drop=True)
    return out


def wafer_azimuth_table(df: pd.DataFrame, classes=DEFAULT_CLASSES,
                        notch_deg: float = DEFAULT_NOTCH_DEG) -> pd.DataFrame:
    """classes 에 속한 웨이퍼마다 component_azimuth 를 구한 표.

    열: lot, wafer_index, label, theta_deg, span_deg, r_centroid, size.
    """
    col = label_column(df)
    sub = df[df[col].isin(list(classes))]
    rows = []
    for i, r in sub.iterrows():
        az = component_azimuth(np.asarray(r["waferMap"]), notch_deg)
        rows.append({"lot": str(r["lot"]), "wafer_index": r.get("wafer_index", np.nan),
                     "label": r[col], **az})
    cols = ["lot", "wafer_index", "label", "theta_deg", "span_deg", "r_centroid", "size"]
    return pd.DataFrame(rows, columns=cols)


def lot_azimuth_summary(df: pd.DataFrame, classes=DEFAULT_CLASSES, min_n: int = DEFAULT_MIN_N,
                        notch_deg: float = DEFAULT_NOTCH_DEG, n_perm: int = 2000,
                        seed: int = 0) -> pd.DataFrame:
    """로트별 방위각 집중도와 판정.

    Parameters
    ----------
    df       : waferMap, lot, (y_pred 또는 y_true) 열. y_pred 가 있으면 그것을 쓴다.
    classes  : 방위각을 볼 패턴 (기본 EDGE_LOC, LOC).
    min_n    : 판정에 필요한 최소 웨이퍼 수. 미만이면 insufficient.

    Returns
    -------
    DataFrame(lot, n, r_bar, mean_deg, span_med, p, verdict) - verdict 는
    fixed_angle(챔버/스테이션 고정 요소 의심) / scattered(핸들링·이벤트) / insufficient.
    p 는 n >= 2 일 때만 계산하고 그 외 NaN. classes 웨이퍼가 없는 로트는 표에 없다.
    """
    tab = wafer_azimuth_table(df, classes, notch_deg)
    rows = []
    for lot, g in tab.groupby("lot", sort=True):
        th = g["theta_deg"].to_numpy()
        th = th[np.isfinite(th)]
        n = int(len(th))
        rt = rayleigh_test(th, n_perm=n_perm, seed=seed) if n >= 2 else None
        r_bar = rt["r_bar"] if rt else (float("nan") if n == 0 else 1.0)
        mean_deg = rt["mean_deg"] if rt else (float(th[0]) if n == 1 else float("nan"))
        p = rt["p"] if rt else float("nan")
        rows.append({
            "lot": lot, "n": n, "r_bar": r_bar, "mean_deg": mean_deg,
            "span_med": float(np.nanmedian(g["span_deg"])) if len(g) else float("nan"),
            "p": p, "verdict": azimuth_verdict(n, p, r_bar, min_n),
        })
    cols = ["lot", "n", "r_bar", "mean_deg", "span_med", "p", "verdict"]
    return pd.DataFrame(rows, columns=cols)


def line_azimuth_summary(lot_summary: pd.DataFrame, min_lots: int = DEFAULT_MIN_N,
                         min_lot_n: int = 1, n_perm: int = 2000, seed: int = 0) -> dict:
    """로트별 평균각(로트당 1표)을 모아 라인 수준 Rayleigh.

    로트당 1표로 줄이는 이유: 같은 로트의 웨이퍼는 패턴을 공유하므로 웨이퍼를 그대로 풀링하면
    로트 하나가 검정을 지배한다. min_lot_n 으로 '표를 낼 수 있는 로트'의 최소 웨이퍼 수를 둔다
    (기본 1 - WM-811K 처럼 로트당 장수가 적은 데이터에서도 라인 수준은 볼 수 있게).

    Returns
    -------
    dict(n_lots, r_bar, mean_deg, p, verdict) - verdict 는 line_fixed_angle / line_scattered /
    insufficient (n_lots < min_lots). 판정 기준은 lot 수준과 같다 (p < 0.05, r_bar >= 0.7).
    """
    s = lot_summary[(lot_summary["n"] >= min_lot_n) & np.isfinite(lot_summary["mean_deg"])]
    rt = rayleigh_test(s["mean_deg"].to_numpy(), n_perm=n_perm, seed=seed)
    v = azimuth_verdict(rt["n"], rt["p"], rt["r_bar"], min_lots)
    verdict = {"fixed_angle": "line_fixed_angle", "scattered": "line_scattered"}.get(v, v)
    return {"n_lots": rt["n"], "r_bar": rt["r_bar"], "mean_deg": rt["mean_deg"],
            "p": rt["p"], "verdict": verdict}


# ──────────────────────────────────────────
# 5. 그림
# ──────────────────────────────────────────
def plot_azimuth_rose(theta_deg, ax=None, notch_deg: float = DEFAULT_NOTCH_DEG,
                      title: str = "", bins: int = 24):
    """노치 0도 로즈 다이어그램. theta_deg 는 노치 기준 각도(도).

    축을 돌려 0도(노치)가 그림에서 notch_deg 방향(기본 아래)에 오게 하므로 plot_wafer_map 의
    웨이퍼 그림과 같은 방향으로 읽힌다. 반시계 양수. 평균 벡터를 화살표로 덧그린다.
    """
    if ax is None:
        _, ax = plt.subplots(subplot_kw={"projection": "polar"}, figsize=(4, 4))
    th = np.asarray(theta_deg, dtype=float).ravel()
    th = th[np.isfinite(th)]
    edges = np.linspace(-180.0, 180.0, bins + 1)
    counts, _ = np.histogram(th, bins=edges)
    centers = np.radians((edges[:-1] + edges[1:]) / 2.0)
    width = np.radians(360.0 / bins)
    ax.bar(centers, counts, width=width, bottom=0.0, color="#1976D2", alpha=0.75,
           edgecolor="white", linewidth=0.5)
    ax.set_theta_offset(np.radians(notch_deg))       # 0도(노치)를 그림의 notch_deg 방향에
    ax.set_theta_direction(1)                         # 반시계 양수
    ax.set_thetagrids(range(0, 360, 45),
                      labels=[f"{d if d <= 180 else d - 360:d}" for d in range(0, 360, 45)])
    ax.set_yticklabels([])
    ymax = max(counts.max() if len(counts) else 1, 1)
    ax.annotate("notch", xy=(0.0, ymax * 1.05), ha="center", va="center", fontsize=8, color="#455A64")
    if len(th) >= 1:
        rt = rayleigh_test(th)
        ax.annotate("", xy=(np.radians(rt["mean_deg"]), rt["r_bar"] * ymax), xytext=(0, 0),
                    arrowprops=dict(arrowstyle="->", color="#D32F2F", lw=1.8))
        sub = f"n={rt['n']}  r_bar={rt['r_bar']:.2f}  mean={rt['mean_deg']:.0f}deg  p={rt['p']:.3g}"
    else:
        sub = "n=0"
    ax.set_title(f"{title}\n{sub}" if title else sub, fontsize=9)
    return ax


# ──────────────────────────────────────────
# 6. 합성 데모 (로직 확인용 - 성능 아님)
# ──────────────────────────────────────────
def _synthetic_edge_loc_map(angle_deg: float, seed: int, rng: np.random.Generator) -> np.ndarray:
    """임의 각도(맵 좌표계, +x = 0도)에 엣지 국소 호를 심은 맵. generate_sample_wafer_data 는
    edge_loc 각도가 45도 로 고정돼 있어 각도를 바꾼 로트가 필요할 때 쓴다."""
    sys.path.insert(0, str(HERE / "tests"))
    from synthetic_wm811k import df_to_wafermap  # noqa: E402
    from wafer_map_visualizer import generate_sample_wafer_data  # noqa: E402

    diam = float(rng.choice([200, 250, 300]))
    die = float(rng.choice([8, 10]))
    df = generate_sample_wafer_data(wafer_diameter_mm=diam, die_size_mm=die, defect_mode="clean",
                                    noise=0.0, seed=seed)
    R = float(df["radius"].max())
    dev = np.angle(np.exp(1j * np.radians(df["angle_deg"].to_numpy() - angle_deg)))
    fail = (df["radius"].to_numpy() >= 0.8 * R) & (np.abs(np.degrees(dev)) <= 30.0)
    flip = rng.random(len(df)) < rng.uniform(0.01, 0.04)
    fail = np.where(flip, ~fail, fail)
    df["status"] = np.where(fail, "FAIL", "PASS")
    return df_to_wafermap(df, die)


def demo_records(seed: int = 0) -> pd.DataFrame:
    """합성 로트 4개 (waferMap, lot, wafer_index, y_true).

    A  edge_loc 8장, 생성기 고정 각도(맵 좌표 45도)          -> fixed_angle 기대
    B  edge_loc 8장, 각도 균일 난수                          -> scattered 기대
    C  loc 2장                                               -> insufficient 기대
    D  loc 6장, 생성기의 균일 난수 각도                       -> scattered 기대
    """
    sys.path.insert(0, str(HERE / "tests"))
    from synthetic_wm811k import make_wafermap  # noqa: E402

    rng = np.random.default_rng(seed)
    rows = []
    for w in range(8):
        rows.append({"waferMap": make_wafermap("edge_loc", 100 + w, rng), "lot": "demoA",
                     "wafer_index": w, "y_true": "EDGE_LOC"})
    for w in range(8):
        rows.append({"waferMap": _synthetic_edge_loc_map(rng.uniform(-180, 180), 200 + w, rng),
                     "lot": "demoB", "wafer_index": w, "y_true": "EDGE_LOC"})
    for w in range(2):
        rows.append({"waferMap": make_wafermap("loc", 300 + w, rng), "lot": "demoC",
                     "wafer_index": w, "y_true": "LOC"})
    for w in range(6):
        rows.append({"waferMap": make_wafermap("loc", 400 + w, rng), "lot": "demoD",
                     "wafer_index": w, "y_true": "LOC"})
    return pd.DataFrame(rows)


# ──────────────────────────────────────────
# 7. CLI
# ──────────────────────────────────────────
def run(df: pd.DataFrame, out_dir: Path, classes=DEFAULT_CLASSES, min_n: int = DEFAULT_MIN_N,
        notch_deg: float = DEFAULT_NOTCH_DEG, max_rose: int = 5, label: str = "") -> dict:
    """표 2개 + 라인 요약 + 로즈 그림을 out_dir 에 저장하고 요약 dict 를 돌려준다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    note = NOTCH_NOTE.format(notch=notch_deg)
    col = label_column(df)
    wafers = wafer_azimuth_table(df, classes, notch_deg)
    lots = lot_azimuth_summary(df, classes, min_n, notch_deg)
    line = line_azimuth_summary(lots, min_lots=min_n)

    wafers.to_csv(out_dir / "azimuth_wafers.csv", index=False, encoding="utf-8-sig")
    lots.to_csv(out_dir / "azimuth_lots.csv", index=False, encoding="utf-8-sig")

    print(f"\n{'=' * 74}\n방위각 분석{(' - ' + label) if label else ''}\n{'=' * 74}")
    print(f"  라벨 열: {col}   대상 패턴: {', '.join(classes)}   min_n: {min_n}")
    print(f"  {note}")
    print(f"  웨이퍼 {len(wafers)}장 / 로트 {len(lots)}개")
    vc = lots["verdict"].value_counts()
    print("  로트 판정: " + ", ".join(f"{k} {int(vc.get(k, 0))}" for k in
                                 ("fixed_angle", "scattered", "insufficient")))
    if len(lots):
        show = lots.sort_values(["verdict", "n"], ascending=[True, False]).head(20).copy()
        print("\n  " + show.to_string(index=False, float_format=lambda v: f"{v:.3f}").replace("\n", "\n  "))
    print(f"\n  라인 수준 (로트당 1표, n_lots={line['n_lots']}): r_bar={line['r_bar']:.3f} "
          f"mean={line['mean_deg']:.1f}deg p={line['p']:.3g} -> {line['verdict']}")
    print("  판정 읽기: fixed_angle = 챔버/스테이션의 고정 요소(배기구·가스구 방향, 로봇 티칭 오프셋) 의심,"
          " 장비 측 로그(로봇 센터링, 챔버 도면 각도)와 대조. scattered = 핸들링·이벤트 쪽. "
          "insufficient = 로트 안 장수 부족, 판정 보류.")

    with open(out_dir / "azimuth_line.txt", "w", encoding="utf-8") as f:
        f.write(f"{note}\n")
        for k, v in line.items():
            f.write(f"{k}: {v}\n")

    # 로즈: 전체 + 장수 많은 로트 순
    pick = lots[lots["n"] >= 2].sort_values("n", ascending=False)["lot"].head(max_rose).tolist()
    n_ax = 1 + len(pick)
    fig, axes = plt.subplots(1, n_ax, subplot_kw={"projection": "polar"},
                             figsize=(3.6 * n_ax, 4.2))
    axes = np.atleast_1d(axes)
    plot_azimuth_rose(wafers["theta_deg"], axes[0], notch_deg, title="all wafers")
    for ax, lot in zip(axes[1:], pick):
        v = lots.loc[lots["lot"] == lot, "verdict"].iloc[0]
        plot_azimuth_rose(wafers.loc[wafers["lot"] == lot, "theta_deg"], ax, notch_deg,
                          title=f"lot {lot} ({v})")
    fig.suptitle(f"Azimuth of largest component, notch = 0 deg (assumed notch_deg={notch_deg:g})",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(out_dir / "azimuth_rose.png", dpi=110)
    plt.close(fig)
    print(f"\n  저장: {out_dir / 'azimuth_wafers.csv'}, {out_dir / 'azimuth_lots.csv'}, "
          f"{out_dir / 'azimuth_line.txt'}, {out_dir / 'azimuth_rose.png'}")
    return {"wafers": wafers, "lots": lots, "line": line}


def _cli(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="EDGE_LOC/LOC 의 노치 기준 방위각이 로트 안에서 고정인지(챔버 비대칭) "
                    "흩어졌는지(핸들링) Rayleigh 검정으로 판정한다.")
    ap.add_argument("path", nargs="?", type=Path, default=None,
                    help="records.pkl 또는 wm811k_defects.pkl (waferMap, lotName, failureType)")
    ap.add_argument("--pred", type=Path, default=None,
                    help="예측 CSV (lot, y_pred, 선택 wafer_index). 있으면 y_true 대신 y_pred 로 판정")
    ap.add_argument("--classes", nargs="+", default=list(DEFAULT_CLASSES),
                    help=f"방위각을 볼 패턴 (기본 {' '.join(DEFAULT_CLASSES)})")
    ap.add_argument("--min-n", type=int, default=DEFAULT_MIN_N,
                    help=f"로트 판정에 필요한 최소 웨이퍼 수 (기본 {DEFAULT_MIN_N})")
    ap.add_argument("--notch-deg", type=float, default=DEFAULT_NOTCH_DEG,
                    help=f"맵 좌표계에서 노치 방향(도). 기본 {DEFAULT_NOTCH_DEG:g} 는 가정이다")
    ap.add_argument("--output", type=Path, default=None,
                    help="출력 폴더 (기본: HERE/azimuth_out, --demo 는 HERE/azimuth_demo)")
    ap.add_argument("--demo", action="store_true", help="합성 로트 4개로 판정 로직 확인 (성능 아님)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> dict:
    a = _cli(argv)
    if a.demo:
        df = demo_records()
        out = a.output or HERE / "azimuth_demo"
        print("[demo] 합성 로트 4개: A edge_loc 고정각(8장) / B edge_loc 균일 난수각(8장) / "
              "C loc 2장 / D loc 난수각(6장). 로직 확인이지 성능이 아니다.")
        res = run(df, out, tuple(a.classes), a.min_n, a.notch_deg, label="demo (synthetic)")
        exp = {"demoA": "fixed_angle", "demoB": "scattered", "demoC": "insufficient", "demoD": "scattered"}
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
    out = a.output or HERE / "azimuth_out"
    return run(df, out, tuple(a.classes), a.min_n, a.notch_deg, label=a.path.name)


if __name__ == "__main__":
    matplotlib.use("Agg")
    main()
