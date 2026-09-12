# wm811k_structural.py
# WM-811K — 구조적 특징 추가 및 "전역 요약 통계 vs 구조적 특징" 비교
#
# 배경 (교정 실험 결과, test macro-F1)
#   규칙 미교정 0.167 → 규칙 교정 0.540 → 결정트리 0.689 → 랜덤포레스트 0.767
#   남은 병목: SCRATCH 0.131/0.319, EDGE_LOC 0.514/0.664, LOC 0.416/0.432
#   교정이 scratch_axial을 0.50 → 0.10 까지 내린 것은 정밀도를 버리고
#   재현율만 긁은 것(precision 0.116)이며, 임계값으로는 해결 불가라는 신호다.
#
# 가설
#   SCRATCH/LOC/RANDOM은 "불량이 어디에 있나"가 아니라 "어떤 모양으로
#   연결되어 있나"로 갈린다. 전역 요약 통계(평균 반경, 각도 집중도)는
#   이 정보를 구조적으로 담을 수 없다.
#
# 추가하는 특징
#   [연결 성분] n_comp, largest_frac, elongation, comp_size_mean
#       SCRATCH  : 성분 1~2개, 세장비 극단적
#       LOC      : 성분 1개, 세장비 ≈ 1
#       RANDOM   : 성분 수십 개, 각각 작음
#   [각도 커버리지] outer_cover, outer_rate
#       외곽 환형을 24구간으로 나눠 불량이 존재하는 구간 비율.
#       EDGE_RING ≈ 1.0, EDGE_LOC ≈ 0.2~0.4. dir_c보다 직접적이다.
#   [반경 프로파일] prof0..prof4
#       반경 5구간의 불량률 / 전체 불량률. 배경 노이즈 수준에 불변이라
#       평균·표준편차보다 강건하다.
#
# 비교 설계
#   규칙(전역) / 규칙(확장) / 트리(전역) / 트리(확장)
#   확장 규칙까지 교정하는 이유: "특징을 바꾸면 수작업 규칙도 살아나는가"가
#   별개의 질문이기 때문이다. 트리만 올라가면 문제는 특징이 아니라 구조다.
#
# 누수 방지: 로트 단위 분할, 교정·깊이선택 모두 train 내부, test는 1회.

from __future__ import annotations

import os
import sys
import time
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import ndimage
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import GroupKFold
from sklearn.tree import DecisionTreeClassifier, export_text

from wafer_map_visualizer import wafermap_to_df
from wafer_pattern_classifier import classify_wafer_pattern

if sys.platform == "win32":                      # Windows 콘솔 한글 깨짐 방지
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("WM811K_DIR", HERE / "data"))   # 환경변수 또는 스크립트 옆 data/
CACHE = HERE / "wm811k_features_ext.csv"                   # 실행 폴더와 무관하게 스크립트 옆에

CLASSES = ["CENTER", "DONUT", "EDGE_LOC", "EDGE_RING",
           "LOC", "NEAR_FULL", "RANDOM", "SCRATCH"]

GLOBAL_FEATURES = ["fail_frac", "r_mean", "r_med", "r_std", "dir_c", "axial_c"]
STRUCT_FEATURES = ["n_comp", "largest_frac", "elongation", "comp_size_mean",
                   "outer_cover", "outer_rate",
                   "prof0", "prof1", "prof2", "prof3", "prof4"]
ALL_FEATURES = GLOBAL_FEATURES + STRUCT_FEATURES

LABEL_MAP = {
    "Edge-Ring": "EDGE_RING", "Edge-Loc": "EDGE_LOC", "Center": "CENTER",
    "Loc": "LOC", "Scratch": "SCRATCH", "Random": "RANDOM",
    "Donut": "DONUT", "Near-full": "NEAR_FULL",
}
MIN_DIE = 100
N_ANGLE_BINS = 24
OUTER_R = 0.75
N_RADIAL_BINS = 5


# ──────────────────────────────────────────
# 1. 구조적 특징
# ──────────────────────────────────────────
def structural_features(wmap: np.ndarray) -> dict:
    """2D 웨이퍼 맵에서 연결 성분 / 각도 커버리지 / 반경 프로파일 추출."""
    arr = np.asarray(wmap)
    die = arr > 0
    fail = arr == 2

    # 다이 영역의 바운딩 박스로 중심과 반경을 정한다.
    # 배열 중심은 다이 영역과 어긋날 수 있다.
    ys, xs = np.nonzero(die)
    cy, cx = (ys.min() + ys.max()) / 2.0, (xs.min() + xs.max()) / 2.0
    ry = max((ys.max() - ys.min()) / 2.0, 1e-9)
    rx = max((xs.max() - xs.min()) / 2.0, 1e-9)

    yy, xx = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
    # 축별로 반 폭으로 정규화 → 맵이 비정사각이어도 원판이 단위원이 된다
    rn = np.hypot((yy - cy) / ry, (xx - cx) / rx)
    ang = np.arctan2(-(yy - cy) / ry, (xx - cx) / rx)

    n_fail = int(fail.sum())
    n_die = int(die.sum())
    out = {"n_die": n_die}

    # ── 연결 성분 (8-이웃) ──
    lab, n_comp = ndimage.label(fail, structure=np.ones((3, 3), dtype=int))
    if n_comp > 0:
        sizes = np.bincount(lab.ravel())[1:]
        big = int(sizes.argmax()) + 1
        out["n_comp"] = int(n_comp)
        out["largest_frac"] = float(sizes.max() / n_fail)
        out["comp_size_mean"] = float(sizes.mean())

        # 최대 성분의 세장비 — 공분산 고윳값 비의 제곱근
        py, px = np.nonzero(lab == big)
        if len(py) >= 3:
            cov = np.cov(np.vstack([px, py]))
            ev = np.linalg.eigvalsh(cov)
            ev = np.clip(ev, 1e-9, None)
            out["elongation"] = float(np.sqrt(ev[-1] / ev[0]))
        else:
            out["elongation"] = 1.0
    else:
        out |= {"n_comp": 0, "largest_frac": 0.0,
                "comp_size_mean": 0.0, "elongation": 1.0}

    # ── 각도 커버리지 (외곽 환형) ──
    outer = die & (rn >= OUTER_R)
    if outer.sum() > 0:
        bins = ((ang[outer] + np.pi) / (2 * np.pi) * N_ANGLE_BINS).astype(int)
        bins = np.clip(bins, 0, N_ANGLE_BINS - 1)
        f_out = fail[outer]
        has_fail = np.zeros(N_ANGLE_BINS, dtype=bool)
        np.logical_or.at(has_fail, bins, f_out)
        occupied = np.bincount(bins, minlength=N_ANGLE_BINS) > 0
        out["outer_cover"] = float(has_fail[occupied].mean()) if occupied.any() else 0.0
        out["outer_rate"] = float(f_out.mean())
    else:
        out |= {"outer_cover": 0.0, "outer_rate": 0.0}

    # ── 반경 프로파일 비율 (전체 불량률로 정규화) ──
    overall = n_fail / n_die if n_die else 0.0
    edges = np.linspace(0.0, 1.0, N_RADIAL_BINS + 1)
    rn_die = rn[die]
    fail_die = fail[die]
    for b in range(N_RADIAL_BINS):
        lo, hi = edges[b], edges[b + 1]
        m = (rn_die >= lo) & (rn_die < hi if b < N_RADIAL_BINS - 1 else rn_die <= hi)
        if m.sum() >= 5 and overall > 0:
            out[f"prof{b}"] = float(fail_die[m].mean() / overall)
        else:
            out[f"prof{b}"] = 1.0        # 정보 없음 → 중립값
    return out


# ──────────────────────────────────────────
# 2. 특징 테이블
# ──────────────────────────────────────────
def build_features(path: Path | None = None) -> pd.DataFrame:
    if CACHE.exists():
        print(f"캐시 사용: {CACHE}")
        return pd.read_csv(CACHE)

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
            lambda v: str(np.asarray(v).reshape(-1)[0]) if np.asarray(v).size else None
        )
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
        except Exception:
            continue
        recs.append({
            "y_true": y, "lot": lot,
            "fail_frac": r.fail_fraction, "r_mean": r.r_mean_norm,
            "r_med": r.r_med_norm, "r_std": r.r_std_norm,
            "dir_c": r.dir_concentration, "axial_c": r.axial_concentration,
            **st,
        })
        if (i + 1) % 5000 == 0:
            print(f"  {i + 1}/{len(df)} ({time.time() - t0:.0f}s)")

    out = pd.DataFrame(recs)
    out.to_csv(CACHE, index=False, encoding="utf-8-sig")
    print(f"저장: {CACHE} ({len(out)}행, 특징 {len(ALL_FEATURES)}개)")
    return out


# ──────────────────────────────────────────
# 3. 판별력 진단
# ──────────────────────────────────────────
def auc_one_vs_rest(pos: np.ndarray, neg: np.ndarray) -> float:
    a = np.concatenate([pos, neg])
    r = pd.Series(a).rank().to_numpy()
    n1, n0 = len(pos), len(neg)
    return (r[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else 0.5


def auc_table(F: pd.DataFrame, feats: list[str]) -> pd.DataFrame:
    """|AUC-0.5|가 클수록 판별력이 크다. 0.5 아래는 방향이 반대라는 뜻."""
    rows = {}
    for cls in CLASSES:
        pos_m = F["y_true"] == cls
        rows[cls] = {
            f: round(auc_one_vs_rest(F.loc[pos_m, f].to_numpy(),
                                     F.loc[~pos_m, f].to_numpy()), 3)
            for f in feats
        }
    return pd.DataFrame(rows).T


# ──────────────────────────────────────────
# 4. 규칙 — 전역판과 확장판
# ──────────────────────────────────────────
@dataclass(frozen=True)
class RuleParams:
    clean_frac: float = 0.02
    nearfull_frac: float = 0.75
    center_r: float = 0.74
    center_std_min: float = 0.26
    edge_r: float = 0.70
    ring_std: float = 0.24
    ring_dir: float = 0.20
    donut_lo: float = 0.39
    donut_hi: float = 0.58
    donut_std: float = 0.28
    scratch_axial: float = 0.10
    scratch_dir: float = 0.20
    loc_dir: float = 0.20
    # ── 확장판에서만 사용 (use_struct=False면 무시) ──
    ring_cover_min: float = 0.70      # 전둘레 링: 각도 커버리지
    scratch_elong_min: float = 3.00   # 스크래치: 최대 성분 세장비
    scratch_largest_min: float = 0.30
    random_ncomp_min: float = 15.0    # 랜덤: 성분 개수
    center_prof0_min: float = 1.30    # 중심: 최내측 구간 불량률 비


def apply_rules(F: pd.DataFrame, p: RuleParams, use_struct: bool) -> np.ndarray:
    n = len(F)
    out = np.empty(n, dtype=object)
    done = np.zeros(n, dtype=bool)
    g = {c: F[c].to_numpy() for c in ALL_FEATURES}

    def assign(mask, label):
        m = mask & ~done
        out[m], done[m] = label, True

    assign(g["fail_frac"] <= p.clean_frac, "CLEAN")
    assign(g["fail_frac"] >= p.nearfull_frac, "NEAR_FULL")

    if use_struct:
        # 성분이 많고 각각 작으면 산발성 → 위치 기반 판정보다 먼저 걸러낸다
        assign(g["n_comp"] >= p.random_ncomp_min, "RANDOM")
        # 얇고 긴 단일 성분 → 스크래치. 각도 통계보다 직접적이다.
        assign((g["elongation"] >= p.scratch_elong_min)
               & (g["largest_frac"] >= p.scratch_largest_min), "SCRATCH")

    center = (g["r_med"] <= p.center_r) & (g["dir_c"] < p.loc_dir) \
        & (g["r_std"] >= p.center_std_min)
    if use_struct:
        center &= g["prof0"] >= p.center_prof0_min
    assign(center, "CENTER")

    edge = g["r_mean"] >= p.edge_r
    if use_struct:
        assign(edge & (g["outer_cover"] >= p.ring_cover_min), "EDGE_RING")
    else:
        assign(edge & (g["r_std"] <= p.ring_std) & (g["dir_c"] <= p.ring_dir),
               "EDGE_RING")
    assign(edge, "EDGE_LOC")

    assign((g["r_med"] >= p.donut_lo) & (g["r_med"] <= p.donut_hi)
           & (g["r_std"] <= p.donut_std) & (g["dir_c"] <= p.ring_dir), "DONUT")
    assign((g["axial_c"] >= p.scratch_axial) & (g["dir_c"] <= p.scratch_dir),
           "SCRATCH")
    assign(g["dir_c"] >= p.loc_dir, "LOC")
    out[~done] = "RANDOM"
    return out


def macro_f1(y_true, y_pred) -> float:
    return f1_score(y_true, y_pred, average="macro", labels=CLASSES,
                    zero_division=0)


GRIDS = {
    "clean_frac": np.array([0.0, 0.005, 0.01, 0.02, 0.04]),
    "nearfull_frac": np.arange(0.45, 0.91, 0.05),
    "center_r": np.arange(0.40, 0.86, 0.02),
    "center_std_min": np.array([0.0, 0.18, 0.22, 0.26, 0.30]),
    "edge_r": np.arange(0.62, 0.91, 0.02),
    "ring_std": np.arange(0.12, 0.33, 0.02),
    "ring_dir": np.arange(0.05, 0.56, 0.05),
    "donut_lo": np.arange(0.28, 0.61, 0.03),
    "donut_hi": np.arange(0.52, 0.82, 0.03),
    "donut_std": np.arange(0.14, 0.35, 0.02),
    "scratch_axial": np.arange(0.10, 0.71, 0.05),
    "scratch_dir": np.arange(0.10, 0.61, 0.05),
    "loc_dir": np.arange(0.10, 0.61, 0.05),
    "ring_cover_min": np.arange(0.40, 1.01, 0.05),
    "scratch_elong_min": np.array([1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.0, 10.0]),
    "scratch_largest_min": np.arange(0.10, 0.81, 0.10),
    "random_ncomp_min": np.array([5, 8, 10, 15, 20, 30, 50, 1e9]),
    "center_prof0_min": np.array([0.0, 1.0, 1.2, 1.5, 2.0, 3.0]),
}
STRUCT_PARAMS = {"ring_cover_min", "scratch_elong_min", "scratch_largest_min",
                 "random_ncomp_min", "center_prof0_min"}


def calibrate(tr: pd.DataFrame, use_struct: bool, passes: int = 4) -> RuleParams:
    """좌표 하강. 전역 최적을 보장하지 않는다 (파라미터 다수 + 순서 의존 규칙)."""
    best = RuleParams()
    y = tr["y_true"].to_numpy()
    best_f1 = macro_f1(y, apply_rules(tr, best, use_struct))
    names = [f.name for f in fields(RuleParams)
             if use_struct or f.name not in STRUCT_PARAMS]
    print(f"  시작 train macro-F1 {best_f1:.4f}")

    for it in range(passes):
        improved = False
        for name in names:
            cur = getattr(best, name)
            cand_f1, cand_v = best_f1, cur
            for v in GRIDS[name]:
                if abs(v - cur) < 1e-12:
                    continue
                f1 = macro_f1(y, apply_rules(tr, replace(best, **{name: float(v)}),
                                             use_struct))
                if f1 > cand_f1 + 1e-6:
                    cand_f1, cand_v = f1, float(v)
            if abs(cand_v - cur) > 1e-12:
                best, best_f1, improved = replace(best, **{name: cand_v}), cand_f1, True
        print(f"  pass {it + 1}: {best_f1:.4f}")
        if not improved:
            break
    return best


# ──────────────────────────────────────────
# 5. 트리
# ──────────────────────────────────────────
def fit_trees(tr: pd.DataFrame, feats: list[str], depths=(4, 6, 8, 10, 12, 14)):
    X, y, grp = tr[feats].to_numpy(), tr["y_true"].to_numpy(), tr["lot"].to_numpy()
    gkf = GroupKFold(n_splits=4)
    scores = {}
    for d in depths:
        s = [macro_f1(y[va], DecisionTreeClassifier(
                max_depth=d, class_weight="balanced", random_state=42)
                .fit(X[t], y[t]).predict(X[va]))
             for t, va in gkf.split(X, y, groups=grp)]
        scores[d] = float(np.mean(s))
    best_d = max(scores, key=scores.get)
    print("    inner CV: " + "  ".join(f"d{d}={v:.3f}" for d, v in scores.items())
          + f"  → {best_d}")
    tree = DecisionTreeClassifier(max_depth=best_d, class_weight="balanced",
                                  random_state=42).fit(X, y)
    rf = RandomForestClassifier(n_estimators=400, min_samples_leaf=2,
                                class_weight="balanced_subsample",
                                random_state=42, n_jobs=-1).fit(X, y)
    return tree, rf, best_d


# ──────────────────────────────────────────
def main(path: Path | None = None):
    F = build_features(path)
    print(f"\n{len(F)}행 / 로트 {F['lot'].nunique()}개 / 특징 {len(ALL_FEATURES)}개")

    rng = np.random.default_rng(42)
    lots = F["lot"].unique()
    test_lots = set(rng.choice(lots, size=int(len(lots) * 0.3), replace=False))
    F["split"] = np.where(F["lot"].isin(test_lots), "test", "train")
    tr = F[F["split"] == "train"].reset_index(drop=True)
    te = F[F["split"] == "test"].reset_index(drop=True)
    print(f"train {len(tr)} (로트 {tr['lot'].nunique()}) / "
          f"test {len(te)} (로트 {te['lot'].nunique()})")

    print(f"\n{'=' * 78}\n구조적 특징의 판별력 (AUC, 0.5 아래는 방향 반대)\n{'=' * 78}")
    print(auc_table(F, STRUCT_FEATURES).to_string())
    print(f"\n비교 — 전역 특징")
    print(auc_table(F, GLOBAL_FEATURES).to_string())

    results, preds = {}, {}

    print(f"\n{'=' * 78}\n1. 규칙 (전역 특징만) 교정\n{'=' * 78}")
    p_glob = calibrate(tr, use_struct=False)
    preds["규칙(전역)"] = apply_rules(te, p_glob, False)
    results["규칙(전역)"] = (macro_f1(tr["y_true"], apply_rules(tr, p_glob, False)),
                          macro_f1(te["y_true"], preds["규칙(전역)"]))

    print(f"\n{'=' * 78}\n2. 규칙 (전역 + 구조) 교정\n{'=' * 78}")
    p_ext = calibrate(tr, use_struct=True)
    preds["규칙(확장)"] = apply_rules(te, p_ext, True)
    results["규칙(확장)"] = (macro_f1(tr["y_true"], apply_rules(tr, p_ext, True)),
                          macro_f1(te["y_true"], preds["규칙(확장)"]))
    print("\n  교정된 구조 파라미터:")
    for k in STRUCT_PARAMS:
        print(f"    {k:22s} {getattr(p_ext, k):>8.2f}")

    print(f"\n{'=' * 78}\n3. 트리 (전역 특징만)\n{'=' * 78}")
    t_g, rf_g, _ = fit_trees(tr, GLOBAL_FEATURES)
    for nm, m in [("트리(전역)", t_g), ("RF(전역)", rf_g)]:
        preds[nm] = m.predict(te[GLOBAL_FEATURES].to_numpy())
        results[nm] = (macro_f1(tr["y_true"], m.predict(tr[GLOBAL_FEATURES].to_numpy())),
                       macro_f1(te["y_true"], preds[nm]))

    print(f"\n{'=' * 78}\n4. 트리 (전역 + 구조)\n{'=' * 78}")
    t_e, rf_e, best_d = fit_trees(tr, ALL_FEATURES)
    for nm, m in [("트리(확장)", t_e), ("RF(확장)", rf_e)]:
        preds[nm] = m.predict(te[ALL_FEATURES].to_numpy())
        results[nm] = (macro_f1(tr["y_true"], m.predict(tr[ALL_FEATURES].to_numpy())),
                       macro_f1(te["y_true"], preds[nm]))

    print("\n  특징 중요도 (RF 확장):")
    for f, imp in sorted(zip(ALL_FEATURES, rf_e.feature_importances_),
                         key=lambda kv: -kv[1]):
        tag = "구조" if f in STRUCT_FEATURES else "전역"
        print(f"    [{tag}] {f:16s} {imp:.3f}")

    print(f"\n{'=' * 78}\n5. 비교 (test macro-F1)\n{'=' * 78}")
    print(f"  {'방법':14s} {'train':>8s} {'test':>8s}")
    for k, (a, b) in results.items():
        print(f"  {k:14s} {a:8.4f} {b:8.4f}")

    print(f"\n  구조적 특징의 기여")
    print(f"    규칙: {results['규칙(전역)'][1]:.4f} → "
          f"{results['규칙(확장)'][1]:.4f}  "
          f"({results['규칙(확장)'][1] - results['규칙(전역)'][1]:+.4f})")
    print(f"    RF  : {results['RF(전역)'][1]:.4f} → "
          f"{results['RF(확장)'][1]:.4f}  "
          f"({results['RF(확장)'][1] - results['RF(전역)'][1]:+.4f})")

    print(f"\n{'=' * 78}\n6. 클래스별 F1 (test)\n{'=' * 78}")
    tab = pd.DataFrame({
        nm: f1_score(te["y_true"], pr, average=None, labels=CLASSES,
                     zero_division=0)
        for nm, pr in preds.items()
    }, index=CLASSES).round(3)
    tab["개선(RF확장-RF전역)"] = (tab["RF(확장)"] - tab["RF(전역)"]).round(3)
    print(tab.to_string())

    print(f"\n  RF(확장) test 상세:")
    print(classification_report(te["y_true"], preds["RF(확장)"], labels=CLASSES,
                                digits=3, zero_division=0))
    print("  Confusion matrix (행=실제, 열=예측)")
    print(pd.DataFrame(
        confusion_matrix(te["y_true"], preds["RF(확장)"], labels=CLASSES),
        index=[f"실제 {c}" for c in CLASSES],
        columns=[f"→{c}" for c in CLASSES]).to_string())

    print(f"\n  트리(확장) 구조 (깊이 3까지):")
    print(export_text(
        DecisionTreeClassifier(max_depth=3, class_weight="balanced",
                               random_state=42)
        .fit(tr[ALL_FEATURES].to_numpy(), tr["y_true"]),
        feature_names=ALL_FEATURES, show_weights=False))

    for nm, pr in preds.items():
        F.loc[F["split"] == "test", f"pred_{nm}"] = pr
    out_csv = HERE / "wm811k_structural_results.csv"
    F.to_csv(out_csv, index=False, encoding="utf-8-sig")
    print(f"저장: {out_csv}\n      {CACHE}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
