# prepare_wm811k.py
# LSWMD.pkl(WM-811K 원본, 약 2GB)에서 라벨 있는 웨이퍼만 추출해 작은 pkl로 저장한다.
#
# 배경
#   원본은 811,457장 중 라벨 있는 것이 172,950장(none 포함), 결함 패턴은 25,519장이다.
#   평가 스크립트마다 2GB 를 다시 읽지 않도록 한 번만 추출한다.
#
# 무엇을 하나
#   data/wm811k_labeled.pkl  라벨 있는 웨이퍼 (none 포함)
#   data/wm811k_defects.pkl  결함 패턴 8종 (none 제외) - 평가 스크립트가 쓰는 파일
#   --sample N 이면 라벨 있는 로트 중 무작위 N 로트만 남긴다 (소규모 재현·디버깅용).
#   로트 단위로 뽑는 이유: 이후 모든 분할이 로트 단위라, 웨이퍼 단위로 뽑으면 로트가 쪼개진다.
#
# 한계
#   --sample 로 만든 부분집합의 수치는 README 의 실측 수치와 다르다. 파이프라인이 도는지
#   보는 용도이며 성능 근거가 아니다.
#
# 사용법
#   python prepare_wm811k.py                                  # data/LSWMD.pkl -> data/
#   python prepare_wm811k.py path/to/LSWMD.pkl out_dir
#   python prepare_wm811k.py --sample 300 --seed 0            # 300 로트만
#
# 원본 데이터: WM-811K (MIR Lab). Kaggle "wm811k-wafer-map" 에서 LSWMD.pkl 다운로드.
# 원본 파일은 저장소에 포함하지 않는다.

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":                      # Windows 파일/파이프 리다이렉트의 cp949 오류 방지
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent


def unwrap(v):
    """WM-811K는 라벨을 (1,1) ndarray로 이중 포장한다. 빈 배열 → None."""
    a = np.asarray(v)
    return str(a.reshape(-1)[0]) if a.size else None


def sample_lots(df: pd.DataFrame, n_lots: int, seed: int = 0) -> pd.DataFrame:
    """lotName 기준 무작위 n_lots 로트만 남긴다. 로트 수가 n_lots 이하면 그대로."""
    if "lotName" not in df.columns:
        raise ValueError("lotName 열이 없어 로트 단위 추출을 할 수 없다.")
    lots = df["lotName"].astype(str).unique()
    if n_lots >= len(lots):
        return df
    keep = set(np.random.default_rng(seed).choice(lots, size=n_lots, replace=False))
    return df[df["lotName"].astype(str).isin(keep)].copy()


def prepare(src: Path, out: Path, sample: int | None = None, seed: int = 0) -> dict:
    """추출 실행. 저장한 파일 경로와 장수를 dict 로 반환."""
    out.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        sys.exit(f"{src} 가 없다. Kaggle에서 LSWMD.pkl을 받아 {src.parent}/ 에 두어라.")

    print(f"로드: {src} (원본이면 수 분 소요)")
    df = pd.read_pickle(src)

    df["ftype"] = df["failureType"].apply(unwrap)
    # 원본 컬럼명 오타(trianTestLabel)는 배포본 그대로다
    if "trianTestLabel" in df.columns:
        df["split"] = df["trianTestLabel"].apply(unwrap)

    print("\n라벨 분포:")
    print(df["ftype"].value_counts(dropna=False).to_string())

    drop = [c for c in ("failureType", "trianTestLabel") if c in df.columns]
    labeled = df[df["ftype"].notna()].drop(columns=drop)
    if sample is not None:
        n_before = labeled["lotName"].astype(str).nunique() if "lotName" in labeled.columns else 0
        labeled = sample_lots(labeled, sample, seed)
        print(f"\n--sample {sample}: 로트 {n_before} -> {labeled['lotName'].astype(str).nunique()} "
              f"(seed {seed}), {len(labeled):,}장")
    labeled.to_pickle(out / "wm811k_labeled.pkl")

    defects = labeled[labeled["ftype"] != "none"].copy()
    defects.to_pickle(out / "wm811k_defects.pkl")

    print(f"\nlabeled {len(labeled):,} -> {out / 'wm811k_labeled.pkl'}")
    print(f"defects {len(defects):,} -> {out / 'wm811k_defects.pkl'}")
    if len(defects):
        print(f"맵 크기 종류: {defects['waferMap'].apply(np.shape).nunique()}")
    print(f"저장 위치: {out.resolve()}")
    return {"labeled": out / "wm811k_labeled.pkl", "defects": out / "wm811k_defects.pkl",
            "n_labeled": len(labeled), "n_defects": len(defects)}


def _cli(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="LSWMD.pkl 에서 라벨 있는 웨이퍼만 추출")
    ap.add_argument("src", nargs="?", type=Path, default=HERE / "data" / "LSWMD.pkl",
                    help="LSWMD.pkl 경로 (기본 data/LSWMD.pkl)")
    ap.add_argument("out", nargs="?", type=Path, default=HERE / "data",
                    help="출력 폴더 (기본 data/)")
    ap.add_argument("--sample", type=int, default=None, metavar="N",
                    help="라벨 있는 로트 중 무작위 N 로트만 추출 (소규모 재현용)")
    ap.add_argument("--seed", type=int, default=0, help="--sample 의 난수 시드 (기본 0)")
    return ap.parse_args(argv)


if __name__ == "__main__":
    _a = _cli()
    prepare(_a.src, _a.out, sample=_a.sample, seed=_a.seed)
