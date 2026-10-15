# wm811k_slot.py
# 슬롯 의존성 검정 - 패턴 발생률이 보트/카세트의 끝 슬롯에 몰리는가, 슬롯 순번을 따라 단조 변하는가
#
# 배경
#   배치 퍼니스(TEL 제품으로는 TELINDY PLUS 계열)는 한 보트에 수십~백여 장을 세워 한 번에
#   처리하므로, 한 장의 맵 모양보다 "같은 배치 안에서 슬롯 위치(상/중/하)에 따라 패턴 비율이
#   달라지는가"가 장비 서명이다. 보트 양끝은 온도 램프·가스 고갈(depletion)·더미 웨이퍼와의
#   경계 조건이 가운데와 달라 끝 슬롯에 EDGE_RING 폭이 넓어지거나 막 두께가 틀어지는 식으로
#   나타나고(공개 특허·교과서 수준의 일반 물리), 단조 기울기는 보트 축 방향 온도·가스 구배의
#   서명이다. docs/defect_signatures.md 현장 순서 2번이 "슬롯 위치와의 상관을 본다"고 적고
#   있었으나 코드가 없었다. 이 모듈은 그 검정을 코드로 고정한다.
#
#   WM-811K 에 대해 (중요): 예측 CSV 의 wafer_index 는 WM-811K 의 waferIndex 를 옮긴 것이다.
#   이 값이 FOUP/보트의 물리 슬롯과 같다는 정의는 데이터셋 설명에 없다. 여기서는 슬롯의
#   '대리 변수'로만 쓰고, 모든 출력에 그렇게 적는다. 실제 팹 데이터에서는 MES 의 슬롯 번호
#   열을 --slot-col 로 넘긴다.
#
# 무엇을 하나
#   slot_rate_table   슬롯별 n, 패턴 장수 k, 발생률, Wilson 95% 구간, 전체 발생률 대비 비.
#   end_slot_test     끝 슬롯(기본 1,2,3,23,24,25 - 25매 캐리어 가정) vs 가운데 2x2.
#                       odds_ratio, p_pooled(기대도수 >= 5 면 카이제곱, 아니면 Fisher),
#                       p_cluster(로트 안에서 슬롯 라벨을 섞는 로트 층화 순열 검정), n_end, n_mid,
#                       n_lots_informative(순열에 실제로 기여한 로트 수).
#   slot_trend_test   슬롯 순번과 패턴 발생의 Spearman 상관 (단조 기울기 = 구배 서명).
#   plot_slot_profile 슬롯별 발생률 막대 + Wilson 구간 + 전체 발생률 선. 라벨은 영문(폰트 무관).
#   CLI               predictions.csv (lot, wafer_index, y_pred) --pattern EDGE_RING --output DIR.
#                     --demo 는 합성 3시나리오(끝 슬롯 +50% / 효과 없음 / 로트 혼입)로 로직 확인.
#
# 왜 p 값이 둘인가 (p_pooled 와 p_cluster)
#   같은 로트의 웨이퍼는 패턴을 공유한다. 로트마다 모든 슬롯이 고르게 들어 있으면(완전한 로트)
#   슬롯과 로트가 직교해 풀링한 2x2 검정이 대체로 맞다. 그러나 결함 부분집합처럼 로트마다
#   일부 슬롯만 남아 있으면, "패턴 있는 로트의 남은 웨이퍼가 우연히 끝 슬롯"인 것만으로
#   풀링 검정이 울린다(로트 혼입). 로트 안에서 슬롯 라벨만 섞는 순열 검정은 로트가 공유하는
#   패턴을 그대로 둔 채 슬롯 효과만 검정하므로 이 혼입에 속지 않는다. 두 p 가 갈리면
#   (p_pooled 작고 p_cluster 큼) 그것 자체가 '로트 효과이지 슬롯 효과가 아니다'는 진단이다.
#
#   로트 층화 CMH(Cochran-Mantel-Haenszel)를 쓰지 않는 이유: CMH 는 층(로트)마다 2x2 가
#   채워져야 하는데 WM-811K 결함 부분집합은 로트당 평균 3.2장(25,519 / 8,047)이라 대부분
#   층이 한 칸짜리로 비고, 공통 오즈비 추정량이 희소 층에서 불안정하다. 순열 검정도 같은
#   정보 한계(웨이퍼가 2장 이상이고 끝·가운데가 섞인 로트만 기여)를 갖지만 희소 층에서도
#   정확한 p 를 주고, 기여한 로트 수(n_lots_informative)를 함께 내서 "검정력이 없었다"를
#   숨기지 않는다.
#
# 한계
#   - 합성(--demo, tests/)은 로직 확인이지 탐지 성능이 아니다.
#   - end_slots 기본값은 25매 캐리어 가정이다. 관측된 슬롯 범위가 1~25 를 벗어나면 CLI 가
#     양끝 3개씩으로 바꾸고 그 사실을 출력한다(--end-slots 로 명시 권장).
#   - slot_trend_test 의 p 는 풀링 p 다. 로트 혼입 의심 시 rho 의 크기와 end_slot_test 의
#     p_cluster 를 함께 본다.
#   - 분류 결과(y_pred)를 그대로 믿는다. 오분류는 걸러지지 않는다.
#   - 슬롯별 두께 데이터·TEL 매뉴얼의 PM 기준은 모른다. 여기서 말하는 배치 장비 물리는 일반론이다.
#
# 사용법
#   python wm811k_slot.py --demo
#   python wm811k_slot.py test_predictions.csv --pattern EDGE_RING
#   python wm811k_slot.py wm811k_predictions.csv --pattern EDGE_RING --output slot_out
#   python wm811k_slot.py fab_preds.csv --slot-col slot --end-slots 1 2 3 4 97 98 99 100
#   출력: slot_<PATTERN>_table.csv, slot_<PATTERN>_summary.txt, slot_<PATTERN>.png

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, fisher_exact, spearmanr

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DEFAULT_END_SLOTS: tuple[int, ...] = (1, 2, 3, 23, 24, 25)   # 25매 캐리어 가정
DEFAULT_SLOT_COL = "wafer_index"
DEFAULT_PRED_COL = "y_pred"
DEFAULT_LOT_COL = "lot"
DEFAULT_N_PERM = 2000
MIN_EXPECTED_CHI2 = 5.0          # 2x2 기대도수가 이보다 작으면 Fisher
Z95 = 1.959963984540054

SLOT_NOTE = ("wafer_index 는 WM-811K waferIndex 를 옮긴 슬롯 '대리 변수'다. "
             "물리 슬롯(FOUP/보트)과 같다는 보장이 없다. 실제 팹 데이터는 MES 슬롯 열을 --slot-col 로 준다.")

OTHER_LABELS = ("CLEAN", "LOC", "CENTER", "RANDOM", "SCRATCH")   # 합성에서 패턴이 아닌 웨이퍼의 라벨


# ──────────────────────────────────────────
# 1. 입력
# ──────────────────────────────────────────
def _prepare(df: pd.DataFrame, pattern: str, slot_col: str, pred_col: str,
             lot_col: str | None = None) -> pd.DataFrame:
    """필수 열 확인, 슬롯 결측 제거, 슬롯을 int 로. 반환 열: slot, hit(bool), (lot)."""
    for c in (slot_col, pred_col):
        if c not in df.columns:
            raise ValueError(f"'{c}' 열이 없다. 열: {list(df.columns)}")
    slot = pd.to_numeric(df[slot_col], errors="coerce")
    keep = slot.notna() & df[pred_col].notna()
    if "skipped" in df.columns:                       # wm811k_evaluate.py 형식
        keep &= ~df["skipped"].astype(bool)
    out = pd.DataFrame({"slot": slot[keep].astype(int).to_numpy(),
                        "hit": (df.loc[keep, pred_col].astype(str) == pattern).to_numpy()})
    if lot_col is not None:
        if lot_col not in df.columns:
            raise ValueError(f"'{lot_col}' 열이 없다. 열: {list(df.columns)}")
        out["lot"] = df.loc[keep, lot_col].astype(str).to_numpy()
    if len(out) == 0:
        raise ValueError("슬롯 값이 있는 행이 없다.")
    return out.reset_index(drop=True)


def load_predictions(path: Path, slot_col: str = DEFAULT_SLOT_COL, pred_col: str = DEFAULT_PRED_COL,
                     lot_col: str = DEFAULT_LOT_COL) -> pd.DataFrame:
    """예측 CSV 를 읽고 lot / slot / y_pred 열이 있는지 확인한다. 슬롯이 전부 결측이면 종료."""
    df = pd.read_csv(path)
    missing = [c for c in (lot_col, slot_col, pred_col) if c not in df.columns]
    if missing:
        sys.exit(f"{path.name}: {missing} 열이 필요하다. 열: {list(df.columns)}\n"
                 f"  wm811k_evaluate.py / wm811k_validate.py --export-predictions 의 CSV 는 wafer_index 를 포함한다.")
    if pd.to_numeric(df[slot_col], errors="coerce").notna().sum() == 0:
        sys.exit(f"{path.name}: '{slot_col}' 열이 전부 결측이다 (구버전 특징 캐시?). 슬롯 분석 불가.")
    return df


# ──────────────────────────────────────────
# 2. 통계
# ──────────────────────────────────────────
def wilson_interval(k, n, z: float = Z95) -> tuple[np.ndarray, np.ndarray]:
    """이항 비율의 Wilson 점수 구간. n = 0 이면 (0, 1). 배열 입력 가능."""
    k = np.asarray(k, dtype=float)
    n = np.asarray(n, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        p = np.where(n > 0, k / n, 0.0)
        denom = n + z * z
        center = (k + z * z / 2.0) / denom
        half = z * np.sqrt(np.where(n > 0, p * (1 - p) * n, 0.0) + z * z / 4.0) / denom
    lo = np.where(n > 0, np.clip(center - half, 0.0, 1.0), 0.0)
    hi = np.where(n > 0, np.clip(center + half, 0.0, 1.0), 1.0)
    return lo, hi


def slot_rate_table(df: pd.DataFrame, pattern: str, slot_col: str = DEFAULT_SLOT_COL,
                    pred_col: str = DEFAULT_PRED_COL) -> pd.DataFrame:
    """슬롯별 발생률 표. 열: slot, n, k, rate, wilson_lo, wilson_hi, ratio_to_overall.

    ratio_to_overall = 그 슬롯 발생률 / 전체 발생률 (전체가 0 이면 NaN). 슬롯은 오름차순.
    """
    d = _prepare(df, pattern, slot_col, pred_col)
    g = d.groupby("slot")["hit"].agg(n="size", k="sum").reset_index()
    g["k"] = g["k"].astype(int)
    g["rate"] = g["k"] / g["n"]
    g["wilson_lo"], g["wilson_hi"] = wilson_interval(g["k"].to_numpy(), g["n"].to_numpy())
    overall = d["hit"].mean()
    g["ratio_to_overall"] = g["rate"] / overall if overall > 0 else np.nan
    g.attrs["overall_rate"] = float(overall)
    g.attrs["pattern"] = pattern
    return g.sort_values("slot").reset_index(drop=True)


def resolve_end_slots(observed: np.ndarray, end_slots=DEFAULT_END_SLOTS, k: int = 3) -> tuple[tuple[int, ...], str]:
    """관측 슬롯이 1~25 안이면 end_slots 그대로, 아니면 관측 양끝 k 개씩. (끝 슬롯, 설명) 반환."""
    uniq = np.unique(np.asarray(observed, dtype=int))
    if uniq.min() >= 1 and uniq.max() <= 25 and any(s in uniq for s in end_slots):
        return tuple(int(s) for s in end_slots), "25-slot carrier default"
    if len(uniq) < 2 * k + 1:
        k = max(1, len(uniq) // 3)
    ends = tuple(int(s) for s in np.concatenate([uniq[:k], uniq[-k:]]))
    return ends, f"observed range {uniq.min()}..{uniq.max()} is outside 1..25 -> lowest/highest {k} each"


def _pooled_2x2(k_end: int, n_end: int, k_mid: int, n_mid: int) -> tuple[float, float, str]:
    """2x2 의 오즈비(0 칸이 있으면 Haldane 0.5 보정), p 값, 사용한 검정 이름."""
    a, b, c, d = k_end, n_end - k_end, k_mid, n_mid - k_mid
    if min(a, b, c, d) == 0:
        orv = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
    else:
        orv = (a * d) / (b * c)
    table = np.array([[a, b], [c, d]], dtype=float)
    if n_end == 0 or n_mid == 0 or table.sum(axis=0).min() == 0:
        return float(orv), float("nan"), "degenerate"
    expected = np.outer(table.sum(axis=1), table.sum(axis=0)) / table.sum()
    if expected.min() >= MIN_EXPECTED_CHI2:
        return float(orv), float(chi2_contingency(table, correction=True)[1]), "chi2"
    return float(orv), float(fisher_exact(table.astype(int), alternative="two-sided")[1]), "fisher"


def _lot_stratified_perm(hit: np.ndarray, is_end: np.ndarray, lot: np.ndarray,
                         n_perm: int, seed: int) -> tuple[float, int]:
    """로트 안에서 is_end 라벨만 섞는 순열 검정. 통계량은 끝 슬롯의 패턴 장수(k_end).

    로트별 끝 슬롯 수와 로트별 패턴 장수는 순열에서 보존되므로 k_end 의 변화가 곧
    끝-가운데 발생률 차의 변화다. 양측 p = (|k_perm - E| >= |k_obs - E| 인 횟수 + 1) / (n_perm + 1).
    기여 로트 = 끝과 가운데가 섞여 있고 패턴 유무가 섞여 있는 로트. 하나도 없으면 p = NaN.
    """
    codes, _ = pd.factorize(lot, sort=True)
    order0 = np.argsort(codes, kind="stable")
    codes, hit, is_end = codes[order0], hit[order0], is_end[order0]
    n = len(hit)
    # 기여 로트: 끝·가운데 둘 다 있고 hit 도 0/1 둘 다 있는 로트
    dfl = pd.DataFrame({"c": codes, "e": is_end, "h": hit})
    agg = dfl.groupby("c").agg(e_min=("e", "min"), e_max=("e", "max"), h_min=("h", "min"), h_max=("h", "max"))
    informative = int(((agg["e_min"] != agg["e_max"]) & (agg["h_min"] != agg["h_max"])).sum())
    if informative == 0:
        return float("nan"), 0
    # 조건부 기대값: 로트별로 k_lot * n_end_lot / n_lot
    g = dfl.groupby("c").agg(k=("h", "sum"), ne=("e", "sum"), n=("h", "size"))
    expected = float((g["k"] * g["ne"] / g["n"]).sum())
    k_obs = int(np.sum(hit & is_end))
    rng = np.random.default_rng(seed)
    dev_obs = abs(k_obs - expected)
    count = 0
    for _ in range(n_perm):
        order = np.lexsort((rng.random(n), codes))      # 로트 블록 안에서만 무작위 순서
        k_perm = int(np.sum(hit & is_end[order]))
        if abs(k_perm - expected) >= dev_obs - 1e-9:
            count += 1
    return (count + 1) / (n_perm + 1), informative


def end_slot_test(df: pd.DataFrame, pattern: str, end_slots=DEFAULT_END_SLOTS,
                  slot_col: str = DEFAULT_SLOT_COL, pred_col: str = DEFAULT_PRED_COL,
                  lot_col: str = DEFAULT_LOT_COL, n_perm: int = DEFAULT_N_PERM, seed: int = 0) -> dict:
    """끝 슬롯 vs 가운데 슬롯의 패턴 발생 2x2 검정.

    반환: odds_ratio(끝/가운데), p_pooled, test_pooled('chi2'|'fisher'|'degenerate'),
          p_cluster(로트 층화 순열), n_lots_informative, n_end, n_mid, k_end, k_mid, rate_end, rate_mid,
          end_slots, n_lots.
    p_pooled 는 웨이퍼를 독립으로 본 검정, p_cluster 는 로트가 공유하는 패턴을 조건부로 둔 검정이다.
    둘이 갈리면(p_pooled 작고 p_cluster 큼) 슬롯이 아니라 로트 효과를 의심한다(머리 주석 참고).
    CMH 를 쓰지 않는 이유도 머리 주석에 있다: 희소 층에서 공통 오즈비가 불안정하고 p 를 못 낸다.
    """
    d = _prepare(df, pattern, slot_col, pred_col, lot_col)
    is_end = d["slot"].isin(list(end_slots)).to_numpy()
    hit = d["hit"].to_numpy()
    n_end, n_mid = int(is_end.sum()), int((~is_end).sum())
    k_end, k_mid = int(hit[is_end].sum()), int(hit[~is_end].sum())
    orv, p_pooled, test_name = _pooled_2x2(k_end, n_end, k_mid, n_mid)
    p_cluster, informative = _lot_stratified_perm(hit, is_end, d["lot"].to_numpy(), n_perm, seed)
    return {
        "pattern": pattern, "end_slots": tuple(int(s) for s in end_slots),
        "odds_ratio": orv, "p_pooled": p_pooled, "test_pooled": test_name,
        "p_cluster": p_cluster, "n_lots_informative": informative, "n_perm": int(n_perm),
        "n_end": n_end, "n_mid": n_mid, "k_end": k_end, "k_mid": k_mid,
        "rate_end": k_end / n_end if n_end else float("nan"),
        "rate_mid": k_mid / n_mid if n_mid else float("nan"),
        "n_lots": int(d["lot"].nunique()),
    }


def slot_trend_test(df: pd.DataFrame, pattern: str, slot_col: str = DEFAULT_SLOT_COL,
                    pred_col: str = DEFAULT_PRED_COL) -> dict:
    """슬롯 순번과 패턴 발생(0/1)의 Spearman 상관. 반환: rho, p, n.

    rho > 0 이면 슬롯 번호가 클수록 발생률이 높다(단조 구배). p 는 풀링 p 라 로트 혼입에는
    end_slot_test 의 p_cluster 만큼 강건하지 않다. 슬롯이 하나뿐이거나 발생이 전무하면 NaN.
    """
    d = _prepare(df, pattern, slot_col, pred_col)
    if d["slot"].nunique() < 2 or d["hit"].nunique() < 2:
        return {"rho": float("nan"), "p": float("nan"), "n": int(len(d))}
    res = spearmanr(d["slot"].to_numpy(), d["hit"].to_numpy().astype(float))
    return {"rho": float(res.statistic), "p": float(res.pvalue), "n": int(len(d))}


# ──────────────────────────────────────────
# 3. 그림
# ──────────────────────────────────────────
def plot_slot_profile(table: pd.DataFrame, ax, title: str = "", end_slots=DEFAULT_END_SLOTS) -> None:
    """슬롯별 발생률 막대 + Wilson 95% 구간 + 전체 발생률 점선. 끝 슬롯은 진한 색. 영문 라벨."""
    x = table["slot"].to_numpy()
    rate = table["rate"].to_numpy()
    err = np.vstack([rate - table["wilson_lo"].to_numpy(), table["wilson_hi"].to_numpy() - rate])
    colors = ["#1565C0" if s in end_slots else "#90A4AE" for s in x]
    ax.bar(x, rate, color=colors, width=0.8)
    ax.errorbar(x, rate, yerr=err, fmt="none", ecolor="#455A64", elinewidth=0.8, capsize=2)
    overall = table.attrs.get("overall_rate", float(np.nansum(table["k"]) / max(1, np.nansum(table["n"]))))
    ax.axhline(overall, color="#F44336", ls="--", lw=1, label=f"overall {overall:.3f}")
    ax.set_xlabel("slot (proxy: wafer_index)")
    ax.set_ylabel(f"rate of {table.attrs.get('pattern', 'pattern')}")
    ax.set_ylim(0, min(1.0, max(0.05, float(np.nanmax(table["wilson_hi"])) * 1.1)))
    ax.set_title(title or "slot profile (blue = end slots)", fontsize=10)
    ax.legend(loc="upper center", fontsize=8, frameon=False)
    for s in ax.spines.values():
        s.set_color("#B0BEC5")


# ──────────────────────────────────────────
# 4. 합성 (로직 확인용 - 성능 아님)
# ──────────────────────────────────────────
def synthetic_slot_predictions(n_wafers: int = 1000, seed: int = 0, pattern: str = "EDGE_RING",
                               end_effect: float = 0.5, trend: float = 0.0, n_slots: int = 25,
                               base_rate: float = 0.3, lot_sd: float = 0.08,
                               end_slots=DEFAULT_END_SLOTS) -> pd.DataFrame:
    """완전한 로트(슬롯 1..n_slots 각 1장)를 이어 붙인 합성 예측. 열: lot, wafer_index, y_pred.

    로트마다 기저 발생률 p_lot ~ N(base_rate, lot_sd) (로트 효과), 끝 슬롯은 (1 + end_effect) 배,
    슬롯 순번을 따라 (1 + trend * (s-1)/(n_slots-1)) 배. 나머지 웨이퍼는 OTHER_LABELS 에서 뽑는다.
    """
    rng = np.random.default_rng(seed)
    n_lots = int(np.ceil(n_wafers / n_slots))
    rows = []
    wid = 0
    for L in range(n_lots):
        p_lot = float(np.clip(rng.normal(base_rate, lot_sd), 0.02, 0.95))
        for s in range(1, n_slots + 1):
            if wid >= n_wafers:
                break
            p = p_lot * (1.0 + (end_effect if s in end_slots else 0.0)) * (1.0 + trend * (s - 1) / max(1, n_slots - 1))
            y = pattern if rng.random() < min(p, 0.98) else str(rng.choice(OTHER_LABELS))
            rows.append({"lot": f"synL{L:04d}", "wafer_index": s, "y_pred": y})
            wid += 1
    return pd.DataFrame(rows)


def synthetic_confounded_predictions(n_lots: int = 40, seed: int = 0, pattern: str = "EDGE_RING",
                                     n_slots: int = 25, end_slots=DEFAULT_END_SLOTS) -> pd.DataFrame:
    """슬롯 효과는 없고 로트 효과만 있는데 표본이 치우친 합성 (결함 부분집합을 흉내).

    절반의 로트는 패턴 비율 0.8(양성 로트), 절반은 0.05. 양성 로트는 끝 슬롯 웨이퍼만 남기고
    (라벨이 끝 슬롯에만 붙은 상황), 음성 로트는 모든 슬롯을 남긴다. 풀링 검정은 끝 슬롯이
    높다고 울리지만 로트 안에서는 슬롯 효과가 없으므로 p_cluster 는 울리지 않아야 한다.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for L in range(n_lots):
        positive = L % 2 == 0
        p = 0.8 if positive else 0.05
        for s in range(1, n_slots + 1):
            if positive and s not in end_slots:
                continue
            y = pattern if rng.random() < p else str(rng.choice(OTHER_LABELS))
            rows.append({"lot": f"cfL{L:04d}", "wafer_index": s, "y_pred": y})
    return pd.DataFrame(rows)


DEMO_SCENARIOS = [
    # (이름, 생성 함수, 기대: p_pooled < 0.01, p_cluster < 0.01)
    ("planted_end+50%", lambda: synthetic_slot_predictions(1000, seed=1, end_effect=0.5), (True, True)),
    ("no_effect", lambda: synthetic_slot_predictions(1000, seed=2, end_effect=0.0), (False, False)),
    ("lot_confound_only", lambda: synthetic_confounded_predictions(40, seed=3), (True, False)),
]


# ──────────────────────────────────────────
# 5. CLI
# ──────────────────────────────────────────
def summarize(df: pd.DataFrame, pattern: str, end_slots, slot_col: str, pred_col: str, lot_col: str,
              n_perm: int, seed: int = 0) -> dict:
    """표 + 끝 슬롯 검정 + 추세 검정을 한 번에. 반환 dict: table, end, trend, end_slots, end_note."""
    d = _prepare(df, pattern, slot_col, pred_col)
    ends, note = resolve_end_slots(d["slot"].to_numpy(), end_slots)
    table = slot_rate_table(df, pattern, slot_col, pred_col)
    end = end_slot_test(df, pattern, ends, slot_col, pred_col, lot_col, n_perm, seed)
    trend = slot_trend_test(df, pattern, slot_col, pred_col)
    return {"table": table, "end": end, "trend": trend, "end_slots": ends, "end_note": note}


def _verdict(end: dict, trend: dict, alpha: float = 0.01) -> str:
    pp, pc = end["p_pooled"], end["p_cluster"]
    if np.isnan(pc):
        base = ("cluster test not possible (no lot has both end and mid slots with mixed outcomes); "
                "pooled p alone cannot separate slot from lot effect")
    elif pp < alpha and pc < alpha:
        base = "end-slot effect supported (both pooled and lot-stratified p below alpha)"
    elif pp < alpha and pc >= alpha:
        base = "pooled test fires but lot-stratified test does not -> lot effect / sampling bias, not a slot effect"
    elif pp >= alpha and pc < alpha:
        base = "lot-stratified test fires only -> weak effect masked by lot variation; check per-lot profiles"
    else:
        base = "no end-slot effect detected"
    if not np.isnan(trend["rho"]) and trend["p"] < alpha and abs(trend["rho"]) >= 0.1:
        base += f"; monotone trend along slot (rho={trend['rho']:+.2f}) -> boat-axis gradient signature"
    return base


def _format_summary(res: dict, label: str) -> list[str]:
    e, t = res["end"], res["trend"]
    lines = [
        f"slot dependence - {label} - pattern {e['pattern']}",
        f"  {SLOT_NOTE}",
        f"  end slots: {list(res['end_slots'])} ({res['end_note']})",
        f"  n_end={e['n_end']} k_end={e['k_end']} rate_end={e['rate_end']:.3f} | "
        f"n_mid={e['n_mid']} k_mid={e['k_mid']} rate_mid={e['rate_mid']:.3f} | lots={e['n_lots']}",
        f"  odds_ratio(end/mid)={e['odds_ratio']:.2f}  p_pooled={e['p_pooled']:.3g} ({e['test_pooled']})  "
        f"p_cluster={e['p_cluster']:.3g} (lot-stratified permutation, {e['n_perm']} perms, "
        f"{e['n_lots_informative']} informative lots)",
        f"  trend: spearman rho={t['rho']:+.3f} p={t['p']:.3g} (n={t['n']}, pooled p)",
        f"  verdict: {_verdict(e, t)}",
        "  reading: end-slot excess -> batch tool boat ends (temperature ramp, gas depletion, dummy-wafer boundary); "
        "monotone trend -> boat-axis gradient. Both are generic batch-furnace physics, not a TEL manual spec.",
    ]
    return lines


def run(df: pd.DataFrame, pattern: str, out_dir: Path, end_slots=DEFAULT_END_SLOTS,
        slot_col: str = DEFAULT_SLOT_COL, pred_col: str = DEFAULT_PRED_COL, lot_col: str = DEFAULT_LOT_COL,
        n_perm: int = DEFAULT_N_PERM, label: str = "", seed: int = 0) -> dict:
    """표·검정·그림을 out_dir 에 저장하고 요약 dict 를 돌려준다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    res = summarize(df, pattern, end_slots, slot_col, pred_col, lot_col, n_perm, seed)
    stem = f"slot_{pattern}"
    res["table"].to_csv(out_dir / f"{stem}_table.csv", index=False, encoding="utf-8-sig")
    lines = _format_summary(res, label or "predictions")
    print("\n" + "\n".join(lines))
    with open(out_dir / f"{stem}_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(8, 3.6))
    plot_slot_profile(res["table"], ax, title=f"{pattern} rate by slot - {label or 'predictions'}",
                      end_slots=res["end_slots"])
    fig.tight_layout()
    fig.savefig(out_dir / f"{stem}.png", dpi=110)
    plt.close(fig)
    print(f"  saved: {out_dir / (stem + '_table.csv')}, {out_dir / (stem + '_summary.txt')}, {out_dir / (stem + '.png')}")
    return res


def run_demo(out_dir: Path, n_perm: int = DEFAULT_N_PERM) -> bool:
    """합성 3시나리오를 돌려 기대 판정과 비교. 일치하면 True. 로직 확인이지 성능이 아니다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    print("[demo] synthetic scenarios (logic check, not detection performance):")
    print("  1) planted_end+50%   : lot effect + end slots x1.5          -> p_pooled < 0.01, p_cluster < 0.01")
    print("  2) no_effect         : lot effect only, complete lots        -> both p >= 0.01")
    print("  3) lot_confound_only : positive lots sampled at end slots only -> p_pooled < 0.01, p_cluster >= 0.01")
    ok_all = True
    fig, axes = plt.subplots(1, len(DEMO_SCENARIOS), figsize=(5.2 * len(DEMO_SCENARIOS), 3.6))
    for ax, (name, make, (exp_pooled, exp_cluster)) in zip(np.atleast_1d(axes), DEMO_SCENARIOS):
        df = make()
        res = summarize(df, "EDGE_RING", DEFAULT_END_SLOTS, DEFAULT_SLOT_COL, DEFAULT_PRED_COL,
                        DEFAULT_LOT_COL, n_perm)
        res["table"].to_csv(out_dir / f"slot_demo_{name}_table.csv", index=False, encoding="utf-8-sig")
        print("\n" + "\n".join(_format_summary(res, f"demo {name}")))
        e = res["end"]
        got = (e["p_pooled"] < 0.01, (not np.isnan(e["p_cluster"])) and e["p_cluster"] < 0.01)
        ok = got == (exp_pooled, exp_cluster)
        ok_all &= ok
        print(f"  expected (pooled<0.01, cluster<0.01) = {(exp_pooled, exp_cluster)}, got {got} -> "
              f"{'OK' if ok else 'MISMATCH'}")
        plot_slot_profile(res["table"], ax, title=f"{name}: p_pooled={e['p_pooled']:.2g} p_cluster={e['p_cluster']:.2g}",
                          end_slots=res["end_slots"])
    fig.tight_layout()
    fig.savefig(out_dir / "slot_demo.png", dpi=110)
    plt.close(fig)
    print(f"\n[demo] {'all scenarios as expected' if ok_all else 'MISMATCH - check logic'}; figure: {out_dir / 'slot_demo.png'}")
    return ok_all


def _cli(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="패턴 발생률의 슬롯 의존성 검정: 끝 슬롯 vs 가운데(2x2, 로트 층화 순열), 슬롯 순번 추세(Spearman).")
    ap.add_argument("predictions", nargs="?", type=Path, default=None,
                    help="예측 CSV (lot, wafer_index, y_pred 필요; wm811k_evaluate / wm811k_validate --export-predictions)")
    ap.add_argument("--pattern", default="EDGE_RING", help="검정할 패턴 (기본 EDGE_RING)")
    ap.add_argument("--slot-col", default=DEFAULT_SLOT_COL, help=f"슬롯 열 (기본 {DEFAULT_SLOT_COL}; 팹 데이터는 MES 슬롯 열)")
    ap.add_argument("--pred-col", default=DEFAULT_PRED_COL)
    ap.add_argument("--lot-col", default=DEFAULT_LOT_COL)
    ap.add_argument("--end-slots", nargs="+", type=int, default=list(DEFAULT_END_SLOTS),
                    help="끝 슬롯 번호 (기본 1 2 3 23 24 25; 관측 범위가 1~25 밖이면 양끝 3개씩으로 자동 대체)")
    ap.add_argument("--n-perm", type=int, default=DEFAULT_N_PERM, help="로트 층화 순열 횟수 (기본 2000)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--output", type=Path, default=None, help="출력 폴더 (기본 HERE/slot_out, --demo 는 HERE/slot_demo)")
    ap.add_argument("--demo", action="store_true", help="합성 3시나리오로 로직 확인 (성능 아님)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> dict | None:
    a = _cli(argv)
    if a.demo:
        ok = run_demo(a.output or HERE / "slot_demo", a.n_perm)
        if not ok:
            sys.exit(1)
        return None
    if a.predictions is None:
        sys.exit("예측 CSV 경로가 필요하다 (또는 --demo).")
    df = load_predictions(a.predictions, a.slot_col, a.pred_col, a.lot_col)
    return run(df, a.pattern, a.output or HERE / "slot_out", tuple(a.end_slots), a.slot_col, a.pred_col,
               a.lot_col, a.n_perm, label=a.predictions.name, seed=a.seed)


if __name__ == "__main__":
    matplotlib.use("Agg")
    main()
