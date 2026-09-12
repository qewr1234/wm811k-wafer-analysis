# batch_wafer_report.py
# 여러 Lot 웨이퍼 맵 배치 PDF 리포트 생성기
#
# 원본 대비 수정 사항
#   [버그] generate_sample_wafer_data / plot_wafer_map / classify_wafer_pattern
#          import 누락 → NameError.
#   [버그] res = classify_wafer_pattern(df) 인데 result.yield_pct 를 참조 →
#          NameError. 변수명 불일치.
#   [버그] 로트 내 웨이퍼가 전부 픽셀 단위로 동일했다. 기본 seed=42 고정이라
#          같은 mode면 FAIL 개수까지 같은 데이터가 나온다. 5장을 나란히
#          그리는 의미가 사라진다. → 웨이퍼별 seed + noise.
#   [버그] wafers_per_lot=1 이면 plt.subplots 가 Axes 스칼라를 반환해
#          enumerate(axes) 가 실패한다. → squeeze=False.
#   [버그] 분류기를 호출하고도 결과를 버렸다. 페이지 제목의 "패턴"은
#          입력으로 넣은 정답을 그대로 출력한 것이어서, 분석 리포트에
#          분석 결과가 들어가 있지 않았다. → 분류 결과와 점수를 표시하고
#          입력과 불일치하면 표시한다.
#   [버그] matplotlib 기본 폰트(DejaVu Sans)에 한글 글리프가 없어 제목이
#          전부 두부(□□□)로 렌더링된다. → 한글 폰트 탐색 + 미발견 시 경고.
#   [버그] bbox_inches="tight" 는 페이지마다 PDF 크기를 다르게 만든다.
#          → A4 가로 고정.
#   [버그] plot_wafer_map 의 범례가 축 아래 bbox_to_anchor=(0.5,-0.13) 에
#          붙어 서브플롯 그리드에서 아래 행 제목과 겹친다.
#          → 축별 범례 제거 후 figure 단위 범례 1개.
#   [개선] 요약 페이지 추가. 웨이퍼 맵만 20장 붙어 있으면 넘겨보는 사람이
#          결론을 얻지 못한다. 로트별 집계표가 배치 리포트의 핵심이다.
#   [개선] 1×N 한 줄 배치 → 3열 그리드. A4 가로에서 종횡비가 맞는다.
#   [개선] defect_mode 7종 반영, random.choice 에 시드 부여.
#
# 주의: 합성 데이터다. 생성기와 분류기가 같은 규칙을 공유하므로 요약표의
#       "분류 일치율"은 성능이 아니라 파이프라인 무결성 확인이다.
#       실측 성능은 WM-811K 평가 결과를 쓸 것.

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.font_manager import FontProperties, findfont

from wafer_map_visualizer import (
    FAIL_COLOR,
    PASS_COLOR,
    generate_sample_wafer_data,
    plot_wafer_map,
)
from wafer_pattern_classifier import classify_wafer_pattern

A4_LANDSCAPE = (11.69, 8.27)
MAX_COLS = 3
NOISE = 0.03
YIELD_WARN = 90.0

ALL_MODES = ["ring", "center", "donut", "edge_loc", "scratch", "random", "clean"]

# defect_mode → 분류기가 내야 할 클래스. 요약표의 일치 여부 판정용.
EXPECTED = {
    "ring": "EDGE_RING", "center": "CENTER", "donut": "DONUT",
    "edge_loc": "EDGE_LOC", "scratch": "SCRATCH", "random": "RANDOM",
    "clean": "CLEAN",
}

# Windows / macOS / Linux 순으로 한글 폰트를 찾는다.
KOREAN_FONTS = ["Malgun Gothic", "AppleGothic", "NanumGothic",
                "NanumBarunGothic", "Noto Sans CJK KR", "Noto Sans KR",
                "UnDotum", "Gulim"]


def setup_korean_font() -> str | None:
    """한글 폰트를 rcParams에 설정하고 폰트명을 반환. 없으면 None.

    matplotlib 기본 폰트는 DejaVu Sans 로 한글 글리프가 없다.
    설정하지 않으면 PDF의 모든 한글이 빈 사각형으로 나온다.
    """
    for name in KOREAN_FONTS:
        try:
            path = findfont(FontProperties(family=name), fallback_to_default=False)
        except Exception:
            continue
        if path and Path(path).name.lower() not in ("dejavusans.ttf",):
            matplotlib.rcParams["font.family"] = name
            matplotlib.rcParams["axes.unicode_minus"] = False
            return name
    matplotlib.rcParams["axes.unicode_minus"] = False
    return None


@dataclass
class WaferResult:
    lot_id: str
    wafer_id: str
    mode: str
    pattern: str
    score: float
    yield_pct: float
    fail_count: int
    matched: bool


# ──────────────────────────────────────────
# 페이지 구성
# ──────────────────────────────────────────
def _cover_page(pdf: PdfPages, n_lots: int, wafers_per_lot: int,
                report_time: str, font_ok: bool) -> None:
    fig = plt.figure(figsize=A4_LANDSCAPE)
    fig.patch.set_facecolor("#1A237E")
    ax = fig.add_subplot(111)
    ax.set_facecolor("#1A237E")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.5, 0.68, "웨이퍼 맵 자동 분석 리포트", ha="center", va="center",
            fontsize=28, fontweight="bold", color="white")
    ax.text(0.5, 0.55, f"생성일시  {report_time}", ha="center", va="center",
            fontsize=13, color="#90CAF9")
    ax.text(0.5, 0.48,
            f"총 {n_lots} Lot  |  Lot당 {wafers_per_lot}장  |  "
            f"합계 {n_lots * wafers_per_lot}장",
            ha="center", va="center", fontsize=13, color="#90CAF9")
    ax.text(0.5, 0.30,
            "합성 데이터 기반. 생성기와 분류기가 동일한 규칙을 공유하므로\n"
            "요약표의 분류 일치율은 파이프라인 무결성 확인이며 성능 지표가 아니다.",
            ha="center", va="center", fontsize=9, color="#B0BEC5")
    if not font_ok:
        ax.text(0.5, 0.10,
                "WARNING: Korean font not found - text may render as boxes",
                ha="center", va="center", fontsize=9, color="#FFCDD2")

    pdf.savefig(fig)          # bbox_inches 미지정 → A4 고정
    plt.close(fig)


def _summary_page(pdf: PdfPages, results: list[WaferResult]) -> pd.DataFrame:
    """로트별 집계표. 리포트를 넘겨보는 사람이 결론을 얻는 페이지."""
    df = pd.DataFrame([r.__dict__ for r in results])

    rows = []
    for lot, g in df.groupby("lot_id", sort=True):
        patterns = g["pattern"].value_counts()
        rows.append({
            "Lot ID": lot,
            "입력 패턴": g["mode"].iloc[0],
            "웨이퍼": len(g),
            "평균 수율": f"{g['yield_pct'].mean():.1f}%",
            "최저 수율": f"{g['yield_pct'].min():.1f}%",
            "분류 결과 (최다)": f"{patterns.index[0]} ({patterns.iloc[0]}/{len(g)})",
            "일치": f"{g['matched'].mean():.0%}",
            "판정": "확인 필요" if g["yield_pct"].mean() < YIELD_WARN else "정상",
        })
    summary = pd.DataFrame(rows)

    fig = plt.figure(figsize=A4_LANDSCAPE)
    fig.suptitle("요약 — 로트별 집계", fontsize=16, fontweight="bold", y=0.95)
    ax = fig.add_subplot(111)
    ax.axis("off")

    # bbox로 표 위치·높이를 고정한다. loc="upper center" + scale 조합은
    # 행 수에 따라 표가 커지면서 아래 문구와 간격이 제멋대로 벌어진다.
    h = min(0.46, 0.055 * (len(summary) + 1))
    table = ax.table(cellText=summary.values, colLabels=summary.columns,
                     cellLoc="center", bbox=(0.0, 0.92 - h, 1.0, h))
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    # Lot ID가 잘리지 않도록 열 폭을 내용에 맞춘다
    table.auto_set_column_width(col=list(range(len(summary.columns))))

    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#CFD8DC")
        if r == 0:
            cell.set_facecolor("#1565C0")
            cell.set_text_props(color="white", fontweight="bold")
        elif summary.iloc[r - 1]["판정"] == "확인 필요":
            cell.set_facecolor("#FFEBEE")

    total = len(df)
    y_foot = 0.92 - h - 0.10
    ax.text(0.5, y_foot,
            f"전체 {total}장  |  평균 수율 {df['yield_pct'].mean():.1f}%  |  "
            f"수율 {YIELD_WARN:.0f}% 미만 {int((df['yield_pct'] < YIELD_WARN).sum())}장  |  "
            f"분류 일치 {df['matched'].mean():.0%}",
            transform=ax.transAxes, ha="center", fontsize=11, fontweight="bold")
    ax.text(0.5, y_foot - 0.07,
            "일치율은 입력 패턴과 분류 결과의 부합 여부다. 합성 데이터에서는\n"
            "코딩 오류가 없다는 확인까지만 의미하며, 실측 정확도가 아니다.",
            transform=ax.transAxes, ha="center", fontsize=8, color="#666")

    pdf.savefig(fig)
    plt.close(fig)
    return summary


def _lot_page(pdf: PdfPages, lot_id: str, mode: str, wafers_per_lot: int,
              seed_base: int) -> list[WaferResult]:
    n = wafers_per_lot
    cols = min(MAX_COLS, n)
    rows = math.ceil(n / cols)

    # squeeze=False → n=1 에서도 항상 2차원 배열이 온다
    fig, axes = plt.subplots(rows, cols, figsize=A4_LANDSCAPE, squeeze=False)
    flat = axes.ravel()

    out: list[WaferResult] = []
    for i in range(n):
        ax = flat[i]
        # 웨이퍼마다 시드를 바꾼다. 원본은 전 장이 동일했다.
        df = generate_sample_wafer_data(defect_mode=mode, noise=NOISE,
                                        seed=seed_base + i)
        res = classify_wafer_pattern(df)
        wafer_id = f"W{i + 1:02d}"

        plot_wafer_map(df, lot_id=lot_id, wafer_id=wafer_id, ax=ax,
                       show_die_coords=False)

        # 축별 범례는 아래 행 제목과 겹친다 → 제거하고 figure 범례로 대체
        leg = ax.get_legend()
        if leg:
            leg.remove()

        matched = res.pattern == EXPECTED.get(mode)
        # 분류 결과를 제목에 넣는다. 원본은 입력 정답을 그대로 출력했다.
        ax.set_title(
            f"{wafer_id}  수율 {res.yield_pct:.1f}%  FAIL {res.fail_count}\n"
            f"분류: {res.pattern} (score {res.score:.2f})"
            + ("" if matched else "  [불일치]"),
            fontsize=9, fontweight="bold", pad=8,
            color="#C62828" if not matched else "#263238",
        )
        ax.set_xlabel("")
        ax.set_ylabel("")
        ax.set_xticks([])
        ax.set_yticks([])

        out.append(WaferResult(lot_id, wafer_id, mode, res.pattern, res.score,
                               res.yield_pct, res.fail_count, matched))

    for j in range(n, len(flat)):
        flat[j].axis("off")

    avg = sum(r.yield_pct for r in out) / len(out)
    n_mis = sum(not r.matched for r in out)
    fig.suptitle(
        f"Lot {lot_id}   |   입력 패턴 {mode.upper()}   |   "
        f"평균 수율 {avg:.1f}%"
        + (f"   |   분류 불일치 {n_mis}장" if n_mis else ""),
        fontsize=13, fontweight="bold", y=0.97,
        color="#C62828" if (avg < YIELD_WARN or n_mis) else "#1A237E",
    )
    fig.legend(
        handles=[
            plt.Line2D([], [], marker="s", linestyle="", markersize=9,
                       color=PASS_COLOR, label="PASS"),
            plt.Line2D([], [], marker="s", linestyle="", markersize=9,
                       color=FAIL_COLOR, label="FAIL"),
        ],
        loc="lower center", ncol=2, frameon=False, fontsize=10,
        bbox_to_anchor=(0.5, 0.015),
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    pdf.savefig(fig)
    plt.close(fig)
    return out


# ──────────────────────────────────────────
def generate_batch_pdf_report(
    lot_configs: list[dict],
    output_path: str = "batch_wafer_report.pdf",
    wafers_per_lot: int = 5,
    seed: int = 42,
) -> pd.DataFrame:
    """여러 Lot의 웨이퍼 맵과 분류 결과를 PDF로 일괄 생성한다.

    Parameters
    ----------
    lot_configs    : [{"lot_id": str, "defect_mode": str}, ...]
                     defect_mode 생략 시 무작위 선택 (시드 고정)
    output_path    : 저장할 PDF 경로
    wafers_per_lot : Lot당 웨이퍼 수
    seed           : 재현성 시드

    Returns
    -------
    pd.DataFrame : 로트별 요약표
    """
    font = setup_korean_font()
    if font:
        print(f"한글 폰트: {font}")
    else:
        print("경고: 한글 폰트를 찾지 못했다. PDF의 한글이 사각형으로 나온다.")

    rng = random.Random(seed)          # 전역 random 오염 방지 + 재현성
    report_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    with PdfPages(output_path) as pdf:
        _cover_page(pdf, len(lot_configs), wafers_per_lot, report_time,
                    font is not None)

        all_results: list[WaferResult] = []
        for li, cfg in enumerate(lot_configs):
            lot_id = cfg["lot_id"]
            mode = cfg.get("defect_mode") or rng.choice(ALL_MODES)
            res = _lot_page(pdf, lot_id, mode, wafers_per_lot,
                            seed_base=seed + li * 1000)
            all_results.extend(res)

            avg = sum(r.yield_pct for r in res) / len(res)
            n_mis = sum(not r.matched for r in res)
            print(f"  {lot_id:20s} {mode:9s} {len(res)}장 "
                  f"평균 수율 {avg:5.1f}%"
                  + (f"  불일치 {n_mis}장" if n_mis else ""))

        summary = _summary_page(pdf, all_results)

        d = pdf.infodict()
        d["Title"] = "웨이퍼 맵 자동 분석 배치 리포트"
        d["Subject"] = f"{len(lot_configs)} lots / {len(all_results)} wafers"
        d["CreationDate"] = datetime.now()

    print(f"\nPDF 저장: {output_path} "
          f"(페이지 {len(lot_configs) + 2}, 웨이퍼 {len(all_results)}장)")
    return summary


if __name__ == "__main__":
    lots = [
        {"lot_id": "SEMI2026_LOT_001", "defect_mode": "ring"},
        {"lot_id": "SEMI2026_LOT_002", "defect_mode": "center"},
        {"lot_id": "SEMI2026_LOT_003", "defect_mode": "scratch"},
        {"lot_id": "SEMI2026_LOT_004", "defect_mode": "donut"},
        {"lot_id": "SEMI2026_LOT_005", "defect_mode": "clean"},
        {"lot_id": "SEMI2026_LOT_006"},                      # 무작위 배정
    ]
    summary = generate_batch_pdf_report(lots, "batch_wafer_report.pdf",
                                        wafers_per_lot=3)
    print()
    print(summary.to_string(index=False))
