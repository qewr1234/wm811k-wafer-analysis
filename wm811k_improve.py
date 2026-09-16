# wm811k_improve.py
# WM-811K — 노이즈에 강건한 구조 특징 추가 + 그래디언트 부스팅 비교
#
# 배경 (wm811k_validate.py 결과, 로트 분할 5회)
#   RF(전역+구조+위치 20개) macro-F1 0.907 ± 0.008
#   남은 오류: LOC → EDGE_LOC(5회 합산 542장), SCRATCH → LOC(270장).
#   둘 다 "국소 덩어리가 어디 있고 어떤 모양인가"의 경계 문제다.
#
# 진단
#   기존 연결 성분 특징(n_comp, comp_size_mean)은 산발 불량 다이 1개를
#   성분 1개로 센다. 실측은 패턴 위에 산발 불량이 깔려 있어 이 값이
#   패턴이 아니라 노이즈 수준을 재고 있었다(n_comp AUC 0.155이 그 증거).
#
# 추가하는 특징 (8개, 모두 최대 연결 성분 또는 성분 크기 ≥ 3 기준)
#   isolated_frac : 불량 중 고립 다이(성분 크기 1) 비율. 노이즈 수준 자체.
#   n_comp_sig    : 크기 ≥ 3 성분 수. 노이즈를 뺀 "덩어리 개수".
#   sig_frac      : 크기 ≥ 3 성분에 속한 불량 비율. 패턴 대 노이즈 비.
#   fail_nb_mean  : 불량 다이당 8-이웃 불량 수 평균. RANDOM 낮고 덩어리는 높다.
#   big_extent    : 최대 성분 크기 / 바운딩 박스 면적. 선(SCRATCH)은 낮고 덩어리(LOC)는 높다.
#   big_len       : 최대 성분 주축 길이 / 웨이퍼 반경. 스크래치는 길다.
#   big_edge_touch: 최대 성분 다이 중 웨이퍼 가장자리(밖과 인접)에 닿은 비율.
#                   EDGE_LOC은 가장자리에 붙어 있고 LOC은 떠 있다 — 혼동을 직접 겨냥.
#   second_frac   : 두 번째 큰 성분 / 최대 성분. 성분이 둘 이상인 패턴 구분.
#
# 비교 설계 (모두 같은 로트 분할 5개에서 짝지어)
#   RF-20 (기준) / RF-28 / HGB-20 / HGB-28
#   HGB(HistGradientBoosting)은 RF와 같은 특징으로 "모델을 바꾸면 얼마나
#   오르나"를 분리해 본다. 특징의 기여와 모델의 기여를 섞지 않기 위해서다.
#   채택 기준: 5회 모두 개선이고 Δ 평균이 분할 간 표준편차보다 클 것.
#
# 누수 방지: 로트 단위 분할, 하이퍼파라미터는 고정값(탐색하지 않음), test는 비교에만.

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score

from wm811k_structural import CLASSES, LABEL_MAP, MIN_DIE, structural_features
from wm811k_validate import (
    FEATS_B, SEEDS, auc_ovr, largest_component_features, lot_split, macro_f1,
    make_rf,
)
from wafer_map_visualizer import wafermap_to_df
from wafer_pattern_classifier import classify_wafer_pattern

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("WM811K_DIR", HERE / "data"))
CACHE3 = HERE / "wm811k_features_ext3.csv"

ROBUST_FEATURES = ["isolated_frac", "n_comp_sig", "sig_frac", "fail_nb_mean",
                   "big_extent", "big_len", "big_edge_touch", "second_frac"]
FEATS_BASE = FEATS_B                        # 20개 (wm811k_validate 결과 재현)
FEATS_ALL = FEATS_B + ROBUST_FEATURES       # 28개
SIG_MIN_SIZE = 3
_EIGHT = np.ones((3, 3), dtype=int)


# ──────────────────────────────────────────
# 1. 노이즈에 강건한 구조 특징
# ──────────────────────────────────────────
def robust_features(wmap: np.ndarray) -> dict:
    arr = np.asarray(wmap)
    die, fail = arr > 0, arr == 2
    n_fail = int(fail.sum())
    zero = {f: 0.0 for f in ROBUST_FEATURES}
    if n_fail == 0:
        return zero

    lab, n = ndimage.label(fail, structure=_EIGHT)
    sizes = np.bincount(lab.ravel())[1:]
    order = np.argsort(sizes)[::-1]
    big = int(order[0]) + 1
    big_size = int(sizes[order[0]])

    out = {
        "isolated_frac": float((sizes == 1).sum() / n_fail),
        "n_comp_sig": float((sizes >= SIG_MIN_SIZE).sum()),
        "sig_frac": float(sizes[sizes >= SIG_MIN_SIZE].sum() / n_fail),
        "second_frac": float(sizes[order[1]] / big_size) if n > 1 else 0.0,
    }

    # 불량 다이당 8-이웃 불량 수. 컨볼루션으로 이웃 합을 구하고 자기 자신을 뺀다.
    nb = ndimage.convolve(fail.astype(int), _EIGHT, mode="constant") - fail
    out["fail_nb_mean"] = float(nb[fail].mean())

    # 최대 성분의 기하
    ys, xs = np.nonzero(die)
    ry = max((ys.max() - ys.min()) / 2.0, 1e-9)
    rx = max((xs.max() - xs.min()) / 2.0, 1e-9)
    py, px = np.nonzero(lab == big)
    h = py.max() - py.min() + 1
    w = px.max() - px.min() + 1
    out["big_extent"] = float(big_size / (h * w))

    if big_size >= 3:
        # 주축 방향 길이 — 단위원 좌표에서 최대 고유벡터로 사영한 범위
        u = np.vstack([(px - px.mean()) / rx, (py - py.mean()) / ry])
        cov = np.cov(u)
        ev, evec = np.linalg.eigh(cov)
        proj = evec[:, -1] @ u
        out["big_len"] = float(proj.max() - proj.min())
    else:
        out["big_len"] = float(max(h / ry, w / rx))

    # 웨이퍼 가장자리 다이: 4-이웃 중 다이가 아닌 칸(밖 또는 배열 경계)이 있는 다이
    inner = ndimage.binary_erosion(die, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]),
                                   border_value=0)
    edge_die = die & ~inner
    out["big_edge_touch"] = float(edge_die[py, px].mean())
    return out


# ──────────────────────────────────────────
# 2. 특징 테이블 (20 + 8)
# ──────────────────────────────────────────
def build_features(path: Path | None = None) -> pd.DataFrame:
    if CACHE3.exists():
        print(f"캐시 사용: {CACHE3}")
        return pd.read_csv(CACHE3)

    if path is None:
        for name in ["wm811k_defects.pkl", "LSWMD.pkl"]:
            if (DATA_DIR / name).exists():
                path = DATA_DIR / name
                break
        else:
            sys.exit(f"데이터 파일을 찾을 수 없다. {DATA_DIR} 에 wm811k_defects.pkl 이 있어야 한다.")

    print(f"로드: {path.name}")
    df = pd.read_pickle(path)
    if "ftype" not in df.columns:
        df["ftype"] = df["failureType"].apply(
            lambda v: str(np.asarray(v).reshape(-1)[0]) if np.asarray(v).size else None)
    df["lot"] = (df["lotName"] if "lotName" in df.columns else "unknown").astype(str)
    df = df[df["ftype"].isin(LABEL_MAP)].copy()
    df["y_true"] = df["ftype"].map(LABEL_MAP)

    recs, t0 = [], time.time()
    for i, (wmap, y, lot) in enumerate(zip(df["waferMap"], df["y_true"], df["lot"])):
        arr = np.asarray(wmap)
        if arr.ndim != 2 or (arr > 0).sum() < MIN_DIE:
            continue
        try:
            r = classify_wafer_pattern(wafermap_to_df(arr))
            st = structural_features(arr)
            nf = largest_component_features(arr)
            rb = robust_features(arr)
        except Exception:
            continue
        recs.append({
            "y_true": y, "lot": lot,
            "fail_frac": r.fail_fraction, "r_mean": r.r_mean_norm,
            "r_med": r.r_med_norm, "r_std": r.r_std_norm,
            "dir_c": r.dir_concentration, "axial_c": r.axial_concentration,
            **st, **nf, **rb,
        })
        if (i + 1) % 5000 == 0:
            print(f"  {i + 1}/{len(df)} ({time.time() - t0:.0f}s)")
    out = pd.DataFrame(recs)
    out.to_csv(CACHE3, index=False, encoding="utf-8-sig")
    print(f"저장: {CACHE3} ({len(out)}행, 특징 {len(FEATS_ALL)}개)")
    return out


# ──────────────────────────────────────────
# 3. 모델
# ──────────────────────────────────────────
def make_hgb() -> HistGradientBoostingClassifier:
    # 고정값. train 내부 탐색을 하지 않았으므로 "모델 교체" 효과만 본다.
    return HistGradientBoostingClassifier(
        max_iter=400, learning_rate=0.06, max_leaf_nodes=31,
        min_samples_leaf=10, l2_regularization=0.5,
        class_weight="balanced", random_state=42,
    )


MODELS = {
    "RF-20": (make_rf, FEATS_BASE),
    "RF-28": (make_rf, FEATS_ALL),
    "HGB-20": (make_hgb, FEATS_BASE),
    "HGB-28": (make_hgb, FEATS_ALL),
}
BASELINE = "RF-20"


def paired_table(res: dict[str, np.ndarray]) -> pd.DataFrame:
    base = res[BASELINE]
    rows = []
    for nm, v in res.items():
        d = v - base
        rows.append({
            "모델": nm,
            "평균": v.mean(), "표준편차": v.std(ddof=1),
            "최소": v.min(), "최대": v.max(),
            "Δ(기준 대비)": d.mean(),
            "개선 횟수": f"{int((d > 0).sum())}/{len(d)}" if nm != BASELINE else "-",
        })
    return pd.DataFrame(rows).set_index("모델")


# ──────────────────────────────────────────
def main(path: Path | None = None):
    F = build_features(path)
    print(f"\n{len(F)}행 / 로트 {F['lot'].nunique()}개 / 특징 {len(FEATS_ALL)}개")

    # ── 신규 특징 판별력 ──
    print(f"\n{'=' * 74}\n신규 특징의 판별력 (AUC one-vs-rest, 0.5 아래는 방향 반대)\n{'=' * 74}")
    tab = pd.DataFrame({
        f: {c: auc_ovr(F.loc[F["y_true"] == c, f].to_numpy(),
                       F.loc[F["y_true"] != c, f].to_numpy()) for c in CLASSES}
        for f in ROBUST_FEATURES
    }).round(3)
    print(tab.to_string())

    print(f"\n  겨냥한 혼동 — EDGE_LOC vs LOC / SCRATCH vs LOC (AUC)")
    el, lo, sc = (F[F["y_true"] == c] for c in ("EDGE_LOC", "LOC", "SCRATCH"))
    print(f"  {'특징':15s} {'EDGE_LOC|LOC':>13s} {'SCRATCH|LOC':>12s}")
    for f in ROBUST_FEATURES + ["big_r", "big_r_min", "elongation"]:
        print(f"  {f:15s} {auc_ovr(el[f].to_numpy(), lo[f].to_numpy()):13.3f} "
              f"{auc_ovr(sc[f].to_numpy(), lo[f].to_numpy()):12.3f}")

    # ── 로트 분할 5회, 4개 모델 짝지어 비교 ──
    print(f"\n{'=' * 74}\n로트 분할 {len(SEEDS)}회 반복 (시드 {SEEDS}) — test macro-F1\n{'=' * 74}")
    y = F["y_true"].to_numpy()
    X = {nm: F[feats].to_numpy() for nm, (_, feats) in MODELS.items()}
    res = {nm: [] for nm in MODELS}
    cls = {nm: [] for nm in MODELS}
    cms = {nm: np.zeros((len(CLASSES), len(CLASSES)), dtype=int) for nm in MODELS}
    gaps = {nm: [] for nm in MODELS}

    print("  " + f"{'seed':>5s} " + " ".join(f"{nm:>8s}" for nm in MODELS))
    for sd in SEEDS:
        tr, te = lot_split(F, sd)
        line = []
        for nm, (mk, _) in MODELS.items():
            m = mk().fit(X[nm][tr], y[tr])
            p = m.predict(X[nm][te])
            f1 = macro_f1(y[te], p)
            res[nm].append(f1)
            gaps[nm].append(macro_f1(y[tr], m.predict(X[nm][tr])) - f1)
            cls[nm].append(f1_score(y[te], p, average=None, labels=CLASSES, zero_division=0))
            cms[nm] += confusion_matrix(y[te], p, labels=CLASSES)
            line.append(f"{f1:8.4f}")
        print(f"  {sd:>5d} " + " ".join(line))

    res = {nm: np.array(v) for nm, v in res.items()}
    print()
    print(paired_table(res).round(4).to_string())
    print("\n  train−test 격차 평균: " +
          "  ".join(f"{nm} {np.mean(g):+.3f}" for nm, g in gaps.items()))
    print("  → 채택 기준: 5회 모두 개선이고 Δ가 기준 모델의 표준편차보다 클 것.")

    print(f"\n{'=' * 74}\n클래스별 F1 평균 (5회)\n{'=' * 74}")
    ct = pd.DataFrame({nm: np.mean(v, axis=0) for nm, v in cls.items()}, index=CLASSES)
    for nm in MODELS:
        if nm != BASELINE:
            ct[f"Δ {nm}"] = ct[nm] - ct[BASELINE]
    print(ct.round(3).to_string())

    best = max(res, key=lambda k: res[k].mean())
    print(f"\n{'=' * 74}\n{best} confusion matrix (5회 합산, 행=실제, 열=예측)\n{'=' * 74}")
    print(pd.DataFrame(cms[best], index=[f"실제 {c}" for c in CLASSES],
                       columns=[f"→{c}" for c in CLASSES]).to_string())
    el_i, lo_i, sc_i = (CLASSES.index(c) for c in ("EDGE_LOC", "LOC", "SCRATCH"))
    for nm in (BASELINE, best):
        cm = cms[nm]
        print(f"  {nm:7s} LOC→EDGE_LOC {cm[lo_i, el_i]:4d}  EDGE_LOC→LOC {cm[el_i, lo_i]:4d}  "
              f"SCRATCH→LOC {cm[sc_i, lo_i]:4d}  LOC→SCRATCH {cm[lo_i, sc_i]:4d}")

    out = pd.DataFrame({"seed": SEEDS, **{nm: v for nm, v in res.items()}})
    out.to_csv(HERE / "wm811k_improve_results.csv", index=False)
    print(f"\n저장: {HERE / 'wm811k_improve_results.csv'}\n      {CACHE3}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
