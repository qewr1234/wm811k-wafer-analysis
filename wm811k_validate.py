# wm811k_validate.py
# WM-811K — 결과 안정성 검증 + 남은 혼동(EDGE_LOC↔LOC) 겨냥 특징 + RF 규제
#
# 배경
#   wm811k_structural.py 결과: RF(전역+구조 17개) test macro-F1 0.890 (시드 42, 단일 분할)
#   5회 반복 평균은 0.878 ± 0.008 — 시드 42가 상위권이었다.
#   남은 오류의 절반이 EDGE_LOC↔LOC 혼동(256장). RF train 0.99 / test 0.89 과적합 폭.
#
# 이 스크립트가 답하는 질문
#   Q1. 0.890은 재현되는가            → 로트 분할 시드 5개 반복, 평균±표준편차
#   Q2. EDGE_LOC↔LOC을 가를 수 있는가  → 최대 성분의 위치 특징 추가, 같은 5분할에서 짝지어 비교
#   Q3. 과적합 폭을 줄일 수 있는가      → min_samples_leaf 를 train 내부 GroupKFold로 선택
#
# 신규 특징 (최대 연결 성분 기준 — 배경 노이즈에 섞이지 않는다)
#   big_r      : 최대 성분 무게중심의 정규화 반경. LOC은 중간, EDGE_LOC은 외곽
#   big_span   : 최대 성분이 차지하는 각도 폭(도). EDGE_LOC은 호(弧)라 넓고 LOC은 좁다
#   big_r_min  : 최대 성분에서 가장 안쪽 다이의 반경. 엣지에 붙은 성분과 떠 있는 성분 구분
#
# 누수 방지: 로트 단위 분할, 규제 선택은 train 내부, 모든 비교는 같은 분할에서 짝지어.

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold

from wm811k_structural import (
    ALL_FEATURES, CLASSES, GLOBAL_FEATURES, LABEL_MAP, MIN_DIE,
    STRUCT_FEATURES, structural_features,
)
from wafer_map_visualizer import wafermap_to_df
from wafer_pattern_classifier import classify_wafer_pattern

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("WM811K_DIR", HERE / "data"))
CACHE2 = HERE / "wm811k_features_ext2.csv"

NEW_FEATURES = ["big_r", "big_span", "big_r_min"]
FEATS_A = ALL_FEATURES                     # 17개 (이전 결과 재현용)
FEATS_B = ALL_FEATURES + NEW_FEATURES      # 20개
SEEDS = [42, 0, 1, 2, 3]
LEAF_GRID = [1, 2, 4, 8, 16]


# ──────────────────────────────────────────
# 1. 신규 특징 — 최대 성분의 위치·폭
# ──────────────────────────────────────────
def largest_component_features(wmap: np.ndarray) -> dict:
    arr = np.asarray(wmap)
    die, fail = arr > 0, arr == 2
    ys, xs = np.nonzero(die)
    cy, cx = (ys.min() + ys.max()) / 2.0, (xs.min() + xs.max()) / 2.0
    ry = max((ys.max() - ys.min()) / 2.0, 1e-9)
    rx = max((xs.max() - xs.min()) / 2.0, 1e-9)

    lab, n = ndimage.label(fail, structure=np.ones((3, 3), dtype=int))
    if n == 0:
        return {"big_r": 0.0, "big_span": 0.0, "big_r_min": 0.0}
    sizes = np.bincount(lab.ravel())[1:]
    big = int(sizes.argmax()) + 1
    py, px = np.nonzero(lab == big)

    uy, ux = (py - cy) / ry, (px - cx) / rx        # 단위원 좌표
    rn = np.hypot(uy, ux)
    ang = np.arctan2(-uy, ux)                        # y 축 위가 +

    # 각도 폭 — 0/360 경계를 넘는 호를 위해 원형 통계로 계산
    c, s = np.cos(ang).mean(), np.sin(ang).mean()
    mean_ang = np.arctan2(s, c)
    dev = np.angle(np.exp(1j * (ang - mean_ang)))    # (-π, π]
    span_deg = float(np.degrees(dev.max() - dev.min())) if len(dev) > 1 else 0.0

    return {
        "big_r": float(np.hypot(uy.mean(), ux.mean())),
        "big_span": span_deg,
        "big_r_min": float(rn.min()),
    }


# ──────────────────────────────────────────
# 2. 특징 테이블 (17 + 3)
# ──────────────────────────────────────────
def build_features(path: Path | None = None) -> pd.DataFrame:
    if CACHE2.exists():
        print(f"캐시 사용: {CACHE2}")
        return pd.read_csv(CACHE2)

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
        except Exception:
            continue
        recs.append({
            "y_true": y, "lot": lot,
            "fail_frac": r.fail_fraction, "r_mean": r.r_mean_norm,
            "r_med": r.r_med_norm, "r_std": r.r_std_norm,
            "dir_c": r.dir_concentration, "axial_c": r.axial_concentration,
            **st, **nf,
        })
        if (i + 1) % 5000 == 0:
            print(f"  {i + 1}/{len(df)} ({time.time() - t0:.0f}s)")
    out = pd.DataFrame(recs)
    out.to_csv(CACHE2, index=False, encoding="utf-8-sig")
    print(f"저장: {CACHE2} ({len(out)}행, 특징 {len(FEATS_B)}개)")
    return out


# ──────────────────────────────────────────
# 3. 유틸
# ──────────────────────────────────────────
def macro_f1(y, p) -> float:
    return f1_score(y, p, average="macro", labels=CLASSES, zero_division=0)


def lot_split(F: pd.DataFrame, seed: int, test_frac: float = 0.3):
    rng = np.random.default_rng(seed)
    lots = F["lot"].unique()
    test_lots = set(rng.choice(lots, size=int(len(lots) * test_frac), replace=False))
    m = F["lot"].isin(test_lots).to_numpy()
    return np.where(~m)[0], np.where(m)[0]


def make_rf(min_leaf: int = 2) -> RandomForestClassifier:
    return RandomForestClassifier(n_estimators=400, min_samples_leaf=min_leaf,
                                  class_weight="balanced_subsample",
                                  random_state=42, n_jobs=-1)


def auc_ovr(pos, neg) -> float:
    a = np.concatenate([pos, neg]); r = pd.Series(a).rank().to_numpy()
    n1, n0 = len(pos), len(neg)
    return (r[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else 0.5


# ──────────────────────────────────────────
def main(path: Path | None = None):
    F = build_features(path)
    print(f"\n{len(F)}행 / 로트 {F['lot'].nunique()}개")

    # ── 신규 특징 판별력 (EDGE_LOC vs LOC 에만 집중) ──
    print(f"\n{'=' * 74}\n신규 특징의 판별력 — EDGE_LOC vs LOC (AUC, 0.5 아래는 방향 반대)\n{'=' * 74}")
    el, lo = F[F["y_true"] == "EDGE_LOC"], F[F["y_true"] == "LOC"]
    print(f"  {'특징':10s} {'AUC':>7s}   EDGE_LOC 중앙값   LOC 중앙값")
    for f in NEW_FEATURES + ["r_mean", "r_med"]:
        a = auc_ovr(el[f].to_numpy(), lo[f].to_numpy())
        print(f"  {f:10s} {a:7.3f}   {el[f].median():14.3f}   {lo[f].median():10.3f}")
    print("  (r_mean·r_med는 기존 특징의 같은 역할 — 신규 특징이 이보다 커야 의미가 있다)")

    # ══════════════════════════════════════
    # Q1 + Q2. 반복 로트 분할 — 17개 vs 20개, 같은 분할에서 짝지어
    # ══════════════════════════════════════
    print(f"\n{'=' * 74}\nQ1·Q2. 로트 분할 {len(SEEDS)}회 반복 (시드 {SEEDS})\n{'=' * 74}")
    y = F["y_true"].to_numpy()
    XA, XB = F[FEATS_A].to_numpy(), F[FEATS_B].to_numpy()
    resA, resB, cls_A, cls_B, cm_B = [], [], [], [], np.zeros((8, 8), dtype=int)

    print(f"  {'seed':>5s} {'RF-17개':>9s} {'RF-20개':>9s} {'Δ':>8s}")
    for sd in SEEDS:
        tr, te = lot_split(F, sd)
        pa = make_rf().fit(XA[tr], y[tr]).predict(XA[te])
        pb = make_rf().fit(XB[tr], y[tr]).predict(XB[te])
        a, b = macro_f1(y[te], pa), macro_f1(y[te], pb)
        resA.append(a); resB.append(b)
        cls_A.append(f1_score(y[te], pa, average=None, labels=CLASSES, zero_division=0))
        cls_B.append(f1_score(y[te], pb, average=None, labels=CLASSES, zero_division=0))
        cm_B += confusion_matrix(y[te], pb, labels=CLASSES)
        print(f"  {sd:>5d} {a:9.4f} {b:9.4f} {b - a:+8.4f}")

    resA, resB = np.array(resA), np.array(resB)
    d = resB - resA
    print(f"\n  RF-17개  {resA.mean():.4f} ± {resA.std(ddof=1):.4f}   (범위 {resA.min():.4f}~{resA.max():.4f})")
    print(f"  RF-20개  {resB.mean():.4f} ± {resB.std(ddof=1):.4f}   (범위 {resB.min():.4f}~{resB.max():.4f})")
    print(f"  Δ 평균 {d.mean():+.4f}, 5회 중 {int((d > 0).sum())}회 개선")
    print("  → 5회 모두 개선이고 Δ가 분할 간 표준편차보다 크면 채택. 아니면 판정 불가로 기록.")

    print(f"\n  클래스별 F1 평균 (5회)")
    tab = pd.DataFrame({"RF-17개": np.mean(cls_A, axis=0),
                        "RF-20개": np.mean(cls_B, axis=0)}, index=CLASSES)
    tab["Δ"] = tab["RF-20개"] - tab["RF-17개"]
    print(tab.round(3).to_string())

    print(f"\n  RF-20개 confusion matrix (5회 합산, 행=실제, 열=예측)")
    print(pd.DataFrame(cm_B, index=[f"실제 {c}" for c in CLASSES],
                       columns=[f"→{c}" for c in CLASSES]).to_string())
    el_i, lo_i = CLASSES.index("EDGE_LOC"), CLASSES.index("LOC")
    print(f"  EDGE_LOC↔LOC 상호 오분류: {cm_B[el_i, lo_i] + cm_B[lo_i, el_i]}장 "
          f"(5회 합산; 이전 단일 분할 256장 × 5 ≈ 1280 기준)")

    # ══════════════════════════════════════
    # Q3. 과적합 폭 — min_samples_leaf 를 train 내부에서 선택
    # ══════════════════════════════════════
    print(f"\n{'=' * 74}\nQ3. RF 규제 (min_samples_leaf, train 내부 GroupKFold 4)\n{'=' * 74}")
    tr, te = lot_split(F, 42)
    Xtr, ytr, gtr = XB[tr], y[tr], F["lot"].to_numpy()[tr]
    gkf = GroupKFold(n_splits=4)
    print(f"  {'leaf':>5s} {'inner CV':>9s} {'train':>8s} {'test':>8s} {'gap':>8s}")
    best_leaf, best_cv = None, -1
    for leaf in LEAF_GRID:
        cv = np.mean([macro_f1(ytr[v], make_rf(leaf).fit(Xtr[t], ytr[t]).predict(Xtr[v]))
                      for t, v in gkf.split(Xtr, ytr, groups=gtr)])
        m = make_rf(leaf).fit(Xtr, ytr)
        a_tr, a_te = macro_f1(ytr, m.predict(Xtr)), macro_f1(y[te], m.predict(XB[te]))
        print(f"  {leaf:>5d} {cv:9.4f} {a_tr:8.4f} {a_te:8.4f} {a_tr - a_te:+8.4f}")
        if cv > best_cv:
            best_cv, best_leaf = cv, leaf
    print(f"\n  inner CV 기준 선택: min_samples_leaf={best_leaf}")
    print("  test 열은 선택에 쓰지 않았다. 선택은 inner CV 열로만 한다.")
    print("  gap이 줄면서 test가 유지되면 규제 채택. test가 같이 떨어지면 leaf=2 유지.")

    pd.DataFrame({"seed": SEEDS, "rf17": resA, "rf20": resB}).to_csv(
        HERE / "wm811k_validate_results.csv", index=False)
    print(f"\n저장: {HERE / 'wm811k_validate_results.csv'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
