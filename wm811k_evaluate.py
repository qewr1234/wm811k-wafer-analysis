# wm811k_evaluate.py
# WM-811K 실측 데이터로 규칙 기반 분류기 평가
#
# 지금까지의 검증은 모두 합성 데이터였다. 생성기와 분류기가 같은 규칙을
# 공유했으므로 7/7은 성능이 아니라 코딩 오류가 없다는 확인이었다.
# 이 스크립트가 처음으로 실측 숫자를 낸다.
#
# 평가 설계
#   - accuracy 사용 금지. WM-811K는 Edge-Ring 9,680 vs Near-full 149 로
#     65배 불균형이다. macro-F1과 balanced accuracy를 주 지표로 쓴다.
#   - macro-F1은 결함 클래스 8종(CLASSES)으로 고정해 계산한다. 예측에만
#     등장한 CLEAN을 라벨 집합에 넣으면 F1 0인 9번째 클래스가 평균을
#     끌어내려 wm811k_calibrate.py 이후의 숫자와 어긋난다(0.146 vs 0.167).
#   - 분류기에 학습된 파라미터가 없으므로(임계값을 이 데이터로 맞추지 않았다)
#     전체 25,519장 평가가 편향되지 않는다. 단 이후 임계값을 교정할 경우
#     반드시 lot 단위 group split의 train 쪽에서만 해야 한다.
#     같은 로트의 웨이퍼는 결함 패턴을 공유하므로 무작위 분할은 누수가 된다.
#   - 클래스별 특징 분포를 함께 출력한다. 어디를 고쳐야 하는지는
#     confusion matrix보다 이 표에서 드러난다.

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

from wafer_map_visualizer import wafermap_to_df
from wafer_pattern_classifier import classify_wafer_pattern

DATA_DIR = Path(os.getenv("WM811K_DIR", Path(__file__).resolve().parent / "data"))  # 환경변수 또는 스크립트 옆 data/
CANDIDATES = ["wm811k_defects.pkl", "wm811k_labeled.pkl", "LSWMD.pkl"]

# 실측 라벨 → 분류기 출력 클래스
LABEL_MAP = {
    "Edge-Ring": "EDGE_RING",
    "Edge-Loc": "EDGE_LOC",
    "Center": "CENTER",
    "Loc": "LOC",
    "Scratch": "SCRATCH",
    "Random": "RANDOM",
    "Donut": "DONUT",
    "Near-full": "NEAR_FULL",
    "none": "CLEAN",
}
MIN_DIE = 100          # 다이가 너무 적은 맵은 반경 통계가 불안정하다
# macro-F1 계산에 쓰는 클래스. 교정 스크립트들과 동일하게 결함 8종으로 고정한다.
CLASSES = ["CENTER", "DONUT", "EDGE_LOC", "EDGE_RING",
           "LOC", "NEAR_FULL", "RANDOM", "SCRATCH"]


def _unwrap(v):
    """WM-811K의 (1,1) ndarray 포장을 벗긴다. 빈 배열은 None."""
    a = np.asarray(v)
    return str(a.reshape(-1)[0]) if a.size else None


def load_data(path: Path | None = None, include_none: bool = False) -> pd.DataFrame:
    """LSWMD 또는 미리 추출한 pkl을 읽어 waferMap/ftype/lotName만 남긴다."""
    if path is None:
        for name in CANDIDATES:
            p = DATA_DIR / name
            if p.exists():
                path = p
                break
        else:
            sys.exit(f"데이터 파일을 찾을 수 없다. {CANDIDATES} 중 하나를 "
                     f"{DATA_DIR} 에 두거나 경로를 인자로 넘겨라.")

    print(f"로드: {path.name}")
    df = pd.read_pickle(path)

    if "ftype" not in df.columns:
        df["ftype"] = df["failureType"].apply(_unwrap)
    if "lotName" in df.columns:
        df["lot"] = df["lotName"].astype(str)
    else:
        df["lot"] = "unknown"

    df = df[df["ftype"].notna()].copy()
    if not include_none:
        df = df[df["ftype"] != "none"]

    df = df[df["ftype"].isin(LABEL_MAP)].copy()
    df["y_true"] = df["ftype"].map(LABEL_MAP)
    return df[["waferMap", "ftype", "y_true", "lot"]].reset_index(drop=True)


def classify_all(df: pd.DataFrame) -> pd.DataFrame:
    """전체 맵을 분류하고 예측 + 특징을 반환."""
    recs = []
    t0 = time.time()
    n = len(df)

    for i, (wmap, y_true, lot) in enumerate(
        zip(df["waferMap"], df["y_true"], df["lot"])
    ):
        arr = np.asarray(wmap)
        n_die = int((arr > 0).sum())
        if arr.ndim != 2 or n_die < MIN_DIE:
            recs.append({"y_true": y_true, "lot": lot, "y_pred": None,
                         "n_die": n_die, "skipped": True})
            continue

        try:
            res = classify_wafer_pattern(wafermap_to_df(arr))
        except Exception as e:                     # 퇴화된 맵 방어
            recs.append({"y_true": y_true, "lot": lot, "y_pred": None,
                         "n_die": n_die, "skipped": True, "error": str(e)})
            continue

        recs.append({
            "y_true": y_true, "lot": lot, "y_pred": res.pattern,
            "n_die": n_die, "skipped": False,
            "score": res.score,
            "fail_frac": res.fail_fraction,
            "r_mean_norm": res.r_mean_norm,
            "r_std_norm": res.r_std_norm,
            "dir_conc": res.dir_concentration,
            "axial_conc": res.axial_concentration,
        })

        if (i + 1) % 2000 == 0:
            el = time.time() - t0
            print(f"  {i + 1}/{n}  ({el:.0f}s, 남은 시간 약 "
                  f"{el / (i + 1) * (n - i - 1):.0f}s)")

    print(f"  완료 {n}장 / {time.time() - t0:.0f}s")
    return pd.DataFrame(recs)


def lot_group_split(res: pd.DataFrame, test_frac: float = 0.3,
                    seed: int = 42) -> pd.Series:
    """로트 단위 분할. 같은 로트가 train/test에 동시에 들어가지 않게 한다."""
    lots = res["lot"].unique()
    rng = np.random.default_rng(seed)
    test_lots = set(rng.choice(lots, size=int(len(lots) * test_frac), replace=False))
    return res["lot"].isin(test_lots).map({True: "test", False: "train"})


def report(res: pd.DataFrame, title: str) -> dict:
    ok = res[~res["skipped"]]
    y_true, y_pred = ok["y_true"], ok["y_pred"]
    # 표에는 CLEAN 예측 열도 보여주되, 지표는 결함 8종으로만 계산한다.
    labels = sorted(set(y_true) | set(y_pred))
    metric_labels = [c for c in CLASSES if c in set(y_true)] or CLASSES

    macro_f1 = f1_score(y_true, y_pred, average="macro", labels=metric_labels,
                        zero_division=0)
    bal_acc = balanced_accuracy_score(y_true, y_pred)
    acc = (y_true == y_pred).mean()

    print(f"\n{'=' * 74}")
    print(f"{title}  (n={len(ok)}, 제외 {int(res['skipped'].sum())})")
    print(f"{'=' * 74}")
    print(f"  macro-F1          {macro_f1:.4f}   ← 주 지표")
    print(f"  balanced accuracy {bal_acc:.4f}")
    print(f"  accuracy          {acc:.4f}   (불균형 데이터라 참고용)")

    print("\n클래스별:")
    print(classification_report(y_true, y_pred, labels=labels, digits=3,
                                zero_division=0))

    cm = confusion_matrix(y_true, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=[f"실제 {l}" for l in labels],
                         columns=[f"→{l}" for l in labels])
    print("Confusion matrix (행=실제, 열=예측)")
    print(cm_df.to_string())

    return {"macro_f1": macro_f1, "balanced_acc": bal_acc, "accuracy": acc}


def feature_table(res: pd.DataFrame) -> pd.DataFrame:
    """실제 라벨별 특징 분포. 임계값을 어디로 옮겨야 하는지가 여기서 보인다."""
    ok = res[~res["skipped"]]
    tbl = ok.groupby("y_true").agg(
        n=("y_pred", "size"),
        fail_frac=("fail_frac", "median"),
        r_mean=("r_mean_norm", "median"),
        r_std=("r_std_norm", "median"),
        dir_c=("dir_conc", "median"),
        axial_c=("axial_conc", "median"),
    )
    tbl["recall"] = [
        (ok.loc[ok["y_true"] == c, "y_pred"] == c).mean() for c in tbl.index
    ]
    return tbl[["n", "recall", "fail_frac", "r_mean", "r_std", "dir_c", "axial_c"]]


def main(path: Path | None = None, include_none: bool = False):
    df = load_data(path, include_none=include_none)
    print(f"평가 대상 {len(df)}장 / 로트 {df['lot'].nunique()}개")
    print("\n라벨 분포:")
    print(df["ftype"].value_counts().to_string())

    res = classify_all(df)
    out_csv = Path(__file__).resolve().parent / "wm811k_predictions.csv"
    res.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # 전체 평가 — 임계값을 이 데이터로 맞추지 않았으므로 편향 없음
    report(res, "전체")

    print(f"\n{'=' * 74}")
    print("실제 라벨별 특징 분포 (중앙값) — 임계값 교정의 근거")
    print(f"{'=' * 74}")
    print(feature_table(res).round(3).to_string())

    # 로트 단위 분할 — 이후 임계값 교정 시 사용할 하니스.
    # 학습된 파라미터가 없는 현 상태에서는 두 숫자가 같아야 정상이며,
    # 차이는 로트 구성에 따른 변동일 뿐이다.
    res["split"] = lot_group_split(res)
    print(f"\n{'=' * 74}")
    print("로트 단위 분할 (교정용 하니스 확인)")
    print(f"{'=' * 74}")
    for s in ["train", "test"]:
        sub = res[res["split"] == s]
        ok = sub[~sub["skipped"]]
        f1 = f1_score(ok["y_true"], ok["y_pred"], average="macro",
                      labels=CLASSES, zero_division=0)
        print(f"  {s:5s} n={len(ok):6d} 로트={sub['lot'].nunique():5d} "
              f"macro-F1={f1:.4f}")

    print(f"\n저장: {out_csv}")


if __name__ == "__main__":
    arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(arg, include_none="--with-none" in sys.argv)
