# wm811k_calibrate.py
# WM-811K — 임계값 교정 + 결정트리 기준선 비교
#
# 배경
#   미교정 규칙 기반 분류기의 실측 macro-F1은 0.146이었다.
#   특징별 단일 AUC를 보면 신호는 존재한다(EDGE_RING r_mean 0.956,
#   NEAR_FULL fail_frac 1.000, CENTER r_mean 0.894·r_std 0.966).
#   원인은 특징 부재가 아니라 임계값이 노이즈 없는 합성 데이터에서
#   정해졌다는 것이다. 실측은 패턴 위에 산발적 불량이 깔려 있어
#   모든 반경 통계가 바깥으로, 산포가 크게 밀린다.
#
# 이 스크립트가 하는 일
#   1. 임계값을 train 로트에서만 교정하고 test 로트로 평가
#   2. 같은 특징으로 결정트리를 적합해 기준선과 비교
#
# 왜 2번이 필요한가
#   1번을 하는 순간 우리는 손으로 결정트리를 적합하는 것이다.
#   따라서 같은 특징을 받은 실제 트리와 비교해야 한다.
#   트리가 더 좋으면 수작업 규칙의 가치는 성능이 아니라 해석 가능성으로
#   좁혀지고, 그 결론도 결과다.
#
# 누수 방지
#   - 로트 단위 분할. 같은 로트의 웨이퍼는 결함 패턴을 공유한다.
#   - 임계값 탐색과 트리 깊이 선택 모두 train 안에서만 수행.
#     트리 깊이는 train 내부 GroupKFold(lot)로 고른다.
#   - test는 최종 1회만 사용.

from __future__ import annotations

import os
import sys
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.tree import DecisionTreeClassifier, export_text

from wafer_map_visualizer import wafermap_to_df
from wafer_pattern_classifier import classify_wafer_pattern

DATA_DIR = Path(os.getenv("WM811K_DIR", Path(__file__).resolve().parent / "data"))  # 환경변수 또는 스크립트 옆 data/
FEATURE_CACHE = Path("wm811k_features.csv")

CLASSES = ["CENTER", "DONUT", "EDGE_LOC", "EDGE_RING",
           "LOC", "NEAR_FULL", "RANDOM", "SCRATCH"]
FEATURES = ["fail_frac", "r_mean", "r_med", "r_std", "dir_c", "axial_c"]

LABEL_MAP = {
    "Edge-Ring": "EDGE_RING", "Edge-Loc": "EDGE_LOC", "Center": "CENTER",
    "Loc": "LOC", "Scratch": "SCRATCH", "Random": "RANDOM",
    "Donut": "DONUT", "Near-full": "NEAR_FULL",
}
MIN_DIE = 100


# ──────────────────────────────────────────
# 1. 특징 추출 (캐시)
# ──────────────────────────────────────────
def build_features(path: Path | None = None) -> pd.DataFrame:
    if FEATURE_CACHE.exists():
        print(f"특징 캐시 사용: {FEATURE_CACHE}")
        return pd.read_csv(FEATURE_CACHE)

    if path is None:
        for name in ["wm811k_defects.pkl", "LSWMD.pkl"]:
            if (DATA_DIR / name).exists():
                path = DATA_DIR / name
                break
        else:
            sys.exit("데이터 파일을 찾을 수 없다.")

    print(f"로드: {path.name}")
    df = pd.read_pickle(path)
    if "ftype" not in df.columns:
        df["ftype"] = df["failureType"].apply(
            lambda v: str(np.asarray(v).reshape(-1)[0]) if np.asarray(v).size else None
        )
    df["lot"] = df.get("lotName", "unknown").astype(str)
    df = df[df["ftype"].isin(LABEL_MAP)].copy()
    df["y_true"] = df["ftype"].map(LABEL_MAP)

    recs, t0 = [], time.time()
    for i, (wmap, y, lot) in enumerate(zip(df["waferMap"], df["y_true"], df["lot"])):
        arr = np.asarray(wmap)
        if arr.ndim != 2 or (arr > 0).sum() < MIN_DIE:
            continue
        try:
            r = classify_wafer_pattern(wafermap_to_df(arr))
        except Exception:
            continue
        recs.append({
            "y_true": y, "lot": lot, "n_die": int((arr > 0).sum()),
            "fail_frac": r.fail_fraction,
            "r_mean": r.r_mean_norm, "r_med": r.r_med_norm, "r_std": r.r_std_norm,
            "dir_c": r.dir_concentration, "axial_c": r.axial_concentration,
            "y_rule_default": r.pattern,
        })
        if (i + 1) % 5000 == 0:
            print(f"  {i + 1}/{len(df)} ({time.time() - t0:.0f}s)")

    out = pd.DataFrame(recs)
    out.to_csv(FEATURE_CACHE, index=False, encoding="utf-8-sig")
    print(f"특징 저장: {FEATURE_CACHE} ({len(out)}행)")
    return out


# ──────────────────────────────────────────
# 2. 규칙을 파라미터화 (벡터 연산)
# ──────────────────────────────────────────
@dataclass(frozen=True)
class Thresholds:
    clean_frac: float = 0.02
    nearfull_frac: float = 0.60
    center_r: float = 0.30
    center_std_min: float = 0.00      # 0이면 무제약 (CENTER는 r_std가 크다)
    edge_r: float = 0.70
    ring_std: float = 0.15
    ring_dir: float = 0.45
    donut_lo: float = 0.35
    donut_hi: float = 0.70
    donut_std: float = 0.16
    scratch_axial: float = 0.50
    scratch_dir: float = 0.35
    loc_dir: float = 0.50


def apply_rules(F: pd.DataFrame, p: Thresholds) -> np.ndarray:
    """분류기와 동일한 판정 순서를 벡터 연산으로 재현."""
    n = len(F)
    out = np.empty(n, dtype=object)
    done = np.zeros(n, dtype=bool)

    ff = F["fail_frac"].to_numpy()
    rm, rmed, rs = (F[c].to_numpy() for c in ("r_mean", "r_med", "r_std"))
    dc, ac = F["dir_c"].to_numpy(), F["axial_c"].to_numpy()

    def assign(mask: np.ndarray, label: str):
        m = mask & ~done
        out[m] = label
        done[m] = True

    assign(ff <= p.clean_frac, "CLEAN")
    assign(ff >= p.nearfull_frac, "NEAR_FULL")
    assign((rmed <= p.center_r) & (dc < p.loc_dir) & (rs >= p.center_std_min),
           "CENTER")

    edge = rm >= p.edge_r
    assign(edge & (rs <= p.ring_std) & (dc <= p.ring_dir), "EDGE_RING")
    assign(edge, "EDGE_LOC")

    assign((rmed >= p.donut_lo) & (rmed <= p.donut_hi)
           & (rs <= p.donut_std) & (dc <= p.ring_dir), "DONUT")
    assign((ac >= p.scratch_axial) & (dc <= p.scratch_dir), "SCRATCH")
    assign(dc >= p.loc_dir, "LOC")
    out[~done] = "RANDOM"
    return out


def macro_f1(y_true, y_pred) -> float:
    return f1_score(y_true, y_pred, average="macro", labels=CLASSES,
                    zero_division=0)


# ──────────────────────────────────────────
# 3. 좌표 하강 교정 (train 전용)
# ──────────────────────────────────────────
GRIDS: dict[str, np.ndarray] = {
    "clean_frac": np.array([0.0, 0.005, 0.01, 0.02, 0.04]),
    "nearfull_frac": np.arange(0.45, 0.91, 0.05),
    "center_r": np.arange(0.40, 0.76, 0.02),
    "center_std_min": np.array([0.0, 0.20, 0.24, 0.26, 0.28, 0.30]),
    "edge_r": np.arange(0.68, 0.91, 0.02),
    "ring_std": np.arange(0.12, 0.31, 0.01),
    "ring_dir": np.arange(0.05, 0.51, 0.05),
    "donut_lo": np.arange(0.30, 0.61, 0.03),
    "donut_hi": np.arange(0.55, 0.81, 0.03),
    "donut_std": np.arange(0.14, 0.33, 0.02),
    "scratch_axial": np.arange(0.10, 0.61, 0.05),
    "scratch_dir": np.arange(0.10, 0.61, 0.05),
    "loc_dir": np.arange(0.10, 0.61, 0.05),
}


def calibrate(tr: pd.DataFrame, passes: int = 4, verbose: bool = True) -> Thresholds:
    """좌표 하강. 한 파라미터씩 격자 탐색하며 train macro-F1을 최대화한다.

    전역 최적을 보장하지 않는다. 파라미터가 13개라 전체 격자는 불가능하고,
    순서 의존적인 규칙 구조라 상호작용도 있다. 그래서 트리 기준선이 필요하다.
    """
    best = Thresholds()
    y = tr["y_true"].to_numpy()
    best_f1 = macro_f1(y, apply_rules(tr, best))
    if verbose:
        print(f"  교정 전 train macro-F1 {best_f1:.4f}")

    for it in range(passes):
        improved = False
        for name, grid in GRIDS.items():
            cur = getattr(best, name)
            cand_best, cand_val = best_f1, cur
            for v in grid:
                if v == cur:
                    continue
                f1 = macro_f1(y, apply_rules(tr, replace(best, **{name: float(v)})))
                if f1 > cand_best + 1e-6:
                    cand_best, cand_val = f1, float(v)
            if cand_val != cur:
                best = replace(best, **{name: cand_val})
                best_f1, improved = cand_best, True
        if verbose:
            print(f"  pass {it + 1}: train macro-F1 {best_f1:.4f}")
        if not improved:
            break
    return best


# ──────────────────────────────────────────
# 4. 트리 기준선 — 깊이는 train 내부 GroupKFold로 선택
# ──────────────────────────────────────────
def fit_tree_baseline(tr: pd.DataFrame, depths=(3, 4, 5, 6, 8, 10)):
    X, y, g = tr[FEATURES].to_numpy(), tr["y_true"].to_numpy(), tr["lot"].to_numpy()
    gkf = GroupKFold(n_splits=4)

    scores = {}
    for d in depths:
        fold = []
        for tri, vai in gkf.split(X, y, groups=g):
            m = DecisionTreeClassifier(max_depth=d, class_weight="balanced",
                                       random_state=42).fit(X[tri], y[tri])
            fold.append(macro_f1(y[vai], m.predict(X[vai])))
        scores[d] = float(np.mean(fold))
        print(f"    max_depth={d:2d}  inner CV macro-F1 {scores[d]:.4f}")

    best_d = max(scores, key=scores.get)
    print(f"    선택: max_depth={best_d}")
    tree = DecisionTreeClassifier(max_depth=best_d, class_weight="balanced",
                                  random_state=42).fit(X, y)

    rf = RandomForestClassifier(n_estimators=300, min_samples_leaf=2,
                                class_weight="balanced_subsample",
                                random_state=42, n_jobs=-1).fit(X, y)
    return tree, rf, best_d


# ──────────────────────────────────────────
def main(path: Path | None = None):
    F = build_features(path)
    print(f"\n특징 테이블 {len(F)}행 / 로트 {F['lot'].nunique()}개")

    # 로트 단위 분할 — wm811k_evaluate.py와 동일한 시드
    rng = np.random.default_rng(42)
    lots = F["lot"].unique()
    test_lots = set(rng.choice(lots, size=int(len(lots) * 0.3), replace=False))
    F["split"] = np.where(F["lot"].isin(test_lots), "test", "train")
    tr = F[F["split"] == "train"].reset_index(drop=True)
    te = F[F["split"] == "test"].reset_index(drop=True)
    print(f"train {len(tr)} (로트 {tr['lot'].nunique()}) / "
          f"test {len(te)} (로트 {te['lot'].nunique()})")

    results = {}

    # ── 1. 미교정 규칙 ──
    print(f"\n{'=' * 74}\n1. 미교정 규칙 (합성 데이터 기준 임계값)\n{'=' * 74}")
    base = Thresholds()
    results["규칙(미교정)"] = (
        macro_f1(tr["y_true"], apply_rules(tr, base)),
        macro_f1(te["y_true"], apply_rules(te, base)),
    )
    print(f"  train {results['규칙(미교정)'][0]:.4f} / "
          f"test {results['규칙(미교정)'][1]:.4f}")

    # ── 2. 교정 ──
    print(f"\n{'=' * 74}\n2. 임계값 교정 (train 로트 전용)\n{'=' * 74}")
    tuned = calibrate(tr)
    results["규칙(교정)"] = (
        macro_f1(tr["y_true"], apply_rules(tr, tuned)),
        macro_f1(te["y_true"], apply_rules(te, tuned)),
    )
    print(f"\n  교정된 임계값:")
    for k, v in asdict(tuned).items():
        mark = "  <- 변경" if v != getattr(base, k) else ""
        print(f"    {k:16s} {getattr(base, k):>6.3f} → {v:>6.3f}{mark}")
    print(f"\n  train {results['규칙(교정)'][0]:.4f} / "
          f"test {results['규칙(교정)'][1]:.4f}")

    y_pred_te = apply_rules(te, tuned)
    print("\n  test 클래스별:")
    print(classification_report(te["y_true"], y_pred_te, labels=CLASSES,
                                digits=3, zero_division=0))
    cm = confusion_matrix(te["y_true"], y_pred_te, labels=CLASSES)
    print("  Confusion matrix (행=실제, 열=예측)")
    print(pd.DataFrame(cm, index=[f"실제 {c}" for c in CLASSES],
                       columns=[f"→{c}" for c in CLASSES]).to_string())

    # ── 3. 트리 기준선 ──
    print(f"\n{'=' * 74}\n3. 결정트리 기준선 (동일 특징 6개)\n{'=' * 74}")
    tree, rf, best_d = fit_tree_baseline(tr)
    for name, model in [("결정트리", tree), ("랜덤포레스트", rf)]:
        results[name] = (
            macro_f1(tr["y_true"], model.predict(tr[FEATURES].to_numpy())),
            macro_f1(te["y_true"], model.predict(te[FEATURES].to_numpy())),
        )
    print(f"\n  결정트리 test 클래스별:")
    print(classification_report(te["y_true"], tree.predict(te[FEATURES].to_numpy()),
                                labels=CLASSES, digits=3, zero_division=0))

    print("  특징 중요도 (랜덤포레스트):")
    for f, imp in sorted(zip(FEATURES, rf.feature_importances_),
                         key=lambda kv: -kv[1]):
        print(f"    {f:12s} {imp:.3f}")

    # ── 4. 비교 ──
    print(f"\n{'=' * 74}\n4. 비교 (macro-F1)\n{'=' * 74}")
    print(f"  {'방법':16s} {'train':>8s} {'test':>8s}")
    for k, (a, b) in results.items():
        print(f"  {k:16s} {a:8.4f} {b:8.4f}")

    gap = results["랜덤포레스트"][1] - results["규칙(교정)"][1]
    print(f"\n  랜덤포레스트 − 교정규칙 = {gap:+.4f}")
    if gap > 0.03:
        print("  → 규칙 구조가 정보를 잃고 있다. 수작업 규칙의 가치는")
        print("     성능이 아니라 해석 가능성으로 좁혀진다.")
    elif gap < -0.03:
        print("  → 규칙이 트리보다 낫다. 도메인 구조를 넣은 효과가 있다.")
    else:
        print("  → 두 방법이 동등. 규칙은 해석 가능성 면에서 우위.")

    print(f"\n  참고: 트리 구조 (max_depth={min(best_d, 3)}까지만 표시)")
    print(export_text(
        DecisionTreeClassifier(max_depth=min(best_d, 3), class_weight="balanced",
                               random_state=42).fit(tr[FEATURES].to_numpy(),
                                                    tr["y_true"]),
        feature_names=FEATURES, show_weights=False,
    ))

    F["y_rule_tuned"] = apply_rules(F, tuned)
    F["y_tree"] = tree.predict(F[FEATURES].to_numpy())
    F.to_csv("wm811k_calibrated.csv", index=False, encoding="utf-8-sig")
    print("저장: wm811k_calibrated.csv, wm811k_features.csv")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
