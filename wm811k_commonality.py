# wm811k_commonality.py
# 장비 공통성 분석(tool commonality analysis) - 패턴 양성 로트들이 공유한 공정 단계·장비·챔버 찾기
#
# 배경
#   수율 이상이 나면 팹에서 가장 먼저 하는 일은 "불량 로트들이 어느 장비를 같이 지났는가"를
#   로트 이력에서 찾는 것이다(docs/defect_signatures.md 현장 순서 4번). 장비사 기술지원
#   엔지니어 입장에서는 이 결과가 "우리 장비(TEL 모듈)가 지목됐는가, 타사 장비 인계인가"를
#   가르는 첫 근거이고, 지목된 장비·챔버의 PM·부품 교체 이력을 그 다음에 맞댄다.
#   WM-811K 에는 장비 이력이 없다. 그래서 입력 스키마(docs/lot_history_schema.md)를 정하고
#   합성 이력으로 로직을 고정했다. 실제 팹에서는 MES 의 로트 라우팅 추출 CSV 가 입력이다.
#
# 무엇을 하나
#   load_lot_history     이력 CSV 읽기 + 스키마 검증(lot, step, tool 필수; chamber 선택) + 결측 경고.
#   lot_pattern_status   예측 CSV -> 로트별 양성 여부(Series[bool], index=lot).
#                        양성 = 로트 안 패턴 비율 >= min_frac 이고 로트 장수 >= min_n.
#   commonality_table    단계(step) 안에서 장비(tool[/chamber]) 단위 2x2: 그 단위를 지난 로트의
#                        양성률 vs 같은 단계의 나머지 로트. rate_ratio + 95% CI, Fisher 단측(greater)
#                        p, 단계 안 Benjamini-Hochberg q, n_lots < min_lots 는 'insufficient',
#                        상위 단위와의 로트 중복률(overlap_with_top)로 라우팅 혼입 경고.
#   synthetic_history    가상 ID 로 만든 합성 이력 (planted 단계의 특정 장비에 효과를 심는다).
#   synthetic_predictions 그 이력과 맞는 합성 예측 (planted 장비를 지난 로트에 패턴 비율을 높인다).
#   plot_commonality     단위별 양성률 가로 막대 + CI (유의/불충분 색 구분, 영문 라벨).
#   CLI                  predictions.csv --history lot_history.csv --pattern EDGE_LOC --output DIR / --demo
#
# 왜 이렇게
#   - 단위는 로트다. 같은 로트의 웨이퍼는 패턴을 공유하므로 웨이퍼를 세면 과산포로 p 가 과장된다.
#   - 단계 안 비교다. 같은 단계의 장비들은 서로 배타적(한 로트가 한 장비를 지남)이라 2x2 가 깨끗하다.
#     단계가 다른 장비끼리는 라우팅이 묶여 있을 수 있어(ETCH-02 로트가 늘 CVD-01 도 지나면 둘 다
#     뜬다) overlap_with_top 으로 '구분 불가'를 표시한다.
#   - Fisher 단측(greater): 묻는 것은 '이 장비가 더 나쁜가'다. 로트 수가 적으면 Fisher 는 보수적이다.
#   - BH 는 단계 안에서만 적용한다. 단계 간은 질문이 다르고 장비 수가 달라 한 묶음으로 보정하면
#     장비가 많은 단계가 불리해진다.
#
# 한계
#   - min_n 기본 1: WM-811K 결함 부분집합은 로트당 평균 3.2장이라 min_n 을 올리면 대부분 로트가
#     빠진다. 대신 1~2장짜리 로트의 '양성'은 웨이퍼 한 장의 판정이므로 로트 수가 충분히 많을 때만
#     믿고, 실제 팹 데이터(로트당 25장)에서는 min_n=5 이상을 권한다.
#   - n_lots < 5 인 단위는 근거 부족(insufficient)으로 표시만 하고 순위에서 뒤로 보낸다.
#   - 공통성은 상관이지 인과가 아니다. 지목된 장비의 PM·부품 이력과 시점(wm811k_spc.py --event-col)을
#     맞대야 끝난다. pm_date 와 start_time 이 있으면 상위 단위의 'PM 후 경과일' 요약을 함께 낸다.
#   - 합성(--demo, tests/)은 로직 확인이지 성능이 아니다. 고객 데이터·실제 장비 ID 는 커밋하지 않는다
#     (.gitignore 의 *.lot_history.csv). 예시 ID 는 전부 가상이다.
#
# 사용법
#   python wm811k_commonality.py --demo
#   python wm811k_commonality.py test_predictions.csv --history fab.lot_history.csv --pattern EDGE_LOC
#   python wm811k_commonality.py preds.csv --history hist.csv --pattern EDGE_RING --min-n 5 --by step tool
#   출력: commonality_<PATTERN>.csv, commonality_<PATTERN>_summary.txt, commonality_<PATTERN>.png

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
REQUIRED_COLS: tuple[str, ...] = ("lot", "step", "tool")
OPTIONAL_COLS: tuple[str, ...] = ("chamber", "start_time", "pm_date", "part_change")
DEFAULT_BY: tuple[str, ...] = ("step", "tool", "chamber")
DEFAULT_MIN_FRAC = 0.3
DEFAULT_MIN_N = 1
DEFAULT_MIN_LOTS = 5           # 이보다 적은 로트를 지난 단위는 '근거 부족'
DEFAULT_OVERLAP_WARN = 0.8     # 상위 단위와 로트 중복률이 이 이상이면 라우팅 혼입 경고
Q_ALPHA = 0.05
Z95 = 1.959963984540054

# 합성 이력의 가상 단계 (prefix 로 장비 ID 를 만든다). 실제 팹 단계명이 아니다.
DEFAULT_STEPS: tuple[tuple[str, str], ...] = (
    ("ETCH_M1", "ETCH"), ("CVD_ILD1", "CVD"), ("TRACK_M1", "TRK"), ("CLEAN_PRE", "CLN"),
)
OTHER_LABELS = ("CLEAN", "LOC", "CENTER", "RANDOM", "SCRATCH", "EDGE_RING")


# ──────────────────────────────────────────
# 1. 입력
# ──────────────────────────────────────────
def validate_history(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """스키마 검증. lot/step/tool 필수(없으면 ValueError), chamber 없으면 '' 로 채움, 결측 행 경고 후 제거.

    start_time / pm_date 가 있으면 datetime 으로 바꾼다(실패한 값은 NaT, 건수 경고).
    같은 (lot, step) 가 두 번 이상이면(재작업) 경고만 하고 모두 남긴다.
    """
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"lot history 에 필수 열이 없다: {missing}. 열: {list(df.columns)}. "
                         f"스키마: docs/lot_history_schema.md")
    out = df.copy()
    for c in REQUIRED_COLS:
        out[c] = out[c].astype("string")
    if "chamber" not in out.columns:
        out["chamber"] = ""
        if verbose:
            print("[주의] chamber 열이 없어 장비 단위로만 본다 (--by step tool 과 같다).")
    out["chamber"] = out["chamber"].fillna("").astype(str)
    bad = out[list(REQUIRED_COLS)].isna().any(axis=1) | (out["lot"].str.strip() == "")
    if bad.any():
        if verbose:
            print(f"[주의] lot/step/tool 결측 행 {int(bad.sum())}개를 제외한다.")
        out = out[~bad]
    for c in REQUIRED_COLS:
        out[c] = out[c].astype(str).str.strip()
    for c in ("start_time", "pm_date"):
        if c in out.columns:
            parsed = pd.to_datetime(out[c], errors="coerce")
            n_bad = int(parsed.isna().sum() - out[c].isna().sum())
            if n_bad and verbose:
                print(f"[주의] {c} 에 날짜로 읽히지 않는 값 {n_bad}개 (NaT 처리).")
            out[c] = parsed
    dup = out.duplicated(["lot", "step"], keep=False)
    if dup.any() and verbose:
        print(f"[주의] 같은 (lot, step) 가 여러 행인 경우 {int(dup.sum())}행 (재작업?). 모두 남긴다.")
    if len(out) == 0:
        raise ValueError("lot history 에 유효한 행이 없다.")
    return out.reset_index(drop=True)


def load_lot_history(path: Path, verbose: bool = True) -> pd.DataFrame:
    """이력 CSV 를 읽고 validate_history 를 거친다. 스키마는 docs/lot_history_schema.md."""
    df = pd.read_csv(path, dtype=str)
    return validate_history(df, verbose)


def lot_pattern_status(preds: pd.DataFrame, pattern: str, min_frac: float = DEFAULT_MIN_FRAC,
                       min_n: int = DEFAULT_MIN_N, lot_col: str = "lot", pred_col: str = "y_pred") -> pd.Series:
    """로트별 패턴 양성 여부. index=lot, 값=bool. n_lot < min_n 인 로트는 제외(attrs['n_dropped']).

    양성 = (로트 안 y_pred == pattern 비율) >= min_frac. 로트 장수와 비율은 attrs['table'] 에 둔다.
    min_n=1 이면 웨이퍼 한 장짜리 로트도 그 한 장의 판정으로 양성/음성이 정해진다 - 결함 부분집합
    (로트당 평균 3.2장)에서 로트를 버리지 않기 위한 기본값이며, 실제 팹 데이터는 min_n 을 올린다.
    """
    for c in (lot_col, pred_col):
        if c not in preds.columns:
            raise ValueError(f"예측에 '{c}' 열이 없다. 열: {list(preds.columns)}")
    p = preds[preds[pred_col].notna()]
    if "skipped" in p.columns:
        p = p[~p["skipped"].astype(bool)]
    lot = p[lot_col].astype(str).str.strip()
    hit = (p[pred_col].astype(str) == pattern)
    tab = pd.DataFrame({"n": hit.groupby(lot).size(), "k": hit.groupby(lot).sum().astype(int)})
    tab["frac"] = tab["k"] / tab["n"]
    keep = tab["n"] >= min_n
    status = (tab.loc[keep, "frac"] >= min_frac)
    status.name = f"positive_{pattern}"
    status.index.name = "lot"
    status.attrs["n_dropped"] = int((~keep).sum())
    status.attrs["table"] = tab
    status.attrs["pattern"] = pattern
    return status


# ──────────────────────────────────────────
# 2. 통계
# ──────────────────────────────────────────
def bh_adjust(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg q 값. NaN 은 그대로 둔다."""
    p = np.asarray(p, dtype=float)
    q = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    m = int(ok.sum())
    if m == 0:
        return q
    pv = p[ok]
    order = np.argsort(pv)
    ranked = pv[order] * m / (np.arange(m) + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    qq = np.empty(m)
    qq[order] = np.clip(ranked, 0.0, 1.0)
    q[ok] = qq
    return q


def _rate_ratio_ci(a: int, n1: int, c: int, n2: int) -> tuple[float, float, float]:
    """(a/n1) / (c/n2) 와 로그 정규 근사 95% CI. 0 칸이 있으면 0.5 보정(Katz)."""
    if n1 == 0 or n2 == 0:
        return float("nan"), float("nan"), float("nan")
    if a == 0 or c == 0:
        a_, n1_, c_, n2_ = a + 0.5, n1 + 1.0, c + 0.5, n2 + 1.0
    else:
        a_, n1_, c_, n2_ = float(a), float(n1), float(c), float(n2)
    rr = (a_ / n1_) / (c_ / n2_)
    se = np.sqrt(max(0.0, 1.0 / a_ - 1.0 / n1_ + 1.0 / c_ - 1.0 / n2_))
    return float(rr), float(rr * np.exp(-Z95 * se)), float(rr * np.exp(Z95 * se))


def commonality_table(history: pd.DataFrame, status: pd.Series, by=DEFAULT_BY,
                      min_lots: int = DEFAULT_MIN_LOTS, overlap_warn: float = DEFAULT_OVERLAP_WARN) -> pd.DataFrame:
    """단계 안 장비(단위)별 2x2 공통성 표.

    by 의 첫 원소가 층(기본 step), 나머지가 단위 키(기본 tool, chamber). 반환 열:
      step, tool, chamber, n_lots, n_bad, rate, n_other, bad_other, rate_other, rate_ratio, ci_lo, ci_hi,
      p_fisher(단측 greater), q_bh(단계 안), overlap_with_top, evidence('ok'|'insufficient'), note.
    overlap_with_top = 그 단위를 지난 로트 중 상위 1 단위(evidence ok, p 최소)의 장비(모든 챔버)도 지난 비율.
    다른 단계의 단위가 overlap >= overlap_warn 이고 q < 0.05 면 note 에 라우팅 혼입 경고.
    status 에 없는 로트(예측이 없거나 min_n 미만)는 이력에 있어도 세지 않는다.
    """
    by = tuple(by)
    stratum, unit_keys = by[0], list(by[1:])
    hist = history.copy()
    for c in by:
        if c not in hist.columns:
            if c == "chamber":
                hist["chamber"] = ""
            else:
                raise ValueError(f"history 에 '{c}' 열이 없다.")
        hist[c] = hist[c].fillna("").astype(str)
    st = status.astype(bool)
    st.index = st.index.astype(str)
    hist = hist[hist["lot"].astype(str).isin(st.index)]
    if len(hist) == 0:
        raise ValueError("이력의 lot 과 예측의 lot 이 하나도 겹치지 않는다. 로트 ID 표기를 확인하라.")
    rows = []
    lot_sets: dict[tuple, set] = {}
    for s, hs in hist.groupby(stratum, sort=True):
        lots_in_step = set(hs["lot"].astype(str))
        bad_in_step = {L for L in lots_in_step if st[L]}
        for key, hu in hs.groupby(unit_keys, sort=True):
            key = key if isinstance(key, tuple) else (key,)
            lots = set(hu["lot"].astype(str))
            n1, a = len(lots), len(lots & bad_in_step)
            others = lots_in_step - lots
            n2, c = len(others), len(others & bad_in_step)
            rr, lo, hi = _rate_ratio_ci(a, n1, c, n2)
            if n2 > 0 and n1 > 0:
                p = float(fisher_exact([[a, n1 - a], [c, n2 - c]], alternative="greater")[1])
            else:
                p = float("nan")
            row = {stratum: s}
            row.update(dict(zip(unit_keys, key)))
            row.update({"n_lots": n1, "n_bad": a, "rate": a / n1 if n1 else np.nan,
                        "n_other": n2, "bad_other": c, "rate_other": c / n2 if n2 else np.nan,
                        "rate_ratio": rr, "ci_lo": lo, "ci_hi": hi, "p_fisher": p})
            rows.append(row)
            lot_sets[(s, *key)] = lots
    tab = pd.DataFrame(rows)
    for c in ("tool", "chamber"):
        if c not in tab.columns:
            tab[c] = ""
    tab["q_bh"] = np.nan
    for s, idx in tab.groupby(stratum).groups.items():
        tab.loc[idx, "q_bh"] = bh_adjust(tab.loc[idx, "p_fisher"].to_numpy())
    tab["evidence"] = np.where(tab["n_lots"] >= min_lots, "ok", "insufficient")
    tab["_ins"] = (tab["evidence"] == "insufficient").astype(int)       # 근거 부족은 뒤로
    tab = tab.sort_values(["_ins", "p_fisher", "rate_ratio"], ascending=[True, True, False],
                          na_position="last").drop(columns="_ins").reset_index(drop=True)
    # 상위 단위와의 로트 중복률
    tab["overlap_with_top"] = np.nan
    tab["note"] = ""
    ok_rows = tab[tab["evidence"] == "ok"]
    if len(ok_rows):
        top = ok_rows.iloc[0]
        top_key = (top[stratum], *[top[k] for k in unit_keys])
        # 중복률은 상위 단위의 '장비'(첫 단위 키, 모든 챔버) 기준. 라우팅은 장비 단위로 묶이기 때문이다.
        top_lots: set = set()
        for k, v in lot_sets.items():
            if k[0] == top_key[0] and k[1] == top_key[1]:
                top_lots |= v
        for i, r in tab.iterrows():
            key = (r[stratum], *[r[k] for k in unit_keys])
            lots = lot_sets[key]
            ov = len(lots & top_lots) / len(lots) if lots else np.nan
            tab.at[i, "overlap_with_top"] = ov
            if key == top_key:
                tab.at[i, "note"] = "top candidate"
            elif (r[stratum] != top[stratum] and np.isfinite(ov) and ov >= overlap_warn
                  and np.isfinite(r["q_bh"]) and r["q_bh"] < Q_ALPHA):
                tab.at[i, "note"] = (f"routing overlap {ov:.2f} with top ({top[stratum]} "
                                     f"{'/'.join(str(top[k]) for k in unit_keys)}) - cannot separate")
    ins = tab["evidence"] == "insufficient"
    tab.loc[ins, "note"] = (tab.loc[ins, "note"].where(tab.loc[ins, "note"] != "", "") +
                            f" insufficient (n_lots < {min_lots})").str.strip()
    # tool / chamber 열은 by 에 없어도 항상 둔다 (요약·그림이 참조). by 에 없으면 '' 이다.
    cols = [stratum, *unit_keys, *[c for c in ("tool", "chamber") if c not in unit_keys],
            "n_lots", "n_bad", "rate", "n_other", "bad_other", "rate_other",
            "rate_ratio", "ci_lo", "ci_hi", "p_fisher", "q_bh", "overlap_with_top", "evidence", "note"]
    tab.attrs["pattern"] = status.attrs.get("pattern", "")
    tab.attrs["n_lots_total"] = int(st.size)
    tab.attrs["n_bad_total"] = int(st.sum())
    return tab[cols]


def pm_age_summary(history: pd.DataFrame, status: pd.Series, step: str, tool: str,
                   chamber: str | None = None) -> dict | None:
    """상위 단위의 'PM 후 경과일'(start_time - pm_date) 중앙값을 양성/음성 로트로 나눠 본다.

    start_time 과 pm_date 가 둘 다 있을 때만. 양성 로트의 경과일이 유의하게 길면 소모품 마모,
    짧으면 PM 직후 파티클(시즈닝) 쪽을 먼저 본다 - 둘 다 docs/defect_signatures.md 의 점검 순서.
    """
    if "start_time" not in history.columns or "pm_date" not in history.columns:
        return None
    h = history[(history["step"].astype(str) == step) & (history["tool"].astype(str) == tool)]
    if chamber is not None and "chamber" in h.columns and chamber != "":
        h = h[h["chamber"].astype(str) == chamber]
    h = h[h["lot"].astype(str).isin(status.index.astype(str))]
    age = (pd.to_datetime(h["start_time"], errors="coerce") - pd.to_datetime(h["pm_date"], errors="coerce")).dt.days
    st = status.astype(bool)
    st.index = st.index.astype(str)
    bad = age[h["lot"].astype(str).map(st).fillna(False).to_numpy()]
    good = age[~h["lot"].astype(str).map(st).fillna(False).to_numpy()]
    bad, good = bad.dropna(), good.dropna()
    if len(bad) == 0 and len(good) == 0:
        return None
    return {"n_bad": int(len(bad)), "n_good": int(len(good)),
            "median_days_bad": float(bad.median()) if len(bad) else float("nan"),
            "median_days_good": float(good.median()) if len(good) else float("nan")}


# ──────────────────────────────────────────
# 3. 그림
# ──────────────────────────────────────────
def plot_commonality(table: pd.DataFrame, ax, top: int = 12, title: str = "") -> None:
    """단위별 양성률 가로 막대 + CI(비율 CI 는 rate_ratio CI 를 rate_other 로 되돌린 것). 영문 라벨.

    파랑 = q < 0.05 (evidence ok), 회색 = 그 외, 빗금 = insufficient. 점선 = 같은 단계 나머지 로트의 양성률.
    """
    t = table.head(top).iloc[::-1]
    labels = [f"{r['step']} {r['tool']}{('/' + str(r['chamber'])) if str(r.get('chamber', '')) else ''} (n={r['n_lots']})"
              for _, r in t.iterrows()]
    y = np.arange(len(t))
    rate = t["rate"].to_numpy(float)
    lo = np.clip(t["ci_lo"].to_numpy(float) * t["rate_other"].to_numpy(float), 0, 1)
    hi = np.clip(t["ci_hi"].to_numpy(float) * t["rate_other"].to_numpy(float), 0, 1)
    sig = (t["q_bh"].to_numpy(float) < Q_ALPHA) & (t["evidence"].to_numpy() == "ok")
    colors = np.where(sig, "#1565C0", "#90A4AE")
    bars = ax.barh(y, rate, color=colors, height=0.7)
    for b, ins in zip(bars, t["evidence"].to_numpy() == "insufficient"):
        if ins:
            b.set_hatch("///")
            b.set_edgecolor("#607D8B")
    err = np.vstack([np.maximum(0, rate - lo), np.maximum(0, hi - rate)])
    ax.errorbar(rate, y, xerr=err, fmt="none", ecolor="#455A64", elinewidth=0.8, capsize=2)
    ax.scatter(t["rate_other"].to_numpy(float), y, marker="|", color="#F44336", s=60, zorder=3,
               label="rest of same step")
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlim(0, 1)
    ax.set_xlabel(f"fraction of lots positive for {table.attrs.get('pattern', 'pattern')}")
    ax.set_title(title or "tool commonality (blue: q<0.05, hatched: n_lots<5)", fontsize=10)
    ax.legend(loc="lower right", fontsize=8, frameon=False)
    for s in ax.spines.values():
        s.set_color("#B0BEC5")


# ──────────────────────────────────────────
# 4. 합성 (가상 ID - 로직 확인용, 성능 아님)
# ──────────────────────────────────────────
def synthetic_history(lots, seed: int = 0, planted: dict[str, str] | None = None,
                      steps=DEFAULT_STEPS, n_tools: int = 3, n_chambers: int = 2,
                      coupling: float = 0.0) -> pd.DataFrame:
    """가상 로트 이력. 열: lot, step, tool, chamber, start_time, pm_date.

    각 로트가 steps 를 순서대로 지나며 장비는 단계마다 균일 난수로 배정된다. planted 는 효과를
    심을 장비 이름이 이력에 존재하도록 보장만 한다(효과 자체는 synthetic_predictions 가 준다).
    coupling > 0 이면 두 번째 단계의 장비 번호가 그 확률로 첫 단계와 같아진다 - 라우팅 혼입 시나리오.
    start_time 은 로트 순서대로 하루 간격 + 단계마다 6시간, pm_date 는 장비·챔버마다 고정된 과거 날짜.
    """
    rng = np.random.default_rng(seed)
    lots = [str(L) for L in lots]
    planted = planted or {}
    base = pd.Timestamp("2026-01-05")
    pm = {}
    rows = []
    for i, L in enumerate(lots):
        first_idx = None
        for j, (step, prefix) in enumerate(steps):
            idx = int(rng.integers(n_tools))
            if j == 1 and first_idx is not None and rng.random() < coupling:
                idx = first_idx
            if j == 0:
                first_idx = idx
            tool = f"{prefix}-{idx + 1:02d}"
            chamber = chr(ord("A") + int(rng.integers(n_chambers)))
            key = (step, tool, chamber)
            if key not in pm:
                pm[key] = base - pd.Timedelta(days=int(rng.integers(5, 60)))
            rows.append({"lot": L, "step": step, "tool": tool, "chamber": chamber,
                         "start_time": (base + pd.Timedelta(days=i, hours=6 * j)).isoformat(),
                         "pm_date": pm[key].date().isoformat()})
    hist = pd.DataFrame(rows)
    for step, tool in planted.items():
        if not ((hist["step"] == step) & (hist["tool"] == tool)).any():
            raise ValueError(f"planted {step}:{tool} 이 합성 이력에 없다 (n_tools={n_tools} 안의 이름이어야 한다).")
    return hist


def synthetic_predictions(history: pd.DataFrame, pattern: str = "EDGE_LOC",
                          planted: dict[str, str] | None = None, seed: int = 0,
                          base_frac: float = 0.1, planted_frac: float = 0.6,
                          wafers_per_lot: tuple[int, int] = (3, 8)) -> pd.DataFrame:
    """합성 이력에 맞는 합성 예측. 열: lot, wafer_index, y_pred.

    planted 의 (step, tool) 을 지난 로트는 패턴 비율 planted_frac, 나머지는 base_frac. 로트당 장수는
    wafers_per_lot 범위의 난수(결함 부분집합처럼 적게).
    """
    rng = np.random.default_rng(seed)
    planted = planted or {}
    through = set()
    for step, tool in planted.items():
        through |= set(history.loc[(history["step"] == step) & (history["tool"] == tool), "lot"].astype(str))
    rows = []
    for L in history["lot"].astype(str).unique():
        frac = planted_frac if L in through else base_frac
        n = int(rng.integers(wafers_per_lot[0], wafers_per_lot[1] + 1))
        for w in range(1, n + 1):
            y = pattern if rng.random() < frac else str(rng.choice(OTHER_LABELS))
            rows.append({"lot": L, "wafer_index": w, "y_pred": y})
    return pd.DataFrame(rows)


DEMO_PLANTED = {"ETCH_M1": "ETCH-02"}
DEMO_PATTERN = "EDGE_LOC"


# ──────────────────────────────────────────
# 5. CLI
# ──────────────────────────────────────────
def _format_summary(tab: pd.DataFrame, status: pd.Series, history: pd.DataFrame, label: str,
                    min_frac: float, min_n: int, top: int = 8) -> list[str]:
    pattern = tab.attrs.get("pattern", "")
    n_lots, n_bad = tab.attrs.get("n_lots_total", 0), tab.attrs.get("n_bad_total", 0)
    lines = [
        f"tool commonality - {label} - pattern {pattern}",
        f"  lot positive = fraction of {pattern} wafers >= {min_frac:g} and lot size >= {min_n} "
        f"(lots dropped for size: {status.attrs.get('n_dropped', 0)})",
        f"  lots with status and history: {n_lots}, positive: {n_bad} ({(n_bad / n_lots if n_lots else 0):.3f})",
        "  Fisher one-sided (unit worse than rest of same step), BH within step, n_lots<5 = insufficient evidence",
    ]
    show = tab.head(top).copy()
    fmt = {"rate": "{:.3f}", "rate_other": "{:.3f}", "rate_ratio": "{:.2f}", "ci_lo": "{:.2f}", "ci_hi": "{:.2f}",
           "p_fisher": "{:.2g}", "q_bh": "{:.2g}", "overlap_with_top": "{:.2f}"}
    for c, f in fmt.items():
        show[c] = show[c].map(lambda v, f=f: f.format(v) if pd.notna(v) else "nan")
    cols = ["step", "tool", "chamber", "n_lots", "n_bad", "rate", "rate_other", "rate_ratio", "ci_lo", "ci_hi",
            "p_fisher", "q_bh", "overlap_with_top", "evidence", "note"]
    lines.append("  " + show[cols].to_string(index=False).replace("\n", "\n  "))
    sig = tab[(tab["evidence"] == "ok") & (tab["q_bh"] < Q_ALPHA)]
    if len(sig) == 0:
        lines.append("  verdict: no unit stands out (q >= 0.05 everywhere with sufficient evidence). "
                     "Commonality does not point at one tool - look at time trend (wm811k_spc.py) and slot (wm811k_slot.py).")
    else:
        top_r = sig.iloc[0]
        unit = f"{top_r['step']} {top_r['tool']}{('/' + str(top_r['chamber'])) if str(top_r['chamber']) else ''}"
        lines.append(f"  verdict: top candidate {unit}: {top_r['n_bad']}/{top_r['n_lots']} lots positive "
                     f"({top_r['rate']:.2f}) vs rest of step {top_r['rate_other']:.2f}, rate ratio {top_r['rate_ratio']:.2f} "
                     f"[{top_r['ci_lo']:.2f}, {top_r['ci_hi']:.2f}], q={top_r['q_bh']:.2g}")
        conf = sig[sig["note"].str.startswith("routing overlap")]
        if len(conf):
            lines.append("  WARNING routing confound: " + "; ".join(
                f"{r['step']} {r['tool']}/{r['chamber']} shares {r['overlap_with_top']:.0%} of its lots with the top unit"
                for _, r in conf.iterrows()) + " - split by lots that passed only one of them, or compare PM/part history of both.")
        lines.append("  next: pull that unit's tool-side evidence (alarm log, part counters, recipe/PM history) and "
                     "put the first positive lot on the time axis (wm811k_spc.py --event-col). Correlation, not cause.")
        pm = pm_age_summary(history, status, str(top_r["step"]), str(top_r["tool"]),
                            str(top_r["chamber"]) if str(top_r["chamber"]) else None)
        if pm:
            lines.append(f"  PM age (start_time - pm_date, days) at top unit: median positive lots "
                         f"{pm['median_days_bad']:.0f} (n={pm['n_bad']}) vs negative {pm['median_days_good']:.0f} "
                         f"(n={pm['n_good']}). Longer = wear, shorter = post-PM particles/seasoning (generic reading).")
    return lines


def run(preds: pd.DataFrame, history: pd.DataFrame, pattern: str, out_dir: Path, by=DEFAULT_BY,
        min_frac: float = DEFAULT_MIN_FRAC, min_n: int = DEFAULT_MIN_N, min_lots: int = DEFAULT_MIN_LOTS,
        label: str = "") -> dict:
    """상태 -> 표 -> 요약 -> 그림. out_dir 에 저장하고 dict(status, table) 를 돌려준다."""
    out_dir.mkdir(parents=True, exist_ok=True)
    status = lot_pattern_status(preds, pattern, min_frac, min_n)
    missing = set(status.index.astype(str)) - set(history["lot"].astype(str))
    if missing:
        print(f"[주의] 예측에는 있으나 이력에 없는 로트 {len(missing)}개 (예: {sorted(missing)[:3]}) - 공통성 표에서 제외.")
    tab = commonality_table(history, status, by, min_lots)
    stem = f"commonality_{pattern}"
    tab.to_csv(out_dir / f"{stem}.csv", index=False, encoding="utf-8-sig")
    lines = _format_summary(tab, status, history, label or "predictions", min_frac, min_n)
    print("\n" + "\n".join(lines))
    with open(out_dir / f"{stem}_summary.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    fig, ax = plt.subplots(figsize=(8, 0.35 * min(12, len(tab)) + 1.6))
    plot_commonality(tab, ax, title=f"{pattern} commonality - {label or 'predictions'}")
    fig.tight_layout()
    fig.savefig(out_dir / f"{stem}.png", dpi=110)
    plt.close(fig)
    print(f"  saved: {out_dir / (stem + '.csv')}, {out_dir / (stem + '_summary.txt')}, {out_dir / (stem + '.png')}")
    return {"status": status, "table": tab}


def run_demo(out_dir: Path, n_lots: int = 200, seed: int = 0) -> bool:
    """합성 이력 2종(독립 라우팅 / 라우팅 혼입)으로 로직 확인. 기대와 일치하면 True."""
    print(f"[demo] synthetic history, {n_lots} lots, planted {DEMO_PLANTED} with {DEMO_PATTERN} fraction 0.6 vs 0.1. "
          "Fictional IDs. Logic check, not performance.")
    ok_all = True
    lots = [f"demoLot{i:04d}" for i in range(n_lots)]
    for name, coupling in (("independent_routing", 0.0), ("coupled_routing_0.9", 0.9)):
        hist = synthetic_history(lots, seed, DEMO_PLANTED, coupling=coupling)
        preds = synthetic_predictions(hist, DEMO_PATTERN, DEMO_PLANTED, seed)
        res = run(preds, hist, DEMO_PATTERN, out_dir / name, label=f"demo {name}")
        tab = res["table"]
        top = tab[tab["evidence"] == "ok"].iloc[0]
        got_top = (top["step"], top["tool"]) == next(iter(DEMO_PLANTED.items())) and top["q_bh"] < Q_ALPHA
        if coupling == 0.0:
            other = tab[(tab["step"] != "ETCH_M1") & (tab["evidence"] == "ok")]
            quiet = bool((other["q_bh"] >= Q_ALPHA).all())
            ok = got_top and quiet
            print(f"  expected: ETCH_M1 ETCH-02 on top with q<0.05 and other steps quiet -> "
                  f"top={'OK' if got_top else 'MISMATCH'}, other steps quiet={'OK' if quiet else 'MISMATCH'}")
        else:
            flagged = bool(tab["note"].str.startswith("routing overlap").any())
            ok = got_top and flagged
            print(f"  expected: ETCH-02 on top and the coupled CVD unit flagged as routing confound -> "
                  f"top={'OK' if got_top else 'MISMATCH'}, flag={'OK' if flagged else 'MISMATCH'}")
        ok_all &= ok
    print(f"\n[demo] {'all as expected' if ok_all else 'MISMATCH - check logic'}; outputs under {out_dir}")
    return ok_all


def _cli(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="로트 이력으로 패턴 양성 로트가 공유한 단계·장비·챔버를 찾는다 (Fisher + BH, 라우팅 혼입 경고).")
    ap.add_argument("predictions", nargs="?", type=Path, default=None, help="예측 CSV (lot, y_pred 필요)")
    ap.add_argument("--history", type=Path, default=None, help="로트 이력 CSV (docs/lot_history_schema.md)")
    ap.add_argument("--pattern", default=DEMO_PATTERN, help=f"대상 패턴 (기본 {DEMO_PATTERN})")
    ap.add_argument("--by", nargs="+", default=list(DEFAULT_BY), help="층 + 단위 열 (기본 step tool chamber)")
    ap.add_argument("--min-frac", type=float, default=DEFAULT_MIN_FRAC, help="로트 양성 기준 패턴 비율 (기본 0.3)")
    ap.add_argument("--min-n", type=int, default=DEFAULT_MIN_N, help="로트 양성 판정에 필요한 최소 장수 (기본 1; 팹 데이터는 5 권장)")
    ap.add_argument("--min-lots", type=int, default=DEFAULT_MIN_LOTS, help="이보다 적은 로트를 지난 단위는 근거 부족 (기본 5)")
    ap.add_argument("--output", type=Path, default=None, help="출력 폴더 (기본 HERE/commonality_out, --demo 는 HERE/commonality_demo)")
    ap.add_argument("--demo", action="store_true", help="합성 이력으로 로직 확인 (성능 아님)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> dict | None:
    a = _cli(argv)
    if a.demo:
        if not run_demo(a.output or HERE / "commonality_demo"):
            sys.exit(1)
        return None
    if a.predictions is None or a.history is None:
        sys.exit("예측 CSV 와 --history 이력 CSV 가 필요하다 (또는 --demo).")
    preds = pd.read_csv(a.predictions)
    history = load_lot_history(a.history)
    return run(preds, history, a.pattern, a.output or HERE / "commonality_out", tuple(a.by),
               a.min_frac, a.min_n, a.min_lots, label=a.predictions.name)


if __name__ == "__main__":
    matplotlib.use("Agg")
    main()
