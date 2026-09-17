# wm811k_spc.py
# 분류 결과에 SPC 관리도를 붙인다 — 패턴별 p 관리도 + 저신뢰 비율 관리도 + EWMA
#
# 무엇을 감시하나
#   웨이퍼 한 장의 판정은 wafer_pattern_classifier / wm811k_train 이 한다.
#   이 스크립트는 그 위 단계다. 판정 결과를 시간 순서로 부분군(subgroup)에 묶어
#   "이 패턴의 비율이 평소보다 늘고 있는가"를 관리도로 본다. 한 장씩은 정상 범위인데
#   방향이 한쪽으로 기우는 것(소모품 마모, 챔버 오염 축적)을 잡는 것이 목적이다.
#
# 관리도
#   [p 관리도]  부분군마다 패턴 X로 판정된 웨이퍼 비율. 부분군 크기 n_i가 달라도
#               한계를 n_i마다 다시 계산한다: p̄ ± 3·sqrt(p̄(1-p̄)/n_i)
#               정규 근사가 성립하려면 n·p̄ ≥ 5 여야 한다. NEAR_FULL(0.6%)처럼 드문
#               패턴은 25장 부분군이면 p가 0 아니면 0.04라 규칙이 헛울린다. 그래서
#               패턴마다 부분군을 n·p̄ ≥ 5 가 되도록 자동으로 키운다(기본 크기의 배수).
#               x축은 부분군 번호가 아니라 웨이퍼 순번이라 크기가 달라도 같은 축에 놓인다.
#   [저신뢰 p]  신뢰도 < 임계값인 웨이퍼 비율. 분류기가 헷갈리는 웨이퍼가 갑자기
#               늘면 새 패턴이 나타났거나 분류기가 낡았다는 신호다. 모델을 감시하는 관리도.
#   [Laney p′]  로트 사이 변동이 이항 분산보다 크면(과산포) 보통 p 관리도는 계속 헛울린다.
#               같은 로트의 웨이퍼가 패턴을 공유하는 반도체 데이터가 정확히 그 경우다.
#               Laney 보정은 baseline z 점수의 이동 범위로 σ_z를 재서 한계를 σ_z 배 넓힌다.
#               기본으로 켜져 있고 σ_z 를 출력한다. σ_z ≈ 1 이면 보정이 없는 것과 같다.
#   [EWMA]      z 점수의 지수가중 이동평균. 0.5σ 수준의 작은 이동을 3σ 규칙보다 빨리 잡는다.
#   [fail_frac] 예측 CSV에 불량 비율 열이 있으면 부분군 평균의 I-MR 관리도도 그린다.
#
# 규칙 (Western Electric)
#   R1  3σ 밖 1점            R2  연속 3점 중 2점이 같은 쪽 2σ 밖
#   R3  연속 5점 중 4점이 같은 쪽 1σ 밖    R4  연속 8점이 중심선 같은 쪽
#
# Phase I / Phase II
#   한계는 앞부분(기본 50%)의 안정 구간(baseline)에서만 잡고, 나머지를 감시한다.
#   전체로 한계를 잡으면 이상이 한계 안으로 흡수된다. baseline 안에서 규칙이 울리면
#   그 구간이 안정이 아니었다는 뜻이므로 따로 보고한다.
#
# 시간 순서
#   WM-811K에는 시각이 없다. 기본값은 CSV의 행 순서(원본 데이터셋 순서)를 시간의
#   대리로 쓴다. 실제 팹 데이터라면 --time-col 로 시각 열을 지정한다.
#
# 입력: wm811k_evaluate.py 의 wm811k_predictions.csv 또는 wm811k_train.py 의
#       {val,test}_predictions.csv. lot, y_pred 열이 필요하고 confidence, fail_frac 는 선택.
#
# 사용
#   python wm811k_spc.py runs/wm811k/seed_42/cnn/test_predictions.csv
#   python wm811k_spc.py --demo          # 합성 시퀀스에 드리프트를 심어 탐지 확인

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from batch_wafer_report import setup_korean_font
from wafer_pattern_classifier import ACTIONS

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
CLASSES = ["CENTER", "DONUT", "EDGE_LOC", "EDGE_RING",
           "LOC", "NEAR_FULL", "RANDOM", "SCRATCH"]

EWMA_LAMBDA = 0.2
EWMA_L = 2.7

# 색은 wafer_map_visualizer 와 맞춘다. 알람은 색만이 아니라 마커 모양으로도 구분한다.
INK, MUTED, LIMIT = "#455A64", "#78909C", "#B0BEC5"
BASELINE_BG = "#ECEFF1"
ALARM_STYLE = {                # rule → (marker, color, label)
    "R1": ("o", "#F44336", "R1 3σ 밖"),
    "R2": ("^", "#FB8C00", "R2 2/3점 2σ 밖"),
    "R3": ("v", "#FB8C00", "R3 4/5점 1σ 밖"),
    "R4": ("s", "#8E24AA", "R4 8점 한쪽"),
    "EWMA": ("D", "#1565C0", "EWMA"),
}


# ──────────────────────────────────────────
# 1. 입력 정리
# ──────────────────────────────────────────
def load_predictions(path: Path, time_col: str | None = None) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "y_pred" not in df.columns or "lot" not in df.columns:
        sys.exit(f"{path.name}: lot, y_pred 열이 필요하다. 열: {list(df.columns)}")
    if "skipped" in df.columns:                       # wm811k_evaluate.py 형식
        df = df[~df["skipped"].astype(bool)]
    df = df[df["y_pred"].notna()].copy()
    df["lot"] = df["lot"].astype(str)
    if time_col:
        if time_col not in df.columns:
            sys.exit(f"--time-col {time_col} 열이 없다.")
        df = df.sort_values(time_col, kind="stable")
    return df.reset_index(drop=True)


def chunk_ids(df: pd.DataFrame, target: int, by_lot: bool) -> np.ndarray:
    """행을 시간 순서대로 크기 ≥ target 인 부분군에 묶는다. 부분군 번호 배열을 반환.

    by_lot=True 면 로트를 쪼개지 않고 연속 로트를 target 이 될 때까지 합친다.
    마지막 조각이 target 의 절반보다 작으면 버린다(-1).
    """
    n = len(df)
    if by_lot:
        gid = np.empty(n, dtype=int)
        lot = df["lot"].to_numpy()
        g, size, start = 0, 0, 0
        for i in range(n):
            size += 1
            last_of_lot = i == n - 1 or lot[i + 1] != lot[i]
            if last_of_lot and size >= target:
                gid[start: i + 1] = g
                g, size, start = g + 1, 0, i + 1
        gid[start:] = g if size >= target / 2 else -1
        return gid
    gid = np.arange(n) // target
    if n % target and n % target < target / 2:
        gid[gid == gid.max()] = -1
    return gid


def summarize(df: pd.DataFrame, gid: np.ndarray, column: str, match) -> pd.DataFrame:
    """부분군별 n, 조건 충족 수, 끝 웨이퍼 순번, 로트 표기."""
    d = pd.DataFrame({"gid": gid, "lot": df["lot"].to_numpy(),
                      "hit": match(df[column].to_numpy()) if column else 0,
                      "idx": np.arange(len(df))})
    d = d[d["gid"] >= 0]
    g = d.groupby("gid")
    out = pd.DataFrame({"n": g.size(), "count": g["hit"].sum().astype(int),
                        "end_idx": g["idx"].max(),
                        "lots": g["lot"].agg(lambda s: ",".join(pd.unique(s)[:3]) + ("…" if s.nunique() > 3 else ""))})
    return out.reset_index(drop=True)


# ──────────────────────────────────────────
# 2. 관리도 계산
# ──────────────────────────────────────────
@dataclass
class Chart:
    name: str
    value: np.ndarray          # 부분군별 관측값 (p 또는 평균)
    center: float
    sigma: np.ndarray          # 부분군별 σ (n_i 에 따라 다름)
    z: np.ndarray
    ewma: np.ndarray
    ewma_limit: np.ndarray
    alarms: dict[str, np.ndarray]     # rule → bool 배열 (규칙이 완성되는 점에 표시)
    ucl: np.ndarray
    lcl: np.ndarray
    end_idx: np.ndarray        # 부분군 끝 웨이퍼 순번 (x축)
    n: np.ndarray              # 부분군 크기
    n_base: int                # baseline 부분군 수
    kind: str = "p"            # "p" | "mean"
    sigma_z: float = 1.0       # Laney 과산포 계수 (1이면 보정 없음)


def western_electric(z: np.ndarray) -> dict[str, np.ndarray]:
    n = len(z)
    r1 = np.abs(z) > 3
    r2 = np.zeros(n, bool)
    r3 = np.zeros(n, bool)
    r4 = np.zeros(n, bool)
    for i in range(n):
        for side in (1, -1):
            w3 = side * z[max(0, i - 2): i + 1]
            w5 = side * z[max(0, i - 4): i + 1]
            w8 = side * z[max(0, i - 7): i + 1]
            if len(w3) == 3 and (w3 > 2).sum() >= 2:
                r2[i] = True
            if len(w5) == 5 and (w5 > 1).sum() >= 4:
                r3[i] = True
            if len(w8) == 8 and (w8 > 0).all():
                r4[i] = True
    return {"R1": r1, "R2": r2, "R3": r3, "R4": r4}


def ewma_chart(z: np.ndarray, lam: float = EWMA_LAMBDA, L: float = EWMA_L):
    e = np.zeros(len(z))
    prev = 0.0
    for i, v in enumerate(z):
        prev = lam * v + (1 - lam) * prev
        e[i] = prev
    i = np.arange(1, len(z) + 1)
    limit = L * np.sqrt(lam / (2 - lam) * (1 - (1 - lam) ** (2 * i)))
    return e, limit


MIN_EXPECTED = 5.0     # 정규 근사 조건 n·p̄ ≥ 5


def _finish(name, value, center, sigma, S, n_base, kind, clip=None, sigma_z=1.0):
    z = (value - center) / sigma
    e, lim = ewma_chart(z)
    alarms = western_electric(z)
    alarms["EWMA"] = np.abs(e) > lim
    ucl, lcl = center + 3 * sigma, center - 3 * sigma
    if clip is not None:
        ucl, lcl = np.clip(ucl, *clip), np.clip(lcl, *clip)
    return Chart(name, value, center, sigma, z, e, lim, alarms, ucl, lcl,
                 end_idx=S["end_idx"].to_numpy(), n=S["n"].to_numpy(), n_base=n_base,
                 kind=kind, sigma_z=sigma_z)


def laney_factor(z_base: np.ndarray) -> float:
    """Laney p′: baseline z 점수의 이동 범위 평균 / d2. 1보다 작으면 1 (좁히지는 않는다)."""
    if len(z_base) < 3:
        return 1.0
    return max(1.0, float(np.abs(np.diff(z_base)).mean() / 1.128))


def p_chart(name: str, S: pd.DataFrame, n_base: int, laney: bool = True) -> Chart | None:
    count, n = S["count"].to_numpy(), S["n"].to_numpy()
    p_bar = float(count[:n_base].sum() / n[:n_base].sum())
    if p_bar <= 0 or p_bar >= 1:
        return None                              # baseline에 없는(또는 전부인) 패턴은 감시 불가
    sigma = np.sqrt(p_bar * (1 - p_bar) / n)
    sigma_z = laney_factor(((count / n - p_bar) / sigma)[:n_base]) if laney else 1.0
    return _finish(name, count / n, p_bar, sigma * sigma_z, S, n_base, "p",
                   clip=(0, 1), sigma_z=sigma_z)


def mean_chart(name: str, S: pd.DataFrame, x: np.ndarray, n_base: int) -> Chart | None:
    """부분군 평균의 I-MR 관리도. σ는 baseline 이동 범위 평균 / d2(=1.128)."""
    base = x[:n_base]
    if len(base) < 3:
        return None
    center = float(base.mean())
    sigma_scalar = np.abs(np.diff(base)).mean() / 1.128
    if sigma_scalar <= 0:
        return None
    sigma = np.full(len(x), sigma_scalar)
    return _finish(name, x, center, sigma, S, n_base, "mean")


def baseline_groups(S: pd.DataFrame, n_base_rows: int) -> int:
    """끝 순번이 baseline 행 범위 안에 있는 부분군 수 (최소 3)."""
    return max(3, int((S["end_idx"] < n_base_rows).sum()))


def build_charts(df: pd.DataFrame, classes: list[str], base_size: int, by_lot: bool,
                 n_base_rows: int, conf_threshold: float,
                 laney: bool = True) -> tuple[list[Chart], dict[str, int], list[str]]:
    """패턴마다 n·p̄ ≥ 5 가 되도록 부분군 크기를 base_size 의 배수로 키워 관리도를 만든다."""
    charts, sizes, dropped = [], {}, []
    y = df["y_pred"].to_numpy()
    targets = {c: (y == c) for c in classes}
    if "confidence" in df.columns:
        targets["LOW_CONFIDENCE"] = df["confidence"].to_numpy() < conf_threshold
    for name, hit in targets.items():
        p0 = hit[:n_base_rows].mean()
        if p0 <= 0:
            dropped.append(name)
            continue
        k = int(np.ceil(MIN_EXPECTED / p0 / base_size))
        size = k * base_size
        gid = chunk_ids(df, size, by_lot)
        S = summarize(df, gid, None, None)
        S["count"] = pd.Series(hit).groupby(gid).sum().reindex(range(len(S))).to_numpy().astype(int) \
            if (gid >= 0).all() else pd.Series(hit[gid >= 0]).groupby(gid[gid >= 0]).sum().to_numpy().astype(int)
        n_base = baseline_groups(S, n_base_rows)
        if len(S) - n_base < 2:
            dropped.append(name)
            continue
        ch = p_chart(name, S, n_base, laney)
        if ch is None:
            dropped.append(name)
            continue
        charts.append(ch)
        sizes[name] = size
    if "fail_frac" in df.columns:
        gid = chunk_ids(df, base_size, by_lot)
        S = summarize(df, gid, None, None)
        x = pd.Series(df["fail_frac"].to_numpy()[gid >= 0]).groupby(gid[gid >= 0]).mean().to_numpy()
        ch = mean_chart("FAIL_FRAC_MEAN", S, x, baseline_groups(S, n_base_rows))
        if ch is not None:
            charts.append(ch)
            sizes["FAIL_FRAC_MEAN"] = base_size
    return charts, sizes, dropped


# ──────────────────────────────────────────
# 3. 보고
# ──────────────────────────────────────────
def alarm_table(charts: list[Chart]) -> pd.DataFrame:
    rows = []
    for ch in charts:
        for rule, mask in ch.alarms.items():
            for i in np.nonzero(mask)[0]:
                rows.append({"chart": ch.name, "subgroup": int(i), "wafer_end_idx": int(ch.end_idx[i]),
                             "phase": "baseline" if i < ch.n_base else "monitor",
                             "rule": rule, "value": float(ch.value[i]), "z": float(ch.z[i]),
                             "direction": "up" if ch.z[i] > 0 else "down"})
    cols = ["chart", "subgroup", "wafer_end_idx", "phase", "rule", "value", "z", "direction"]
    return pd.DataFrame(rows, columns=cols).sort_values(["chart", "wafer_end_idx"]).reset_index(drop=True)


def first_detection(alarms: pd.DataFrame) -> pd.DataFrame:
    """감시 구간에서 규칙별로 처음 울린 시점(웨이퍼 순번). '얼마나 빨리 잡았나'를 본다."""
    mon = alarms[alarms["phase"] == "monitor"]
    if mon.empty:
        return pd.DataFrame(columns=["chart", "rule", "first_wafer_idx"])
    return (mon.groupby(["chart", "rule"])["wafer_end_idx"].min()
            .rename("first_wafer_idx").reset_index())


def plot_charts(charts: list[Chart], n_base_rows: int, out_png: Path, title: str) -> None:
    rows = len(charts)
    fig, axes = plt.subplots(rows, 1, figsize=(12, 2.0 * rows + 1.0), sharex=True,
                             squeeze=False, layout="constrained")
    for ax, ch in zip(axes[:, 0], charts):
        x = ch.end_idx
        ax.axvspan(0, n_base_rows, color=BASELINE_BG, zorder=0)
        ax.plot(x, ch.ucl, color=LIMIT, lw=0.9, ls="--", drawstyle="steps-pre")
        ax.plot(x, ch.lcl, color=LIMIT, lw=0.9, ls="--", drawstyle="steps-pre")
        ax.axhline(ch.center, color=MUTED, lw=0.9)
        ax.plot(x, ch.value, color=INK, lw=1.1, zorder=2)
        n_alarm = {}
        for rule, mask in ch.alarms.items():
            idx = np.nonzero(mask)[0]
            n_alarm[rule] = int((idx >= ch.n_base).sum())
            if len(idx):
                m, col, _ = ALARM_STYLE[rule]
                ax.scatter(x[idx], ch.value[idx], marker=m, s=34, color=col,
                           edgecolor="white", linewidth=0.6, zorder=3)
        summary = "  ".join(f"{r} {k}" for r, k in n_alarm.items() if k)
        unit = "p̄" if ch.kind == "p" else "x̄"
        laney = f"   σz={ch.sigma_z:.2f}" if ch.sigma_z > 1 else ""
        ax.set_title(f"{ch.name}   {unit}={ch.center:.3f}   부분군 {int(np.median(ch.n))}장{laney}   "
                     f"감시 구간 알람: {summary or '없음'}", loc="left", fontsize=9, color=INK)
        ax.tick_params(labelsize=8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(False)
    axes[-1, 0].set_xlabel("웨이퍼 순번 (시간 순서)", fontsize=9)
    handles = [plt.Line2D([], [], marker=m, ls="", color=c, markeredgecolor="white", markersize=6, label=l)
               for m, c, l in ALARM_STYLE.values()]
    handles.append(matplotlib.patches.Patch(color=BASELINE_BG, label="baseline (한계 산출 구간)"))
    fig.legend(handles=handles, loc="outside lower center", ncol=6, fontsize=8, frameon=False)
    fig.suptitle(title, fontsize=11, color=INK, x=0.01, ha="left")
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


# ──────────────────────────────────────────
# 4. 데모 — 드리프트를 심은 합성 시퀀스
# ──────────────────────────────────────────
def demo_predictions(n_groups: int = 200, n: int = 25, seed: int = 0) -> pd.DataFrame:
    """WM-811K 라벨 비율로 판정을 뽑되, 후반에 EDGE_RING 드리프트와 SCRATCH 계단을 심는다.
    합성이다. 탐지 로직이 도는지 보는 용도이며 공정에 대한 정보는 없다."""
    rng = np.random.default_rng(seed)
    base = np.array([4294, 555, 5189, 9680, 3593, 149, 866, 1193], float)   # WM-811K 결함 8종 장수
    base /= base.sum()
    rows = []
    for g in range(n_groups):
        p = base.copy()
        if g >= 120:                                   # EDGE_RING 완만한 드리프트 (+0.15 over 40 groups)
            p[3] += 0.15 * min(1.0, (g - 120) / 40)
        if g >= 165:                                   # SCRATCH 계단
            p[7] += 0.10
        p /= p.sum()
        y = rng.choice(CLASSES, size=n, p=p)
        conf = rng.beta(8, 1.2, size=n)
        if g >= 150:                                   # 저신뢰 비율 증가 (모델 노후 신호)
            conf = np.where(rng.random(n) < 0.15, rng.uniform(0.3, 0.7, n), conf)
        rows.extend({"sample_id": g * n + i, "lot": f"lot{g:04d}", "y_pred": y[i],
                     "confidence": float(conf[i])} for i in range(n))
    return pd.DataFrame(rows)


# ──────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="분류 결과에 SPC 관리도를 붙인다.")
    ap.add_argument("predictions", nargs="?", type=Path, help="예측 CSV (lot, y_pred 필수)")
    ap.add_argument("--demo", action="store_true", help="합성 시퀀스로 탐지 확인 (성능 근거 아님)")
    ap.add_argument("--subgroup", default="25", help="'lot' 또는 기본 부분군 크기 (기본 25). 드문 패턴은 자동으로 배수만큼 키운다")
    ap.add_argument("--min-size", type=int, default=25, help="--subgroup lot 일 때 연속 로트를 이 크기가 될 때까지 합친다")
    ap.add_argument("--baseline-frac", type=float, default=0.5, help="한계를 잡는 앞부분 비율")
    ap.add_argument("--conf-threshold", type=float, default=0.7)
    ap.add_argument("--time-col", help="시간 순서로 정렬할 열 (없으면 행 순서)")
    ap.add_argument("--no-laney", action="store_true", help="Laney 과산포 보정을 끈다 (순수 이항 한계)")
    ap.add_argument("--classes", nargs="+", default=CLASSES)
    ap.add_argument("--output", type=Path, default=HERE / "spc")
    args = ap.parse_args()

    if args.demo:
        df = demo_predictions()
        title = "SPC 데모 — 합성 시퀀스 (웨이퍼 3000부터 EDGE_RING 드리프트, 3750부터 저신뢰 증가, 4125부터 SCRATCH 계단)"
        stem = "spc_demo"
    elif args.predictions:
        df = load_predictions(args.predictions, args.time_col)
        title = f"SPC — {args.predictions.name} (행 순서를 시간의 대리로 사용)"
        stem = "spc_" + args.predictions.stem
    else:
        ap.error("예측 CSV 경로를 주거나 --demo 를 지정하라.")

    by_lot = args.subgroup == "lot"
    base_size = args.min_size if by_lot else int(args.subgroup)
    if base_size < 2:
        ap.error("--subgroup 은 'lot' 또는 2 이상의 정수여야 한다.")
    n_base_rows = int(len(df) * args.baseline_frac)
    print(f"웨이퍼 {len(df):,}장, 기본 부분군 {'로트 병합 ≥' if by_lot else ''}{base_size}장, "
          f"baseline 웨이퍼 0–{n_base_rows - 1}, 감시 {n_base_rows}–{len(df) - 1}")

    charts, sizes, dropped = build_charts(df, args.classes, base_size, by_lot, n_base_rows,
                                          args.conf_threshold, laney=not args.no_laney)
    if not charts:
        sys.exit("그릴 관리도가 없다. 데이터가 너무 적거나 baseline에 패턴이 없다.")
    print("부분군 크기 (n·p̄ ≥ 5 조건):  " + "  ".join(f"{k} {v}" for k, v in sizes.items()))
    over = {ch.name: ch.sigma_z for ch in charts if ch.sigma_z > 1.05}
    if over:
        print("Laney 과산포 계수 σz (로트 간 변동이 이항 분산보다 큰 정도):  "
              + "  ".join(f"{k} {v:.2f}" for k, v in over.items()))
    if dropped:
        print(f"감시 불가 (baseline에 없거나 부분군이 너무 커져 감시 구간이 없음): {', '.join(dropped)}")

    alarms = alarm_table(charts)
    args.output.mkdir(parents=True, exist_ok=True)
    alarms.to_csv(args.output / f"{stem}_alarms.csv", index=False, encoding="utf-8-sig")
    pd.concat([pd.DataFrame({"chart": ch.name, "subgroup": np.arange(len(ch.value)), "n": ch.n,
                             "wafer_end_idx": ch.end_idx, "value": ch.value, "z": ch.z,
                             "ewma": ch.ewma, "ucl": ch.ucl, "lcl": ch.lcl}) for ch in charts]
              ).to_csv(args.output / f"{stem}_subgroups.csv", index=False, encoding="utf-8-sig")
    setup_korean_font()
    plot_charts(charts, n_base_rows, args.output / f"{stem}.png", title)

    print(f"\n{'=' * 70}\n감시 구간 알람 — 규칙별 첫 탐지 시점 (웨이퍼 순번)\n{'=' * 70}")
    fd = first_detection(alarms)
    if fd.empty:
        print("  없음")
    else:
        print(fd.pivot(index="chart", columns="rule", values="first_wafer_idx")
              .reindex(columns=list(ALARM_STYLE)).fillna("-").to_string())

    base_alarms = alarms[alarms["phase"] == "baseline"]
    n_base_points = sum(ch.n_base for ch in charts)
    base_rate = len(base_alarms) / max(n_base_points, 1)
    if base_rate > 0.05:
        print(f"\n[경고] baseline 구간 알람률 {base_rate:.0%} ({len(base_alarms)}건 / {n_base_points}점). "
              f"안정 공정이라면 규칙 5개를 다 켜도 1–2% 수준이다.\n"
              f"  이 시퀀스는 정상 상태가 아니거나 시간 순서가 아니다. WM-811K의 행 순서는 제품·로트 블록 순서라\n"
              f"  관리도가 공정 변화가 아니라 데이터셋 정렬을 잡는다. 실제 팹 데이터는 --time-col 로 시각을 지정하라.\n"
              f"  탐지 로직 자체를 확인하려면 --demo 를 써라.")
    elif not base_alarms.empty:
        print(f"\nbaseline 구간 알람 {len(base_alarms)}건 ({base_rate:.1%}) — 우연 범위 안이면 무시, "
              f"많으면 --baseline-frac 을 조정하거나 구간을 다시 골라라.")

    # 패턴별 조치 — 상승 방향 알람이 있는 결함 패턴만
    up = alarms[(alarms["phase"] == "monitor") & (alarms["direction"] == "up")]
    up_classes = [c for c in args.classes if c in set(up["chart"])]
    if up_classes:
        print(f"\n{'=' * 70}\n상승 알람이 있는 패턴과 점검 항목\n{'=' * 70}")
        for c in up_classes:
            print(f"  {c:10s} {ACTIONS.get(c, '')}")
    if "LOW_CONFIDENCE" in set(up["chart"]):
        print("  LOW_CONFIDENCE 저신뢰 웨이퍼 증가 — 새 패턴 출현 또는 분류기 노후. 저신뢰 웨이퍼를 직접 검토하라.")

    print(f"\n저장: {args.output / (stem + '.png')}\n      {args.output / (stem + '_subgroups.csv')}"
          f"\n      {args.output / (stem + '_alarms.csv')}")


if __name__ == "__main__":
    main()
