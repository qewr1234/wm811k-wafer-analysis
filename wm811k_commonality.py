# wm811k_commonality.py
# DA(Defect Analysis) 단계 — 패턴이 늘어난 로트들이 어느 공정 단계의 어느 장비를 공유하는지 찾는다.
#
# 흐름
#   분류기(웨이퍼별 패턴) → SPC(패턴 비율 상승 알람, wm811k_spc.py) → 여기(원인 장비 후보)
#   → ACTIONS(점검 항목, wafer_pattern_classifier.py)
#
# 방법 (commonality analysis)
#   로트마다 패턴 X 비율 r_lot 을 구한다. 공정 단계 s 의 장비 t 에 대해, t 를 지난 로트들의
#   r_lot 과 지나지 않은 로트들의 r_lot 을 비교한다.
#   - 검정 단위는 웨이퍼가 아니라 로트다. 같은 로트의 웨이퍼는 패턴을 공유하므로 웨이퍼 단위
#     검정(Fisher 등)은 표본을 부풀려 p 값이 터무니없이 작아진다. wm811k_spc.py 의 Laney
#     보정이 필요한 이유와 같다.
#   - Mann-Whitney U 단측 검정(지난 쪽이 크다) + Benjamini-Hochberg 다중비교 보정.
#     (단계 × 장비) 조합이 수십 개라 보정 없이는 항상 무언가가 "유의"하게 나온다.
#   - 효과 크기: 지난 로트 평균 비율 − 나머지 평균 비율 (Δ). 지지: 지난 로트 수 (MIN_LOTS 미만은 보류).
#
# 교락(confounding) 확인
#   단계 1의 장비 A 와 단계 2의 장비 B 를 같은 로트들이 함께 지나면(route 고정), A 가 원인이어도
#   B 도 유의하게 나온다. 1위 후보 A 를 지나지 않은 로트만으로 다시 검정해 살아남지 못하는 후보는
#   "A 와 교락 가능"으로 표시한다. 최종 확인은 데이터가 아니라 split-lot 실험(같은 로트를
#   A 와 다른 장비로 나눠 진행)이다. 이 스크립트는 실험 대상을 좁히는 도구다.
#
# 입력
#   predictions.csv : lot, y_pred (wm811k_evaluate.py / 학습 스크립트 출력). 웨이퍼 한 장이 한 행.
#   history.csv     : lot, step, tool (로트별 공정 단계·장비 이력). 로트 × 단계마다 한 행.
#                     WM-811K 에는 이 정보가 없다. --demo 는 합성 이력에 원인 장비 하나와
#                     교락 장비 하나를 심어 로직이 도는지 확인한다. 탐지 성능 근거가 아니다.
#
# 사용
#   python wm811k_commonality.py --demo
#   python wm811k_commonality.py test_predictions.csv history.csv --pattern EDGE_RING

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from wafer_pattern_classifier import ACTIONS

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
CLASSES = ["CENTER", "DONUT", "EDGE_LOC", "EDGE_RING",
           "LOC", "NEAR_FULL", "RANDOM", "SCRATCH"]
MIN_LOTS = 5
ALPHA = 0.05


# ──────────────────────────────────────────
# 1. 입력
# ──────────────────────────────────────────
def load_predictions(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "lot" not in df.columns or "y_pred" not in df.columns:
        sys.exit(f"{path.name}: lot, y_pred 열이 필요하다. 열: {list(df.columns)}")
    if "skipped" in df.columns:
        df = df[~df["skipped"].astype(bool)]
    df = df[df["y_pred"].notna()].copy()
    df["lot"] = df["lot"].astype(str)
    return df.reset_index(drop=True)


def load_history(path: Path) -> pd.DataFrame:
    h = pd.read_csv(path)
    need = {"lot", "step", "tool"}
    if not need <= set(h.columns):
        sys.exit(f"{path.name}: lot, step, tool 열이 필요하다. 열: {list(h.columns)}")
    h = h[["lot", "step", "tool"]].astype(str).drop_duplicates()
    dup = h.duplicated(["lot", "step"], keep=False)
    if dup.any():
        sys.exit(f"{path.name}: 같은 로트가 한 단계에서 장비 둘 이상에 배정됐다 ({int(dup.sum())}행). "
                 "split-lot 이면 lot 을 나눠 적어라.")
    return h.reset_index(drop=True)


def lot_rates(pred: pd.DataFrame, pattern: str) -> pd.DataFrame:
    """로트별 패턴 비율. 이것이 검정의 관측 단위다."""
    g = pred.groupby("lot")["y_pred"]
    return pd.DataFrame({"n_wafers": g.size(), "rate": g.apply(lambda s: float((s == pattern).mean()))})


# ──────────────────────────────────────────
# 2. 검정
# ──────────────────────────────────────────
def bh_adjust(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg. NaN 은 그대로 둔다."""
    p = np.asarray(p, dtype=float)
    out = np.full_like(p, np.nan)
    ok = ~np.isnan(p)
    m = int(ok.sum())
    if m == 0:
        return out
    order = np.argsort(p[ok])
    ranked = p[ok][order] * m / np.arange(1, m + 1)
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    adj = np.empty(m)
    adj[order] = np.clip(ranked, 0, 1)
    out[ok] = adj
    return out


def commonality(rates: pd.DataFrame, history: pd.DataFrame, min_lots: int = MIN_LOTS) -> pd.DataFrame:
    """(단계, 장비)마다 지난 로트 vs 나머지 로트의 패턴 비율을 비교한다."""
    h = history[history["lot"].isin(rates.index)]
    rows = []
    for (step, tool), grp in h.groupby(["step", "tool"]):
        through = rates.loc[grp["lot"].unique(), "rate"].to_numpy()
        step_lots = h.loc[h["step"] == step, "lot"].unique()
        others = rates.loc[np.setdiff1d(step_lots, grp["lot"].unique()), "rate"].to_numpy()
        row = {"step": step, "tool": tool, "n_lots": len(through), "n_others": len(others),
               "rate_through": float(through.mean()) if len(through) else np.nan,
               "rate_others": float(others.mean()) if len(others) else np.nan}
        row["delta"] = row["rate_through"] - row["rate_others"]
        if len(through) >= min_lots and len(others) >= min_lots and (np.ptp(np.r_[through, others]) > 0):
            row["p"] = float(mannwhitneyu(through, others, alternative="greater").pvalue)
        else:
            row["p"] = np.nan                    # 지지 부족 → 판정 보류
        rows.append(row)
    T = pd.DataFrame(rows)
    if T.empty:
        return T
    T["p_adj"] = bh_adjust(T["p"].to_numpy())
    return T.sort_values(["p_adj", "delta"], ascending=[True, False], na_position="last").reset_index(drop=True)


def confounding_check(rates: pd.DataFrame, history: pd.DataFrame, T: pd.DataFrame,
                      alpha: float = ALPHA, min_lots: int = MIN_LOTS) -> pd.DataFrame:
    """1위 후보를 지나지 않은 로트만으로 다시 검정한다. 거기서 죽는 후보는 1위와 교락 가능."""
    T = T.copy()
    T["confounded_with"] = ""
    sig = T[T["p_adj"] < alpha]
    if len(sig) < 2:
        return T
    top = sig.iloc[0]
    top_lots = history.loc[(history["step"] == top["step"]) & (history["tool"] == top["tool"]), "lot"].unique()
    rest = rates.drop(index=[l for l in top_lots if l in rates.index])
    if len(rest) < 2 * min_lots:
        return T
    T2 = commonality(rest, history, min_lots).set_index(["step", "tool"])
    for i in sig.index[1:]:
        key = (T.at[i, "step"], T.at[i, "tool"])
        if key in T2.index:
            p2 = T2.at[key, "p_adj"]
            if np.isnan(p2) or p2 >= alpha:
                T.at[i, "confounded_with"] = f"{top['step']}/{top['tool']}"
        else:
            T.at[i, "confounded_with"] = f"{top['step']}/{top['tool']} (로트 없음)"
    return T


# ──────────────────────────────────────────
# 3. 데모 — 원인 장비와 교락 장비를 심은 합성 이력
# ──────────────────────────────────────────
DEMO_STEPS = {"PHOTO": 4, "ETCH": 4, "DEP": 3, "CMP": 3, "CLEAN": 2}
DEMO_CAUSE = ("ETCH", "ETCH-03")
DEMO_CONFOUND = ("DEP", "DEP-02")


def demo_data(n_lots: int = 240, n_wafers: int = 25, seed: int = 0,
              effect: float = 0.20) -> tuple[pd.DataFrame, pd.DataFrame]:
    """패턴은 WM-811K 결함 8종 비율로 뽑는다(EDGE_RING ≈ 0.38). ETCH-03 을 지난 로트는
    EDGE_RING 확률에 +effect 를 더한다. ETCH-03 로트의 75% 는 DEP-02 로 고정 배정되어
    DEP-02 가 교락 후보로 같이 잡히도록 한다. effect=0 이면 심은 원인이 없는 귀무 데이터다."""
    rng = np.random.default_rng(seed)
    base = np.array([4294, 555, 5189, 9680, 3593, 149, 866, 1193], float)   # WM-811K 결함 8종 장수
    base /= base.sum()
    hist, pred = [], []
    for i in range(n_lots):
        lot = f"lot{i:04d}"
        tools = {s: f"{s}-{rng.integers(1, n + 1):02d}" for s, n in DEMO_STEPS.items()}
        if tools["ETCH"] == DEMO_CAUSE[1] and rng.random() < 0.75:
            tools["DEP"] = DEMO_CONFOUND[1]
        hist.extend({"lot": lot, "step": s, "tool": t} for s, t in tools.items())
        p = base.copy()
        if tools["ETCH"] == DEMO_CAUSE[1]:
            p[CLASSES.index("EDGE_RING")] += effect
        p /= p.sum()
        y = rng.choice(CLASSES, size=n_wafers, p=p)
        pred.extend({"lot": lot, "wafer": w, "y_pred": y[w]} for w in range(n_wafers))
    return pd.DataFrame(pred), pd.DataFrame(hist)


# ──────────────────────────────────────────
# 4. 보고
# ──────────────────────────────────────────
def plot_by_tool(rates: pd.DataFrame, history: pd.DataFrame, T: pd.DataFrame, pattern: str,
                 out_png: Path, alpha: float = ALPHA, n_steps: int = 3) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from batch_wafer_report import setup_korean_font
    setup_korean_font()

    steps = list(dict.fromkeys(T["step"]))[:n_steps]
    fig, axes = plt.subplots(1, len(steps), figsize=(3.6 * len(steps) + 1, 3.6), squeeze=False,
                             layout="constrained", sharey=True)
    h = history[history["lot"].isin(rates.index)]
    for ax, step in zip(axes[0], steps):
        sub = T[T["step"] == step].sort_values("tool")
        hs = h[h["step"] == step]
        for k, (_, row) in enumerate(sub.iterrows()):
            vals = rates.loc[hs.loc[hs["tool"] == row["tool"], "lot"].unique(), "rate"].to_numpy()
            sig = (not np.isnan(row["p_adj"])) and row["p_adj"] < alpha
            ax.bar(k, vals.mean(), color="#F44336" if sig else "#B0BEC5", width=0.6)
            ax.scatter(np.full(len(vals), k) + np.random.default_rng(k).uniform(-0.18, 0.18, len(vals)),
                       vals, s=8, color="#455A64", alpha=0.6, zorder=3)
            ax.text(k, 0, f"n={row['n_lots']}", ha="center", va="bottom", fontsize=7, color="white")
        ax.set_xticks(range(len(sub)))
        ax.set_xticklabels(sub["tool"], fontsize=8, rotation=20)
        ax.set_title(step, loc="left", fontsize=9)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0][0].set_ylabel(f"로트별 {pattern} 비율")
    fig.suptitle(f"{pattern} — 장비별 로트 비율 (빨강: BH 보정 p < {alpha})", fontsize=10, x=0.01, ha="left")
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def report(T: pd.DataFrame, pattern: str, alpha: float) -> None:
    print(f"\n{'=' * 78}\n{pattern} — 공정 단계·장비별 commonality (로트 단위 Mann-Whitney, BH 보정)\n{'=' * 78}")
    show = T.copy()
    show["rate_through"] = show["rate_through"].map("{:.3f}".format)
    show["rate_others"] = show["rate_others"].map("{:.3f}".format)
    show["delta"] = show["delta"].map("{:+.3f}".format)
    show["p_adj"] = show["p_adj"].map(lambda v: "보류" if np.isnan(v) else f"{v:.2e}")
    cols = ["step", "tool", "n_lots", "rate_through", "rate_others", "delta", "p_adj", "confounded_with"]
    print(show[cols].head(12).to_string(index=False))
    sig = T[T["p_adj"] < alpha]
    if sig.empty:
        print(f"\n  유의한 장비 없음 (BH 보정 p ≥ {alpha}). 패턴이 장비가 아니라 시간·제품·원자재에 붙어 있을 수 있다.")
        return
    top = sig.iloc[0]
    print(f"\n  1위 후보: {top['step']} / {top['tool']}  (로트 {top['n_lots']}개, Δ {top['delta']:+.3f}, "
          f"p_adj {top['p_adj']:.2e})")
    conf = sig[sig["confounded_with"] != ""]
    if not conf.empty:
        print("  교락 가능 (1위 후보를 뺀 로트에서는 유의하지 않음): "
              + ", ".join(f"{r['step']}/{r['tool']}" for _, r in conf.iterrows()))
    indep = sig.iloc[1:][sig.iloc[1:]["confounded_with"] == ""]
    if not indep.empty:
        print("  독립적으로 유의 (별도 원인 가능): " + ", ".join(f"{r['step']}/{r['tool']}" for _, r in indep.iterrows()))
    print(f"  점검 항목 [{pattern}]: {ACTIONS.get(pattern, '')}")
    print(f"  다음 단계: {top['step']} 에서 {top['tool']} 과 다른 장비로 split-lot 을 흘려 확인한다.")


def run(pred: pd.DataFrame, history: pd.DataFrame, pattern: str, alpha: float, min_lots: int,
        out_dir: Path, stem: str, plot: bool = True) -> pd.DataFrame:
    rates = lot_rates(pred, pattern)
    T = commonality(rates, history, min_lots)
    if T.empty:
        print(f"{pattern}: 이력과 겹치는 로트가 없다.")
        return T
    T = confounding_check(rates, history, T, alpha, min_lots)
    report(T, pattern, alpha)
    out_dir.mkdir(parents=True, exist_ok=True)
    T.to_csv(out_dir / f"{stem}_{pattern}.csv", index=False, encoding="utf-8-sig")
    if plot:
        plot_by_tool(rates, history, T, pattern, out_dir / f"{stem}_{pattern}.png", alpha)
    return T


def main():
    ap = argparse.ArgumentParser(description="패턴 비율이 높은 로트가 공유하는 공정 단계·장비를 찾는다.")
    ap.add_argument("predictions", nargs="?", type=Path, help="예측 CSV (lot, y_pred)")
    ap.add_argument("history", nargs="?", type=Path, help="공정 이력 CSV (lot, step, tool)")
    ap.add_argument("--pattern", help="분석할 패턴. 생략하면 예측에 있는 결함 8종 모두")
    ap.add_argument("--demo", action="store_true", help="합성 이력에 원인·교락 장비를 심어 로직 확인 (성능 근거 아님)")
    ap.add_argument("--alpha", type=float, default=ALPHA, help="BH 보정 후 유의 수준")
    ap.add_argument("--min-lots", type=int, default=MIN_LOTS, help="장비당 최소 로트 수 (미만이면 판정 보류)")
    ap.add_argument("--output", type=Path, default=HERE / "commonality")
    args = ap.parse_args()

    if args.demo:
        pred, history = demo_data()
        patterns = [args.pattern] if args.pattern else ["EDGE_RING"]
        stem = "demo"
        print(f"데모: 로트 {pred['lot'].nunique()}개 × {pred.groupby('lot').size().iloc[0]}장, "
              f"심은 원인 {DEMO_CAUSE[0]}/{DEMO_CAUSE[1]}, 교락 {DEMO_CONFOUND[0]}/{DEMO_CONFOUND[1]}")
    elif args.predictions and args.history:
        pred, history = load_predictions(args.predictions), load_history(args.history)
        patterns = [args.pattern] if args.pattern else [c for c in CLASSES if (pred["y_pred"] == c).any()]
        stem = args.predictions.stem
        common = set(pred["lot"]) & set(history["lot"])
        print(f"웨이퍼 {len(pred):,}장 / 예측 로트 {pred['lot'].nunique():,}개 / 이력 로트 "
              f"{history['lot'].nunique():,}개 / 겹침 {len(common):,}개")
        if not common:
            sys.exit("예측과 이력에 공통 로트가 없다. lot 표기를 맞춰라.")
    else:
        ap.error("예측 CSV 와 이력 CSV 를 주거나 --demo 를 지정하라.")

    summary = []
    for pat in patterns:
        T = run(pred, history, pat, args.alpha, args.min_lots, args.output, stem)
        if not T.empty:
            top = T.iloc[0]
            summary.append({"pattern": pat, "top": f"{top['step']}/{top['tool']}", "delta": top["delta"],
                            "p_adj": top["p_adj"], "significant": bool(top["p_adj"] < args.alpha)})
    if len(patterns) > 1 and summary:
        print(f"\n{'=' * 78}\n패턴별 1위 후보 요약\n{'=' * 78}")
        print(pd.DataFrame(summary).to_string(index=False))
    print(f"\n저장: {args.output}/{stem}_<PATTERN>.csv, .png")


if __name__ == "__main__":
    main()
