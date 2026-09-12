# prepare_wm811k.py
# LSWMD.pkl(WM-811K 원본, 약 2GB)에서 라벨 있는 웨이퍼만 추출해 작은 pkl로 저장한다.
# 사용: python prepare_wm811k.py [LSWMD.pkl 경로] [출력 폴더]
#   기본값: data/LSWMD.pkl → data/
#
# 출력
#   data/wm811k_labeled.pkl  라벨 있는 172,950장 (none 포함)
#   data/wm811k_defects.pkl  결함 패턴 25,519장 (none 제외) — 평가 스크립트가 쓰는 파일
#
# 원본 데이터: WM-811K (MIR Lab). Kaggle "wm811k-wafer-map" 에서 LSWMD.pkl 다운로드.
# 원본 파일은 저장소에 포함하지 않는다.

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
src = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "data" / "LSWMD.pkl"
out = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "data"
out.mkdir(parents=True, exist_ok=True)

if not src.exists():
    sys.exit(f"{src} 가 없다. Kaggle에서 LSWMD.pkl을 받아 {src.parent}/ 에 두어라.")

print(f"로드: {src} (수 분 소요)")
df = pd.read_pickle(src)


def unwrap(v):
    """WM-811K는 라벨을 (1,1) ndarray로 이중 포장한다. 빈 배열 → None."""
    a = np.asarray(v)
    return str(a.reshape(-1)[0]) if a.size else None


df["ftype"] = df["failureType"].apply(unwrap)
# 원본 컬럼명 오타(trianTestLabel)는 배포본 그대로다
df["split"] = df["trianTestLabel"].apply(unwrap)

print("\n라벨 분포:")
print(df["ftype"].value_counts(dropna=False).to_string())

labeled = df[df["ftype"].notna()].drop(columns=["failureType", "trianTestLabel"])
labeled.to_pickle(out / "wm811k_labeled.pkl")

defects = labeled[labeled["ftype"] != "none"].copy()
defects.to_pickle(out / "wm811k_defects.pkl")

print(f"\nlabeled {len(labeled):,} → {out / 'wm811k_labeled.pkl'}")
print(f"defects {len(defects):,} → {out / 'wm811k_defects.pkl'}")
print(f"맵 크기 종류: {defects['waferMap'].apply(np.shape).nunique()}")
print(f"저장 위치: {out.resolve()}")
