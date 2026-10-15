# wm811k_evaluate.py
# WM-811K 실측 데이터로 규칙 기반 분류기 평가
#
# 배경
#   지금까지의 검증은 모두 합성 데이터였다. 생성기와 분류기가 같은 규칙을
#   공유했으므로 7/7은 성능이 아니라 코딩 오류가 없다는 확인이었다.
#   이 스크립트가 처음으로 실측 숫자를 낸다.
#
# 무엇을 하나
#   - 결함 라벨 8종(기본) 또는 none 포함(--with-none) 웨이퍼 전부를 미교정 규칙으로 분류하고
#     macro-F1 / balanced accuracy / 클래스별 표 / confusion matrix 를 출력한다.
#   - 실제 라벨별 특징 분포(중앙값)를 출력한다. 임계값을 어디로 옮겨야 하는지는
#     confusion matrix 보다 이 표에서 드러난다.
#   - 로트 크기 분포(1장 / 2~4장 / 5장 이상)와 waferIndex 별 라벨 분포를 출력한다.
#   - wm811k_predictions.csv 를 저장한다 (wm811k_spc.py 입력; wafer_index, confidence 열 포함).
#
# 평가 설계
#   - accuracy 사용 금지. WM-811K는 Edge-Ring 9,680 vs Near-full 149 로
#     65배 불균형이다. macro-F1과 balanced accuracy를 주 지표로 쓴다.
#   - macro-F1은 결함 클래스 8종(CLASSES)으로 고정해 계산한다. 예측에만
#     등장한 CLEAN을 라벨 집합에 넣으면 F1 0인 9번째 클래스가 평균을
#     끌어내려 wm811k_calibrate.py 이후의 숫자와 어긋난다(0.146 vs 0.167).
#   - balanced accuracy 도 같은 8종의 recall 평균으로 직접 계산한다. sklearn 의
#     balanced_accuracy_score 는 예측에만 있는 CLEAN 을 라벨로 세어 경고를 내고 값이 달라진다.
#   - 분류기에 학습된 파라미터가 없으므로(임계값을 이 데이터로 맞추지 않았다)
#     전체 25,519장 평가가 편향되지 않는다. 단 이후 임계값을 교정할 경우
#     반드시 lot 단위 group split의 train 쪽에서만 해야 한다.
#     같은 로트의 웨이퍼는 결함 패턴을 공유하므로 무작위 분할은 누수가 된다.
#   - 로트 분할은 제외(skipped)되지 않은 웨이퍼의 로트 목록으로 만든다.
#     wm811k_calibrate.py 가 같은 목록·같은 시드(42)로 나누므로 두 스크립트의 test 로트가 같다.
#
# 한계
#   - confidence 열은 score(규칙 분류기 휴리스틱 점수)를 복제한 것이다. 확률이 아니며,
#     RF 의 predict_proba 와 같은 의미로 읽으면 안 된다. wm811k_spc.py 가 열 이름 하나로
#     두 입력을 받기 위한 별칭이다.
#   - wafer_index 는 WM-811K 의 waferIndex 를 옮긴 것이다. 카세트/FOUP 의 물리 슬롯과
#     같다는 보장은 없다(데이터 설명에 그런 정의가 없다). 슬롯 대리 변수로만 본다.
#   - 결함 부분집합은 로트당 웨이퍼 수가 적어 로트 안의 반복·슬롯 분석은 대부분 n 이 부족하다.
#
# 사용법
#   python wm811k_evaluate.py                        # data/wm811k_defects.pkl (또는 WM811K_DIR)
#   python wm811k_evaluate.py path/to/file.pkl
#   python wm811k_evaluate.py --with-none            # none(정상) 포함 -> y_pred 에 CLEAN 이 섞인다

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score

from wafer_map_visualizer import wafermap_to_df
from wafer_pattern_classifier import classify_wafer_pattern

if sys.platform == "win32":                      # Windows 파일/파이프 리다이렉트의 cp949 오류 방지
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("WM811K_DIR", HERE / "data"))  # 환경변수 또는 스크립트 옆 data/
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
LOT_SIZE_BINS = [(1, 1, "1장"), (2, 4, "2~4장"), (5, 10 ** 9, "5장 이상")]


def _unwrap(v):
    """WM-811K의 (1,1) ndarray 포장을 벗긴다. 빈 배열은 None."""
    a = np.asarray(v)
    return str(a.reshape(-1)[0]) if a.size else None


def load_data(path: Path | None = None, include_none: bool = False) -> pd.DataFrame:
    """LSWMD 또는 미리 추출한 pkl을 읽어 waferMap/ftype/lot/wafer_index 만 남긴다.

    wafer_index 는 waferIndex 열이 있으면 숫자로, 없으면 NaN.
    """
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
    if "waferIndex" in df.columns:
        df["wafer_index"] = pd.to_numeric(df["waferIndex"], errors="coerce")
    else:
        df["wafer_index"] = np.nan

    df = df[df["ftype"].notna()].copy()
    if not include_none:
        df = df[df["ftype"] != "none"]

    df = df[df["ftype"].isin(LABEL_MAP)].copy()
    df["y_true"] = df["ftype"].map(LABEL_MAP)
    return df[["waferMap", "ftype", "y_true", "lot", "wafer_index"]].reset_index(drop=True)


def classify_all(df: pd.DataFrame) -> pd.DataFrame:
    """전체 맵을 분류하고 예측 + 특징을 반환.

    confidence 열은 score 의 복제다 (휴리스틱 점수, 확률 아님). wm811k_spc.py 가
    RF 출력(test_predictions.csv)과 같은 열 이름으로 읽게 하기 위한 별칭이다.
    """
    recs = []
    t0 = time.time()
    n = len(df)
    widx = df["wafer_index"] if "wafer_index" in df.columns else pd.Series(np.nan, index=df.index)

    for i, (wmap, y_true, lot, wi) in enumerate(
        zip(df["waferMap"], df["y_true"], df["lot"], widx)
    ):
        arr = np.asarray(wmap)
        n_die = int((arr > 0).sum())
        if arr.ndim != 2 or n_die < MIN_DIE:
            recs.append({"y_true": y_true, "lot": lot, "wafer_index": wi, "y_pred": None,
                         "n_die": n_die, "skipped": True})
            continue

        try:
            res = classify_wafer_pattern(wafermap_to_df(arr))
        except Exception as e:                     # 퇴화된 맵 방어
            recs.append({"y_true": y_true, "lot": lot, "wafer_index": wi, "y_pred": None,
                         "n_die": n_die, "skipped": True, "error": str(e)})
            continue

        recs.append({
            "y_true": y_true, "lot": lot, "wafer_index": wi, "y_pred": res.pattern,
            "n_die": n_die, "skipped": False,
            "score": res.score,
            "confidence": res.score,          # 휴리스틱 점수의 별칭 (확률 아님)
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
    """로트 단위 분할. 같은 로트가 train/test에 동시에 들어가지 않게 한다.

    로트 목록은 제외(skipped)되지 않은 행에서 만든다. wm811k_calibrate.py 는 특징
    테이블(제외 행 없음)의 로트 목록을 같은 시드로 나누므로, 이렇게 해야 두 스크립트의
    test 로트가 같아진다. 제외 행만 있는 로트는 'train' 쪽에 남는다(지표에는 안 들어간다).
    """
    src = res[~res["skipped"].astype(bool)] if "skipped" in res.columns else res
    lots = src["lot"].unique()
    rng = np.random.default_rng(seed)
    test_lots = set(rng.choice(lots, size=int(len(lots) * test_frac), replace=False))
    return res["lot"].isin(test_lots).map({True: "test", False: "train"})


def balanced_accuracy(y_true, y_pred, labels: list[str]) -> float:
    """labels 기준 recall 평균. 예측에만 있는 클래스(CLEAN)는 세지 않는다."""
    yt, yp = np.asarray(y_true), np.asarray(y_pred)
    recs = []
    for c in labels:
        m = yt == c
        if m.any():
            recs.append(float((yp[m] == c).mean()))
    return float(np.mean(recs)) if recs else 0.0


def report(res: pd.DataFrame, title: str) -> dict:
    ok = res[~res["skipped"]]
    y_true, y_pred = ok["y_true"], ok["y_pred"]
    # 표에는 CLEAN 예측 열도 보여주되, 지표는 결함 8종으로만 계산한다.
    labels = sorted(set(y_true) | set(y_pred))
    metric_labels = [c for c in CLASSES if c in set(y_true)] or CLASSES

    macro_f1 = f1_score(y_true, y_pred, average="macro", labels=metric_labels,
                        zero_division=0)
    bal_acc = balanced_accuracy(y_true, y_pred, metric_labels)
    acc = (y_true == y_pred).mean()

    print(f"\n{'=' * 74}")
    print(f"{title}  (n={len(ok)}, 제외 {int(res['skipped'].sum())})")
    print(f"{'=' * 74}")
    print(f"  macro-F1          {macro_f1:.4f}   <- 주 지표 (결함 {len(metric_labels)}종 기준)")
    print(f"  balanced accuracy {bal_acc:.4f}   (같은 {len(metric_labels)}종의 recall 평균)")
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


def lot_size_table(df: pd.DataFrame) -> pd.DataFrame:
    """로트 크기(이 데이터에 들어 있는 웨이퍼 수) 구간별 로트 수·웨이퍼 수.

    결함 부분집합은 로트당 웨이퍼가 적다. 로트 안의 반복(같은 패턴 n장)·슬롯 런 분석이
    어느 비율의 로트에서 가능한지를 먼저 보여 준다.
    """
    sizes = df.groupby("lot").size()
    rows = []
    for lo, hi, name in LOT_SIZE_BINS:
        m = (sizes >= lo) & (sizes <= hi)
        rows.append({"로트 크기": name, "로트 수": int(m.sum()), "웨이퍼 수": int(sizes[m].sum())})
    out = pd.DataFrame(rows).set_index("로트 크기")
    out["로트 비율"] = (out["로트 수"] / max(len(sizes), 1)).round(3)
    out["웨이퍼 비율"] = (out["웨이퍼 수"] / max(int(sizes.sum()), 1)).round(3)
    return out


def wafer_index_table(df: pd.DataFrame, classes: list[str] | None = None) -> pd.DataFrame | None:
    """waferIndex 별 실제 라벨 분포 (행=wafer_index, 열=라벨, 값=장수, 마지막 열=합계).

    waferIndex 는 슬롯의 대리 변수일 뿐 물리 슬롯과 같다는 보장이 없다. wafer_index 가
    전부 NaN 이면 None.
    """
    if "wafer_index" not in df.columns or df["wafer_index"].notna().sum() == 0:
        return None
    sub = df[df["wafer_index"].notna()]
    tab = pd.crosstab(sub["wafer_index"].astype(int), sub["y_true"])
    cols = [c for c in (classes or list(tab.columns)) if c in tab.columns]
    cols += [c for c in tab.columns if c not in cols]
    tab = tab[cols]
    tab["합계"] = tab.sum(axis=1)
    tab.index.name = "wafer_index"
    return tab


def main(path: Path | None = None, include_none: bool = False):
    df = load_data(path, include_none=include_none)
    print(f"평가 대상 {len(df)}장 / 로트 {df['lot'].nunique()}개")
    print("\n라벨 분포:")
    print(df["ftype"].value_counts().to_string())

    print(f"\n{'=' * 74}")
    print("로트 크기 분포 (이 데이터에 들어 있는 웨이퍼 수 기준)")
    print(f"{'=' * 74}")
    print(lot_size_table(df).to_string())
    print("  -> 1장짜리 로트에서는 로트 내 반복·슬롯 런을 볼 수 없다. 로트 단위 분석은 5장 이상에서만 의미가 있다.")

    wit = wafer_index_table(df, CLASSES + ["CLEAN"])
    print(f"\n{'=' * 74}")
    print("waferIndex 별 실제 라벨 분포 (슬롯 대리 변수. 물리 슬롯과 같다는 보장 없음)")
    print(f"{'=' * 74}")
    if wit is None:
        print("  waferIndex 열이 없어 생략")
    else:
        print(wit.to_string())
        print("  -> 특정 index 에 한 패턴이 몰리면 슬롯/핸들링 가설의 출발점이 된다. 로트당 장수가 적어 로트 층화 대신 전체 풀링이다.")

    res = classify_all(df)
    out_csv = HERE / "wm811k_predictions.csv"
    res.to_csv(out_csv, index=False, encoding="utf-8-sig")

    # 전체 평가 — 임계값을 이 데이터로 맞추지 않았으므로 편향 없음
    report(res, "전체")

    print(f"\n{'=' * 74}")
    print("실제 라벨별 특징 분포 (중앙값) - 임계값 교정의 근거")
    print(f"{'=' * 74}")
    print(feature_table(res).round(3).to_string())

    # 로트 단위 분할 — 이후 임계값 교정 시 사용할 하니스.
    # 학습된 파라미터가 없는 현 상태에서는 두 숫자가 같아야 정상이며,
    # 차이는 로트 구성에 따른 변동일 뿐이다.
    res["split"] = lot_group_split(res)
    print(f"\n{'=' * 74}")
    print("로트 단위 분할 (교정용 하니스 확인; wm811k_calibrate.py 와 같은 시드 42·같은 로트 목록)")
    print(f"{'=' * 74}")
    for s in ["train", "test"]:
        sub = res[res["split"] == s]
        ok = sub[~sub["skipped"]]
        f1 = f1_score(ok["y_true"], ok["y_pred"], average="macro",
                      labels=CLASSES, zero_division=0)
        print(f"  {s:5s} n={len(ok):6d} 로트={ok['lot'].nunique():5d} "
              f"macro-F1={f1:.4f}")

    print(f"\n저장: {out_csv}  (열: lot, wafer_index, y_true, y_pred, score, confidence=score 복제, fail_frac ...)")


def _cli(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="WM-811K 실측 데이터로 미교정 규칙 분류기 평가")
    ap.add_argument("path", nargs="?", type=Path, default=None,
                    help="pkl 경로 (기본: WM811K_DIR 또는 data/ 의 wm811k_defects.pkl)")
    ap.add_argument("--with-none", action="store_true",
                    help="none(정상) 라벨 포함. y_true/y_pred 에 CLEAN 이 들어가고 지표는 결함 8종 기준 유지")
    return ap.parse_args(argv)


if __name__ == "__main__":
    _args = _cli()
    main(_args.path, include_none=_args.with_none)
