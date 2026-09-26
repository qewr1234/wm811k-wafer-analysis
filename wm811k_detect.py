# wm811k_detect.py
# 1단계 — 결함 유무 판별 (Inspection 단계). 정상(none) 웨이퍼를 포함한 전체 데이터에서
# "이 웨이퍼에 패턴이 있는가"를 먼저 판단하고, 있다고 판단한 웨이퍼만 8종 분류기로 보낸다.
#
# 왜 필요한가
#   지금까지의 스크립트는 결함 라벨이 있는 25,519장만 다뤘다. 실제 검사 흐름은 전체
#   웨이퍼(WM-811K 라벨 기준 172,950장, 그중 none 147,431장)에서 시작한다. 패턴 분류가
#   아무리 좋아도 1단계에서 놓친 웨이퍼는 분류기에 도달하지 못한다.
#
# 운영점(threshold)의 의미 — 검사 공정의 비용 구조
#   미탐(결함 → 정상): 패턴이 있는 웨이퍼가 리뷰 없이 다음 공정으로 간다. 비싸다.
#   오탐(정상 → 결함): 정상 웨이퍼가 리뷰 큐에 들어간다. 리뷰 인력과 장비 시간을 쓴다.
#   두 비용은 팹마다 다르므로 F1 최대점을 고르지 않는다. "허용 오탐률(FAR, 정상 중
#   리뷰로 보내는 비율)"을 정하고 그 조건에서 재현율(결함 중 잡는 비율)을 본다.
#   운영점은 train 내부 GroupKFold의 out-of-fold 확률로 맞추고 test는 최종 1회만 본다.
#
# 특징: 28개 (전역 6 + 구조 11 + 위치 3 + 강건 8, wm811k_improve.FEATS_ALL).
#   예상: 강건 특징(isolated_frac, sig_frac, fail_nb_mean)이 "노이즈 대 패턴"을 직접
#   재므로 1단계에서는 fail_frac 보다 유용할 것이다. 예상은 AUC로 검증하고 기록한다.
#
# 2단계 연결
#   1단계가 결함으로 판정한 웨이퍼에 RF-20(wm811k_validate 의 최종 모델)을 적용해
#   none + 8종의 9클래스 confusion matrix 를 낸다. 결함 8종 macro-F1은 end-to-end
#   (1단계에서 놓친 웨이퍼는 그 클래스의 미탐, 정상을 결함으로 보낸 웨이퍼는 그 클래스의
#   오탐)로 계산하고, 1단계를 완벽하다고 가정한 상한(2단계 단독)과 나란히 적는다.
#
# 누수 방지: 로트 단위 분할, 운영점은 train 내부, 시드 5개 반복, test 는 비교에만.
#
# 사용
#   python wm811k_detect.py                      # data/wm811k_labeled.pkl (prepare_wm811k.py 출력)
#   python wm811k_detect.py path/to/labeled.pkl --far 0.02 --workers 4

from __future__ import annotations

import argparse
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, confusion_matrix, f1_score, roc_auc_score, roc_curve
from sklearn.model_selection import GroupKFold

from wm811k_improve import FEATS_ALL, robust_features
from wm811k_structural import CLASSES, LABEL_MAP, MIN_DIE, structural_features
from wm811k_validate import FEATS_B, auc_ovr, largest_component_features, lot_split, macro_f1, make_rf
from wafer_map_visualizer import wafermap_to_df
from wafer_pattern_classifier import classify_wafer_pattern

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("WM811K_DIR", HERE / "data"))
CACHE_ALL = HERE / "wm811k_features_all.csv"

NONE = "NONE"
ALL_CLASSES = [NONE] + CLASSES
STAGE1_FEATURES = FEATS_ALL            # 28개
STAGE2_FEATURES = FEATS_B              # 20개 (wm811k_validate 최종 모델과 동일)
SEEDS = [42, 0, 1, 2, 3]
FAR_TARGETS = [0.005, 0.01, 0.02, 0.05, 0.10]
DEFAULT_FAR = 0.02
INNER_FOLDS = 4


# ──────────────────────────────────────────
# 1. 특징 추출 (none 포함 전체)
# ──────────────────────────────────────────
def extract_features(wmap: np.ndarray) -> dict | None:
    """웨이퍼 맵 한 장 → 28개 특징. 다이가 너무 적거나 퇴화된 맵은 None."""
    arr = np.asarray(wmap)
    if arr.ndim != 2 or (arr > 0).sum() < MIN_DIE:
        return None
    try:
        r = classify_wafer_pattern(wafermap_to_df(arr))
        st = structural_features(arr)
        nf = largest_component_features(arr)
        rb = robust_features(arr)
    except Exception:
        return None
    return {
        "fail_frac": r.fail_fraction, "r_mean": r.r_mean_norm,
        "r_med": r.r_med_norm, "r_std": r.r_std_norm,
        "dir_c": r.dir_concentration, "axial_c": r.axial_concentration,
        **st, **nf, **rb,
    }


def _extract_row(args):
    y, lot, wmap = args
    f = extract_features(wmap)
    return None if f is None else {"y_true": y, "lot": lot, **f}


def find_data(path: Path | None) -> Path:
    if path is not None:
        return path
    for name in ["wm811k_labeled.pkl", "LSWMD.pkl"]:
        if (DATA_DIR / name).exists():
            return DATA_DIR / name
    sys.exit(f"데이터 파일을 찾을 수 없다. {DATA_DIR} 에 wm811k_labeled.pkl 이 있어야 한다 "
             "(prepare_wm811k.py 가 만든다. none 을 포함한 파일이어야 한다).")


def build_features(path: Path | None = None, workers: int = 1, cache: Path = CACHE_ALL) -> pd.DataFrame:
    if cache.exists():
        print(f"캐시 사용: {cache}")
        return pd.read_csv(cache)

    path = find_data(path)
    print(f"로드: {path.name}")
    df = pd.read_pickle(path)
    if "ftype" not in df.columns:
        df["ftype"] = df["failureType"].apply(
            lambda v: str(np.asarray(v).reshape(-1)[0]) if np.asarray(v).size else None)
    df["lot"] = (df["lotName"] if "lotName" in df.columns else "unknown").astype(str)
    df = df[df["ftype"].isin(LABEL_MAP) | (df["ftype"] == "none")].copy()
    df["y_true"] = df["ftype"].map(LABEL_MAP).fillna(NONE)
    if (df["y_true"] == NONE).sum() == 0:
        sys.exit(f"{path.name} 에 none 웨이퍼가 없다. 1단계 검출에는 wm811k_labeled.pkl 이 필요하다.")
    print(f"  {len(df):,}장 (none {int((df['y_true'] == NONE).sum()):,}, "
          f"결함 {int((df['y_true'] != NONE).sum()):,}) — 특징 추출 시작, workers={workers}")

    jobs = list(zip(df["y_true"], df["lot"], df["waferMap"]))
    recs, t0 = [], time.time()
    if workers > 1:
        with Pool(workers) as pool:
            for i, rec in enumerate(pool.imap(_extract_row, jobs, chunksize=256)):
                if rec is not None:
                    recs.append(rec)
                if (i + 1) % 10000 == 0:
                    print(f"  {i + 1}/{len(jobs)} ({time.time() - t0:.0f}s)")
    else:
        for i, job in enumerate(jobs):
            rec = _extract_row(job)
            if rec is not None:
                recs.append(rec)
            if (i + 1) % 10000 == 0:
                print(f"  {i + 1}/{len(jobs)} ({time.time() - t0:.0f}s)")
    out = pd.DataFrame(recs)
    out.to_csv(cache, index=False, encoding="utf-8-sig")
    print(f"저장: {cache} ({len(out)}행, 특징 {len(STAGE1_FEATURES)}개, {time.time() - t0:.0f}s)")
    return out


# ──────────────────────────────────────────
# 2. 운영점 선택 — train 내부 out-of-fold 확률
# ──────────────────────────────────────────
def make_detector() -> RandomForestClassifier:
    # 2단계 RF 와 같은 설정, 트리 수만 절반. 15만 장 × 25회 적합이라 시간을 아낀다.
    return RandomForestClassifier(n_estimators=200, min_samples_leaf=2,
                                  class_weight="balanced_subsample",
                                  random_state=42, n_jobs=-1)


def defect_probability(model: RandomForestClassifier, X: np.ndarray) -> np.ndarray:
    """결함(True) 열의 확률. 학습 폴드에 결함이 없었으면 0."""
    classes = list(model.classes_)
    if True not in classes:
        return np.zeros(len(X))
    return model.predict_proba(X)[:, classes.index(True)]


def oof_probability(X: np.ndarray, y: np.ndarray, groups: np.ndarray,
                    n_splits: int = INNER_FOLDS) -> np.ndarray:
    """train 안에서 GroupKFold 로 얻은 out-of-fold 결함 확률. 운영점은 이것으로만 정한다."""
    p = np.zeros(len(y))
    n_splits = min(n_splits, len(np.unique(groups)))
    for t, v in GroupKFold(n_splits=n_splits).split(X, y, groups=groups):
        p[v] = defect_probability(make_detector().fit(X[t], y[t]), X[v])
    return p


def choose_threshold(p: np.ndarray, is_defect: np.ndarray, far: float) -> float:
    """정상 웨이퍼 중 far 비율만 결함으로 판정되도록 임계값을 정한다 (p > t 이면 결함)."""
    p_none = p[~is_defect]
    if len(p_none) == 0:
        return 0.5
    return float(np.quantile(p_none, 1.0 - far))


def recall_at_far(p: np.ndarray, is_defect: np.ndarray, far_grid: np.ndarray) -> np.ndarray:
    """test 곡선 묘사용: FAR 격자마다 재현율. 운영점 선택에는 쓰지 않는다."""
    fpr, tpr, _ = roc_curve(is_defect, p)
    return np.interp(far_grid, fpr, tpr)


# ──────────────────────────────────────────
# 3. 보고
# ──────────────────────────────────────────
def plot_operating_curve(far_grid: np.ndarray, curves: list[np.ndarray],
                         points: dict[float, tuple[float, float]], out_png: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from batch_wafer_report import setup_korean_font
    setup_korean_font()

    fig, ax = plt.subplots(figsize=(6.4, 4.2), layout="constrained")
    mean = np.mean(curves, axis=0)
    lo, hi = np.min(curves, axis=0), np.max(curves, axis=0)
    ax.fill_between(far_grid * 100, lo, hi, color="#B0BEC5", alpha=0.5, lw=0, label="시드 5개 범위")
    ax.plot(far_grid * 100, mean, color="#455A64", lw=1.4, label="test 평균")
    offsets = [(6, -24), (6, 10), (6, -40), (6, 26), (6, -56)]     # 라벨이 겹치지 않게 번갈아 배치
    for k, (far, (fx, ry)) in enumerate(points.items()):
        ax.scatter([fx * 100], [ry], s=36, color="#F44336", zorder=3)
        ax.annotate(f"FAR {far:.1%} 목표: 실제 {fx:.1%} / 재현율 {ry:.3f}",
                    (fx * 100, ry), xytext=offsets[k % len(offsets)], textcoords="offset points", fontsize=7.5)
    ax.set_xscale("log")
    ax.set_xlabel("오탐률 FAR — 정상 웨이퍼 중 리뷰로 보낸 비율 (%)")
    ax.set_ylabel("재현율 — 결함 웨이퍼 중 잡은 비율")
    ax.set_title("1단계 검출 운영점 곡선 (운영점은 train 내부에서 정함)", loc="left", fontsize=10)
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def main(path: Path | None = None, far: float = DEFAULT_FAR, workers: int = 1,
         seeds: list[int] | None = None, out_dir: Path | None = None,
         cache: Path = CACHE_ALL) -> pd.DataFrame:
    seeds = seeds or SEEDS
    out_dir = out_dir or HERE
    F = build_features(path, workers, cache)
    y = F["y_true"].to_numpy()
    is_defect = y != NONE
    lots = F["lot"].to_numpy()
    X1, X2 = F[STAGE1_FEATURES].to_numpy(), F[STAGE2_FEATURES].to_numpy()
    print(f"\n{len(F):,}장 / 로트 {F['lot'].nunique():,}개 / none {int((~is_defect).sum()):,} "
          f"/ 결함 {int(is_defect.sum()):,}")

    # ── 특징별 판별력: 결함 vs none ──
    print(f"\n{'=' * 74}\n특징별 판별력 — 결함 vs none (AUC, 0.5 아래는 방향 반대)\n{'=' * 74}")
    auc = {f: auc_ovr(F.loc[is_defect, f].to_numpy(), F.loc[~is_defect, f].to_numpy())
           for f in STAGE1_FEATURES}
    auc_s = pd.Series(auc).sort_values(key=lambda s: (s - 0.5).abs(), ascending=False)
    print(auc_s.head(10).round(3).to_string())
    print("  → 예상: isolated_frac / sig_frac / fail_nb_mean 이 fail_frac 보다 위에 있어야 한다.")

    # ── 로트 분할 반복 ──
    print(f"\n{'=' * 74}\n로트 분할 {len(seeds)}회 (시드 {seeds}) — 운영점 FAR {far:.1%}\n{'=' * 74}")
    far_grid = np.logspace(-3, np.log10(0.3), 60)
    rows, curves, points = [], [], {}
    cm9 = np.zeros((len(ALL_CLASSES), len(ALL_CLASSES)), dtype=int)
    miss_by_class = {c: [0, 0] for c in CLASSES}     # [놓친 수, 전체]
    print(f"  {'seed':>5s} {'ROC-AUC':>8s} {'PR-AUC':>7s} {'FAR실제':>8s} {'재현율':>7s} "
          f"{'리뷰비율':>8s} {'E2E F1':>7s} {'상한 F1':>7s}")
    for sd in seeds:
        tr, te = lot_split(F, sd)
        p_oof = oof_probability(X1[tr], is_defect[tr], lots[tr])
        thresholds = {f: choose_threshold(p_oof, is_defect[tr], f) for f in FAR_TARGETS + [far]}

        det = make_detector().fit(X1[tr], is_defect[tr])
        p_te = defect_probability(det, X1[te])
        d_te = is_defect[te]
        roc, ap = roc_auc_score(d_te, p_te), average_precision_score(d_te, p_te)
        curves.append(recall_at_far(p_te, d_te, far_grid))

        rec = {"seed": sd, "roc_auc": roc, "pr_auc": ap}
        for f_t, t in thresholds.items():
            flag = p_te > t
            rec[f"far_actual@{f_t}"] = float(flag[~d_te].mean())
            rec[f"recall@{f_t}"] = float(flag[d_te].mean())

        # 2단계 연결
        flag = p_te > thresholds[far]
        tr_def = tr[is_defect[tr]]
        stage2 = make_rf().fit(X2[tr_def], y[tr_def])
        y_pred = np.where(flag, stage2.predict(X2[te]), NONE)
        y_te = y[te]
        e2e = macro_f1(y_te, y_pred)
        oracle = macro_f1(y_te[d_te], stage2.predict(X2[te][d_te]))
        cm9 += confusion_matrix(y_te, y_pred, labels=ALL_CLASSES)
        for c in CLASSES:
            m = y_te == c
            miss_by_class[c][0] += int((~flag[m]).sum())
            miss_by_class[c][1] += int(m.sum())
        rec.update({"review_frac": float(flag.mean()), "e2e_macro_f1": e2e, "oracle_macro_f1": oracle,
                    "none_precision": float((y_te[y_pred == NONE] == NONE).mean()) if (y_pred == NONE).any() else 0.0,
                    "none_recall": float((y_pred[y_te == NONE] == NONE).mean())})
        rows.append(rec)
        print(f"  {sd:>5d} {roc:8.4f} {ap:7.4f} {rec[f'far_actual@{far}']:8.4f} {rec[f'recall@{far}']:7.4f} "
              f"{rec['review_frac']:8.4f} {e2e:7.4f} {oracle:7.4f}")

    R = pd.DataFrame(rows)
    print(f"\n  ROC-AUC {R['roc_auc'].mean():.4f} ± {R['roc_auc'].std(ddof=1):.4f}   "
          f"PR-AUC {R['pr_auc'].mean():.4f} ± {R['pr_auc'].std(ddof=1):.4f}")
    print(f"\n  운영점별 (train 내부 OOF 로 정한 임계값을 test 에 적용, {len(seeds)}회 평균)")
    print(f"  {'FAR 목표':>8s} {'FAR 실제':>9s} {'재현율':>8s}")
    for f_t in FAR_TARGETS:
        fa, rc = R[f"far_actual@{f_t}"].mean(), R[f"recall@{f_t}"].mean()
        print(f"  {f_t:8.1%} {fa:9.4f} {rc:8.4f}")
        points[f_t] = (fa, rc)
    print("  → FAR 실제가 목표와 크게 다르면 train 과 test 의 none 분포가 다르다는 뜻이다.")

    print(f"\n  운영점 FAR {far:.1%} 에서 1단계가 놓친 결함 (패턴별, {len(seeds)}회 합산)")
    miss = pd.DataFrame({c: {"놓침": v[0], "전체": v[1], "미탐률": v[0] / max(v[1], 1)}
                         for c, v in miss_by_class.items()}).T.sort_values("미탐률", ascending=False)
    print(miss.round(3).to_string())
    print("  → 미탐률이 높은 패턴이 1단계의 병목이다. 불량 비율이 낮은 패턴(LOC, RANDOM)이 예상 후보.")

    print(f"\n  2단계 연결 — 결함 8종 macro-F1: end-to-end {R['e2e_macro_f1'].mean():.4f} ± "
          f"{R['e2e_macro_f1'].std(ddof=1):.4f}   /   1단계 완벽 가정 상한 {R['oracle_macro_f1'].mean():.4f}")
    print(f"  none 정밀도 {R['none_precision'].mean():.4f} (정상 판정 중 실제 정상) / "
          f"none 재현율 {R['none_recall'].mean():.4f}")
    print(f"\n  9클래스 confusion matrix ({len(seeds)}회 합산, 행=실제, 열=예측)")
    print(pd.DataFrame(cm9, index=[f"실제 {c}" for c in ALL_CLASSES],
                       columns=[f"→{c}" for c in ALL_CLASSES]).to_string())

    R.to_csv(out_dir / "wm811k_detect_results.csv", index=False)
    pd.DataFrame(cm9, index=ALL_CLASSES, columns=ALL_CLASSES).to_csv(out_dir / "wm811k_detect_confusion.csv")
    plot_operating_curve(far_grid, curves, points, out_dir / "wm811k_detect_curve.png")
    print(f"\n저장: {out_dir / 'wm811k_detect_results.csv'}\n      {out_dir / 'wm811k_detect_confusion.csv'}"
          f"\n      {out_dir / 'wm811k_detect_curve.png'}")
    return R


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="1단계 결함 유무 판별 + 2단계 연결 평가")
    ap.add_argument("data", nargs="?", type=Path, help="none 을 포함한 pkl (기본 data/wm811k_labeled.pkl)")
    ap.add_argument("--far", type=float, default=DEFAULT_FAR, help="허용 오탐률 (정상 중 리뷰로 보내는 비율)")
    ap.add_argument("--workers", type=int, default=1, help="특징 추출 프로세스 수 (17만 장이면 4 이상 권장)")
    args = ap.parse_args()
    main(args.data, args.far, args.workers)
