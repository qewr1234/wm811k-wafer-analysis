# tests/synthetic_wm811k.py
# 합성 웨이퍼로 WM-811K(LSWMD.pkl) 형식의 데이터를 만든다.
#
# 용도는 파이프라인 스모크 테스트뿐이다. 생성기와 분류기가 규칙을 공유하므로
# 여기서 나오는 F1은 성능이 아니다. 실측 수치는 반드시 실제 LSWMD.pkl로 낼 것.
#
# 사용: python tests/synthetic_wm811k.py [출력 경로] [로트 수]
#   기본값: data/LSWMD_synthetic.pkl, 120 로트

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from wafer_map_visualizer import generate_sample_wafer_data  # noqa: E402

# 합성 모드 → WM-811K 라벨 문자열. loc / near_full 은 생성기에 없어 여기서 만든다.
LABELS = {
    "ring": "Edge-Ring", "center": "Center", "scratch": "Scratch", "random": "Random",
    "donut": "Donut", "edge_loc": "Edge-Loc", "loc": "Loc", "near_full": "Near-full",
}


def df_to_wafermap(df: pd.DataFrame, die_size_mm: float) -> np.ndarray:
    """die_x/die_y/status DataFrame → 0(없음)/1(정상)/2(불량) 2D 배열."""
    x = np.rint(df["die_x"].to_numpy() / die_size_mm).astype(int)
    y = np.rint(df["die_y"].to_numpy() / die_size_mm).astype(int)
    n = int(max(np.abs(x).max(), np.abs(y).max()))
    arr = np.zeros((2 * n + 1, 2 * n + 1), dtype=np.uint8)
    arr[n - y, x + n] = np.where(df["status"].to_numpy() == "FAIL", 2, 1)
    return arr


def make_wafermap(mode: str, seed: int, rng: np.random.Generator) -> np.ndarray:
    """맵 크기, 다이 크기, 노이즈를 무작위로 바꿔 WM-811K처럼 크기가 제각각인 맵을 만든다."""
    diam = float(rng.choice([200, 250, 300, 350]))
    die = float(rng.choice([8, 10, 12]))
    noise = float(rng.uniform(0.01, 0.08))
    base = "random" if mode in ("loc", "near_full") else mode
    df = generate_sample_wafer_data(wafer_diameter_mm=diam, die_size_mm=die,
                                    defect_mode=base, noise=noise, seed=seed)
    R = float(df["radius"].max())
    if mode == "loc":                          # 중간 반경에 떠 있는 덩어리
        ang0 = rng.uniform(-np.pi, np.pi)
        rc = rng.uniform(0.3, 0.65) * R
        cx, cy = rc * np.cos(ang0), rc * np.sin(ang0)
        blob = np.hypot(df["die_x"] - cx, df["die_y"] - cy) <= rng.uniform(0.12, 0.2) * R
        df.loc[blob, "status"] = "FAIL"
    elif mode == "near_full":
        p = rng.uniform(0.65, 0.9)
        df["status"] = np.where(rng.random(len(df)) < p, "FAIL", "PASS")
    return df_to_wafermap(df, die)


def make_lswmd(n_lots: int = 120, n_unlabeled: int = 50, seed: int = 0) -> pd.DataFrame:
    """LSWMD.pkl 과 같은 컬럼(waferMap, dieSize, lotName, waferIndex,
    trianTestLabel, failureType)을 가진 DataFrame. 라벨은 (1,1) ndarray 로 포장한다."""
    rng = np.random.default_rng(seed)
    modes = list(LABELS)
    rows, i = [], 0
    for lot in range(n_lots):
        lot_mode = rng.choice(modes)
        for w in range(int(rng.integers(8, 20))):
            # 같은 로트는 대체로 같은 패턴 (로트 단위 분할이 필요한 이유)
            m = lot_mode if rng.random() < 0.8 else rng.choice(modes)
            rows.append({
                "waferMap": make_wafermap(m, i, rng), "dieSize": 1.0,
                "lotName": f"lot{lot}", "waferIndex": w,
                "trianTestLabel": np.array([["Training"]]),
                "failureType": np.array([[LABELS[m]]]),
            })
            i += 1
    empty = np.array([]).reshape(0, 0)          # 원본의 라벨 없는 맵
    for k in range(n_unlabeled):
        rows.append({
            "waferMap": make_wafermap("random", 10_000 + k, rng), "dieSize": 1.0,
            "lotName": "lotX", "waferIndex": k,
            "trianTestLabel": empty, "failureType": empty,
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "data" / "LSWMD_synthetic.pkl"
    n_lots = int(sys.argv[2]) if len(sys.argv) > 2 else 120
    out.parent.mkdir(parents=True, exist_ok=True)
    df = make_lswmd(n_lots)
    df.to_pickle(out)
    labels = df["failureType"].apply(lambda a: a.reshape(-1)[0] if a.size else None)
    print(f"{len(df)}장 → {out}")
    print(labels.value_counts(dropna=False).to_string())
