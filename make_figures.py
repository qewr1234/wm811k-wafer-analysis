# make_figures.py
# README·docs 용 그림과 샘플 PDF 를 전부 합성 데이터로 다시 만든다 (docs/img, docs/samples)
#
# 배경
#   채용 담당자나 면접관은 코드를 실행하지 않는다. 이 저장소가 "맵 한 장 -> 패턴 -> 의심 모듈 ->
#   SPC 추세 -> 보고서" 를 실제로 만든다는 것은 그림과 샘플 PDF 로만 전달된다. 그런데 *.png / *.pdf
#   가 통째로 .gitignore 라 산출물이 저장소에 없었고, 한글 폰트가 없는 환경에서는 그림의 한글이
#   전부 빈 사각형으로 깨졌다. 이 스크립트는 문서용 그림을 한 명령으로, 동봉 폰트(_fonts.py)로,
#   같은 크기·해상도 규칙으로 다시 만든다.
#
# 무엇을 하나 (전부 합성 데이터; 각 파일 500KB 이하, dpi 110~130, 캡션에 '합성' 표시)
#   patterns        docs/img/wafer_patterns_synthetic.png   합성 8종 2x4 격자 (tests/synthetic_wm811k.make_wafermap)
#   spc             docs/img/spc_demo.png                   wm811k_spc.py --demo 관리도
#   spc_chamber     docs/img/spc_demo_chamber.png           --group-col chamber --event-col event 버전
#   pipeline        docs/img/pipeline.svg                   흐름도 (한글은 글리프를 경로로 묻어 폰트 없는 환경에서도 깨지지 않음)
#   service_report  docs/img/service_report_page.png        batch_wafer_report 의 서비스 리포트 1페이지
#   lot_report      docs/img/lot_report_page.png            wm811k_lot_report --demo PDF 의 1페이지
#   sample_pdf      docs/samples/batch_wafer_report_sample.pdf   로트 3개 x 웨이퍼 2장, 서비스 리포트 전부 첨부
#                   docs/samples/lot_report_sample.pdf           합성 로트 1개의 로트 트러블슈팅 리포트
#   readme          docs/img/README.md                      그림별 생성 명령과 '합성 데이터' 명시
#
# 왜
#   - 그림을 손으로 만들면 코드가 바뀌어도 그림이 안 바뀐다. 스크립트로 묶어 두면 관리도 규칙이나
#     보고서 양식이 바뀔 때 한 번에 다시 만들고, 그림과 코드가 어긋나는 일이 없다.
#   - PNG 는 dpi 를 고정하고 500KB 를 넘으면 256색 팔레트로 줄인다(선·글자 위주 그림이라 손실이 없다).
#   - SVG 는 svg.fonttype='path' 로 글자를 경로로 저장한다. GitHub 뷰어나 폰트 없는 PC 에서도
#     한글이 그대로 보인다(대신 파일이 커진다).
#
# 한계
#   전부 합성 데이터다. 그림 속 일치율·탐지 시점·판정은 로직 확인이지 성능이 아니다. 실측 수치는
#   README 의 WM-811K 결과(macro-F1 0.907 +- 0.008)뿐이고, 이 스크립트는 그 수치를 만들지 않는다.
#   lot_report 페이지의 PNG 변환은 pypdfium2 -> pdftoppm -> (둘 다 없으면) PdfPages 를 가로채
#   첫 페이지 figure 를 저장하는 순서로 시도한다. 한글 폰트가 없으면 영문(en)으로 자동 전환한다.
#
# 사용법
#   python make_figures.py                                  # 전부 (ko)
#   python make_figures.py --only patterns pipeline         # 일부만
#   python make_figures.py --lang en                        # 영문판 (파일명에 _en 접미사)
#   python make_figures.py --img-dir out/img --samples-dir out/samples   # 출력 폴더 변경 (테스트용)

from __future__ import annotations

import argparse
import contextlib
import io
import shutil
import subprocess
import sys
import tempfile
import warnings
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyBboxPatch, Polygon

from _fonts import setup_korean_font
from wafer_map_visualizer import FAIL_COLOR, PASS_COLOR

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
IMG_DIR = HERE / "docs" / "img"
SAMPLES_DIR = HERE / "docs" / "samples"
DPI = 120
MAX_BYTES = 500_000
GLYPH_WARNING = "missing from font"

# 색은 wafer_map_visualizer / wm811k_spc 와 맞춘다.
INK, MUTED, LINE, BG = "#455A64", "#78909C", "#B0BEC5", "#ECEFF1"
BOX_FILL = {"data": "#E3F2FD", "model": "#E8F5E9", "field": "#FFF8E1", "report": "#F3E5F5"}
BOX_EDGE = {"data": "#1565C0", "model": "#2E7D32", "field": "#EF6C00", "report": "#6A1B9A"}

# 합성 8종: (make_wafermap 모드, 클래스명, 한글 이름, 영문 이름)
PATTERNS = [
    ("ring", "EDGE_RING", "엣지 링", "edge ring"),
    ("center", "CENTER", "센터", "center"),
    ("donut", "DONUT", "도넛", "donut"),
    ("edge_loc", "EDGE_LOC", "엣지 국소", "edge-local"),
    ("scratch", "SCRATCH", "스크래치", "scratch"),
    ("loc", "LOC", "국소", "local"),
    ("random", "RANDOM", "무작위", "random"),
    ("near_full", "NEAR_FULL", "전면 불량", "near-full"),
]

TEXT = {
    "ko": {
        "patterns_title": "합성 웨이퍼 맵 8종 (tests/synthetic_wm811k.make_wafermap, 로직 확인용 - 성능 근거 아님)",
        "patterns_foot": "초록 PASS / 빨강 FAIL / 회색 다이 없음.  아래 삼각형 = 노치 (가정 notch_deg=-90).  "
                         "맵 크기·다이 크기·노이즈는 WM-811K 처럼 장마다 다르게 뽑았다.  불량률은 합성값이다.",
        "patterns_sub": "{cls} / {name}\n{h}x{w} 격자, 불량 {ff:.1%}",
        "pipeline_title": "웨이퍼 맵에서 보고서까지 - 이 저장소의 흐름",
        "pipeline_foot": "번호 순서가 현장 순서(docs/defect_signatures.md)다. 실측으로 검증된 수치는 2번의 macro-F1 뿐이고, "
                         "3~8번은 합성 데이터로 로직만 확인했다(docs/roadmap.md). 그림: make_figures.py",
        "pipeline_loop": "조치 후 관리도 복귀 확인",
        "steps": [
            ("웨이퍼 맵", "WM-811K 2D 배열 0/1/2\n또는 다이 격자 CSV", "wafer_map_visualizer.py", "data"),
            ("분류", "해석 가능한 특징 20개 + RF\nmacro-F1 0.907 +- 0.008 (실측)", "wm811k_validate.py", "model"),
            ("패턴 8종", "EDGE_RING, CENTER, DONUT, EDGE_LOC,\nSCRATCH, LOC, RANDOM, NEAR_FULL", "wafer_pattern_classifier.py", "model"),
            ("로트 안 판정", "방위각 / 스크래치 모양 /\n슬롯 / 장비 공통성", "wm811k_azimuth · scratch_shape · slot · commonality", "field"),
            ("장비 측 증거 대조", "로봇 로그, 누적 RF 시간,\nPM 이력, 챔버·슬롯 비교", "ACTION_DETAIL (tool_evidence)", "field"),
            ("TEL 원인 / 타사 인계", "TEL 모듈 1차 점검, 아니면\nCMP·노광·검사 장비로 인계", "docs/tel_equipment_map.md", "field"),
            ("SPC 추세 · 이벤트", "p 관리도(Laney) + EWMA + WE 규칙\n부품 교체·PM 이벤트 대조", "wm811k_spc.py", "model"),
            ("보고", "서비스 리포트 · 로트 리포트 ·\n8D 케이스 스터디", "batch_wafer_report · wm811k_lot_report", "report"),
        ],
        "legend": [("data", "입력"), ("model", "분석"), ("field", "현장 판정"), ("report", "산출물")],
        "img_readme_title": "# docs/img - 문서용 그림 (전부 합성 데이터)",
        "font_none": "[경고] 한글 폰트를 찾지 못해 영문(en)으로 전환한다.",
    },
    "en": {
        "patterns_title": "Eight synthetic wafer-map patterns (tests/synthetic_wm811k.make_wafermap; logic check, not performance)",
        "patterns_foot": "green PASS / red FAIL / grey no die.  Triangle at the bottom = notch (assumed notch_deg=-90).  "
                         "Map size, die size and noise vary per wafer as in WM-811K.  Fail fractions are synthetic.",
        "patterns_sub": "{cls} / {name}\n{h}x{w} grid, fail {ff:.1%}",
        "pipeline_title": "From a wafer map to a report - how this repository is laid out",
        "pipeline_foot": "Numbers follow the field procedure (docs/defect_signatures.md). Only step 2's macro-F1 is measured on real data; "
                         "steps 3-8 are logic-checked on synthetic data only (docs/roadmap.md). Figure: make_figures.py",
        "pipeline_loop": "confirm chart returns to baseline after the action",
        "steps": [
            ("Wafer map", "WM-811K 2D array 0/1/2\nor a die-grid CSV", "wafer_map_visualizer.py", "data"),
            ("Classify", "20 interpretable features + RF\nmacro-F1 0.907 +- 0.008 (measured)", "wm811k_validate.py", "model"),
            ("8 patterns", "EDGE_RING, CENTER, DONUT, EDGE_LOC,\nSCRATCH, LOC, RANDOM, NEAR_FULL", "wafer_pattern_classifier.py", "model"),
            ("Within-lot checks", "azimuth / scratch shape /\nslot / tool commonality", "wm811k_azimuth · scratch_shape · slot · commonality", "field"),
            ("Tool-side evidence", "robot logs, cumulative RF hours,\nPM history, chamber / slot comparison", "ACTION_DETAIL (tool_evidence)", "field"),
            ("TEL cause / hand-off", "check TEL modules first, else\nhand off to CMP / litho / inspection", "docs/tel_equipment_map.md", "field"),
            ("SPC trend · events", "p chart (Laney) + EWMA + WE rules\nparts replacement / PM events", "wm811k_spc.py", "model"),
            ("Report", "service report · lot report ·\n8D case study", "batch_wafer_report · wm811k_lot_report", "report"),
        ],
        "legend": [("data", "input"), ("model", "analysis"), ("field", "field judgement"), ("report", "deliverable")],
        "img_readme_title": "# docs/img - figures for the docs (all synthetic data)",
        "font_none": "[warning] Korean font not found - switching to en.",
    },
}


# ──────────────────────────────────────────
# 공통
# ──────────────────────────────────────────
def _suffix(lang: str) -> str:
    return "" if lang == "ko" else f"_{lang}"


def fit_png_size(path: Path, max_bytes: int = MAX_BYTES) -> int:
    """PNG 가 max_bytes 를 넘으면 256색 팔레트로 다시 저장한다. 최종 크기(바이트)를 돌려준다.

    관리도·흐름도처럼 선과 글자 위주 그림은 팔레트 변환으로 보통 1/2~1/3 이 되고 눈에 띄는 손실이 없다.
    그래도 넘으면 RuntimeError (dpi 나 figure 크기를 줄여야 한다).
    """
    size = path.stat().st_size
    if size <= max_bytes:
        return size
    from PIL import Image  # matplotlib 의존성이라 항상 있다
    im = Image.open(path).convert("RGB")
    im.quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(path, optimize=True)
    size = path.stat().st_size
    if size > max_bytes:
        raise RuntimeError(f"{path.name}: {size:,} bytes > {max_bytes:,} even after quantization")
    return size


def _save_png(fig: plt.Figure, path: Path, dpi: int = DPI) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)
    fit_png_size(path)
    return path


# ──────────────────────────────────────────
# 1. 합성 8종 격자
# ──────────────────────────────────────────
def _draw_map(ax: plt.Axes, arr: np.ndarray) -> None:
    """0/1/2 배열을 색 이미지로. 원 외곽선과 아래쪽 노치 삼각형을 얹는다(가정 notch_deg=-90)."""
    h, w = arr.shape
    rgb = np.empty((h, w, 3))
    pal = {0: matplotlib.colors.to_rgb(BG), 1: matplotlib.colors.to_rgb(PASS_COLOR), 2: matplotlib.colors.to_rgb(FAIL_COLOR)}
    for v, c in pal.items():
        rgb[arr == v] = c
    ax.imshow(rgb, interpolation="nearest", origin="upper")
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    R = max(w, h) / 2.0
    ax.add_patch(Circle((cx, cy), R, fill=False, edgecolor=INK, linewidth=1.2))
    nw, nh = R * 0.06, R * 0.10
    ax.add_patch(Polygon([[cx - nw, cy + R], [cx + nw, cy + R], [cx, cy + R + nh]], closed=True,
                         facecolor=INK, edgecolor=INK))
    ax.set_xlim(cx - R * 1.08, cx + R * 1.08)
    ax.set_ylim(cy + R * 1.18, cy - R * 1.08)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)


def make_patterns(img_dir: Path, lang: str, dpi: int = DPI, seed: int = 2026) -> list[Path]:
    sys.path.insert(0, str(HERE / "tests"))
    from synthetic_wm811k import make_wafermap  # noqa: E402
    T = TEXT[lang]
    rng = np.random.default_rng(seed)
    fig, axes = plt.subplots(2, 4, figsize=(12.0, 7.0), layout="constrained")
    for i, (ax, (mode, cls, ko, en)) in enumerate(zip(axes.ravel(), PATTERNS)):
        arr = make_wafermap(mode, seed + i, rng)
        die = arr > 0
        ff = float((arr == 2).sum() / max(die.sum(), 1))
        _draw_map(ax, arr)
        ax.set_title(T["patterns_sub"].format(cls=cls, name=ko if lang == "ko" else en, h=arr.shape[0], w=arr.shape[1], ff=ff),
                     fontsize=9.5, color=INK)
    fig.suptitle(T["patterns_title"], fontsize=11, color=INK)
    fig.text(0.5, 0.005, T["patterns_foot"], ha="center", va="bottom", fontsize=7.5, color=MUTED)
    return [_save_png(fig, img_dir / f"wafer_patterns_synthetic{_suffix(lang)}.png", dpi)]


# ──────────────────────────────────────────
# 2·3. SPC 데모 관리도
# ──────────────────────────────────────────
def _run_spc_demo(work: Path, lang: str, extra: list[str]) -> Path:
    """wm811k_spc.main 을 같은 프로세스에서 호출한다(콘솔 출력은 삼킨다). 생성된 png 경로를 돌려준다."""
    import wm811k_spc as spc
    out = work / ("spc_" + "_".join(a.strip("-") for a in extra) if extra else "spc")
    with contextlib.redirect_stdout(io.StringIO()):
        spc.main(["--demo", "--lang", lang, "--output", str(out)] + extra)
    png = out / "spc_demo.png"
    if not png.is_file():
        raise RuntimeError(f"wm811k_spc --demo did not produce {png}")
    return png


def make_spc(img_dir: Path, lang: str, work: Path, dpi: int = DPI) -> list[Path]:
    png = _run_spc_demo(work, lang, [])
    dst = img_dir / f"spc_demo{_suffix(lang)}.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(png, dst)
    fit_png_size(dst)
    return [dst]


def make_spc_chamber(img_dir: Path, lang: str, work: Path, dpi: int = DPI) -> list[Path]:
    png = _run_spc_demo(work, lang, ["--group-col", "chamber", "--event-col", "event"])
    dst = img_dir / f"spc_demo_chamber{_suffix(lang)}.png"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(png, dst)
    fit_png_size(dst)
    return [dst]


# ──────────────────────────────────────────
# 4. 흐름도 (SVG, 글자는 경로로)
# ──────────────────────────────────────────
def pipeline_figure(lang: str) -> plt.Figure:
    """흐름도 figure. make_pipeline 이 SVG 로 저장하고, 테스트·검토용으로 PNG 저장에도 쓸 수 있다."""
    T = TEXT[lang]
    steps = T["steps"]
    W, H = 15.0, 6.6
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    cols, bw, bh = 4, 3.15, 1.6
    gap = (W - 0.5 - cols * bw) / (cols - 1)
    rows_y = [H - 0.9 - bh, H - 0.9 - bh - 1.2 - bh]           # 두 줄 (각 4단계)
    centers: list[tuple[float, float]] = []
    for i, (title, body, src, kind) in enumerate(steps):
        r, c = divmod(i, cols)
        x = 0.25 + c * (bw + gap)
        y = rows_y[r]
        ax.add_patch(FancyBboxPatch((x, y), bw, bh, boxstyle="round,pad=0.02,rounding_size=0.12",
                                    facecolor=BOX_FILL[kind], edgecolor=BOX_EDGE[kind], linewidth=1.4))
        ax.add_patch(Circle((x + 0.24, y + bh - 0.24), 0.16, facecolor=BOX_EDGE[kind], edgecolor="none"))
        ax.text(x + 0.24, y + bh - 0.24, str(i + 1), ha="center", va="center", fontsize=8.5, color="white",
                fontweight="bold")
        ax.text(x + 0.5, y + bh - 0.24, title, ha="left", va="center", fontsize=11.5, color=INK, fontweight="bold")
        ax.text(x + bw / 2, y + bh - 0.60, body, ha="center", va="top", fontsize=8.6, color=INK, linespacing=1.35)
        ax.text(x + bw / 2, y + 0.13, src, ha="center", va="center", fontsize=7.2, color=MUTED, style="italic")
        centers.append((x + bw / 2, y + bh / 2))

    arrow = dict(arrowstyle="-|>", color=INK, lw=1.3, mutation_scale=14, shrinkA=0, shrinkB=0)
    for i in range(len(steps) - 1):
        (x0, y0), (x1, y1) = centers[i], centers[i + 1]
        if (i + 1) % cols:                                      # 같은 줄: 오른쪽으로
            ax.annotate("", xy=(x1 - bw / 2, y1), xytext=(x0 + bw / 2, y0), arrowprops=arrow)
        else:                                                   # 줄 바꿈: 아래로 내려가 왼쪽 끝으로
            ymid = (rows_y[0] + rows_y[1] + bh) / 2
            ax.plot([x0, x0, x1, x1], [y0 - bh / 2, ymid, ymid, y1 + bh / 2 + 0.03], color=INK, lw=1.3,
                    solid_capstyle="round")
            ax.annotate("", xy=(x1, y1 + bh / 2), xytext=(x1, y1 + bh / 2 + 0.3), arrowprops=arrow)
    # 보고 -> SPC 피드백(조치 후 복귀 확인): 8번 아래에서 7번 아래로 점선
    (x7, y7), (x8, y8) = centers[6], centers[7]
    yb = rows_y[1] - 0.45
    ax.plot([x8, x8, x7], [y8 - bh / 2, yb, yb], color=MUTED, lw=1.1, ls=(0, (4, 3)))
    ax.annotate("", xy=(x7, y7 - bh / 2), xytext=(x7, yb), arrowprops=dict(arrowstyle="-|>", color=MUTED, lw=1.1,
                                                                           mutation_scale=12, ls=(0, (4, 3))))
    ax.text((x7 + x8) / 2, yb - 0.07, T["pipeline_loop"], ha="center", va="top", fontsize=7.6, color=MUTED)

    ax.text(0.25, H - 0.35, T["pipeline_title"], ha="left", va="center", fontsize=14, color=INK, fontweight="bold")
    lx = W - 0.25
    for kind, label in reversed(T["legend"]):
        tw = 0.22 + 0.11 * len(label)
        ax.add_patch(FancyBboxPatch((lx - tw, H - 0.47), 0.26, 0.24, boxstyle="round,pad=0.01,rounding_size=0.05",
                                    facecolor=BOX_FILL[kind], edgecolor=BOX_EDGE[kind], linewidth=1.0))
        ax.text(lx - tw + 0.34, H - 0.35, label, ha="left", va="center", fontsize=8.5, color=INK)
        lx -= tw + 0.35
    ax.text(0.25, 0.18, T["pipeline_foot"], ha="left", va="center", fontsize=7.8, color=MUTED)
    return fig


def make_pipeline(img_dir: Path, lang: str, dpi: int = DPI) -> list[Path]:
    fig = pipeline_figure(lang)
    out = img_dir / f"pipeline{_suffix(lang)}.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context({"svg.fonttype": "path"}):     # 글자를 경로로: 뷰어에 폰트가 없어도 그대로
        fig.savefig(out, format="svg", facecolor="white")
    plt.close(fig)
    return [out]


# ──────────────────────────────────────────
# 5. 서비스 리포트 1페이지
# ──────────────────────────────────────────
def _synthetic_lot(lot_id: str, mode: str, n: int, seed: int):
    """batch_wafer_report._lot_page 와 같은 방식으로 합성 로트 하나를 분류해 LotSummary 로 만든다(그림은 안 그림)."""
    import batch_wafer_report as bwr
    from wafer_map_visualizer import generate_sample_wafer_data
    from wafer_pattern_classifier import classify_wafer_pattern, expected_patterns
    results = []
    for i in range(n):
        df = generate_sample_wafer_data(defect_mode=mode, noise=bwr.NOISE, seed=seed + i)
        res = classify_wafer_pattern(df)
        results.append(bwr.WaferResult(lot_id, f"W{i + 1:02d}", mode, res.pattern, res.score, res.yield_pct,
                                       res.fail_count, res.pattern in expected_patterns(mode, bwr.NOISE)))
    return bwr.summarize_lots(results)[0]


def make_service_report(img_dir: Path, lang: str, dpi: int = DPI) -> list[Path]:
    import batch_wafer_report as bwr
    lang = bwr.resolve_lang(lang, quiet=True)
    lot = _synthetic_lot("SYN_LOT_RING_001", "ring", 3, seed=42)
    fig = bwr.build_service_report_page(lot, lang=lang, report_time=datetime.now().strftime("%Y-%m-%d"))
    return [_save_png(fig, img_dir / f"service_report_page{_suffix(lang)}.png", dpi)]


# ──────────────────────────────────────────
# 6. 로트 리포트 1페이지 (PDF -> PNG)
# ──────────────────────────────────────────
def _pdf_page_to_png(pdf: Path, png: Path, dpi: int) -> str:
    """PDF 1페이지를 PNG 로. pypdfium2 -> pdftoppm 순서. 둘 다 없으면 ImportError."""
    try:
        import pypdfium2 as pdfium  # type: ignore
        doc = pdfium.PdfDocument(str(pdf))
        doc[0].render(scale=dpi / 72).to_pil().save(png)
        return "pypdfium2"
    except ImportError:
        pass
    exe = shutil.which("pdftoppm")
    if exe:
        stem = png.with_suffix("")
        subprocess.run([exe, "-png", "-r", str(dpi), "-f", "1", "-l", "1", "-singlefile", str(pdf), str(stem)], check=True)
        return "pdftoppm"
    raise ImportError("pypdfium2 / pdftoppm 둘 다 없다")


def _lot_demo(lang: str, out_pdf: Path, capture_png: Path | None = None, dpi: int = DPI):
    """wm811k_lot_report 의 데모 로트(demo_edge_loc_fixed)를 분석해 PDF 로 저장한다.

    capture_png 가 있으면 PdfPages 를 가로채 첫 페이지 figure 를 PNG 로도 저장한다(래스터라이저가 없을 때의 대안).
    """
    import wm811k_lot_report as lr
    records, preds, hist = lr.demo_records()
    f = lr.analyze_lot(records, preds, lr.DEMO_LOTS[0], history=hist, synthetic=True)
    if capture_png is None:
        lr.render_lot_pdf(f, records, out_pdf, lang=lang, quiet=True)
        return f
    real = lr.PdfPages

    class _Capture(real):                                    # 첫 savefig 의 figure 를 PNG 로도 저장
        _done = False

        def savefig(self, figure=None, **kw):
            if not _Capture._done:
                _Capture._done = True
                figure.savefig(capture_png, dpi=dpi, facecolor="white")
            return super().savefig(figure, **kw)

    lr.PdfPages = _Capture
    try:
        lr.render_lot_pdf(f, records, out_pdf, lang=lang, quiet=True)
    finally:
        lr.PdfPages = real
    return f


def make_lot_report(img_dir: Path, lang: str, work: Path, dpi: int = DPI) -> list[Path]:
    import wm811k_lot_report as lr
    lang = lr.resolve_lang(lang, quiet=True)
    pdf = work / "lot_report_demo.pdf"
    png = img_dir / f"lot_report_page{_suffix(lang)}.png"
    png.parent.mkdir(parents=True, exist_ok=True)
    _lot_demo(lang, pdf)
    try:
        _pdf_page_to_png(pdf, png, dpi)
    except ImportError:
        _lot_demo(lang, pdf, capture_png=png, dpi=dpi)
    fit_png_size(png)
    return [png]


# ──────────────────────────────────────────
# 7. 샘플 PDF
# ──────────────────────────────────────────
SAMPLE_LOTS = [
    {"lot_id": "SYN_LOT_RING_001", "defect_mode": "ring"},
    {"lot_id": "SYN_LOT_SCRATCH_002", "defect_mode": "scratch"},
    {"lot_id": "SYN_LOT_CLEAN_003", "defect_mode": "clean"},
]


def make_sample_pdf(samples_dir: Path, lang: str, work: Path, dpi: int = DPI) -> list[Path]:
    import batch_wafer_report as bwr
    samples_dir.mkdir(parents=True, exist_ok=True)
    out1 = samples_dir / f"batch_wafer_report_sample{_suffix(lang)}.pdf"
    bwr.generate_batch_pdf_report(SAMPLE_LOTS, out1, wafers_per_lot=2, seed=42, lang=lang,
                                  service_report="all", quiet=True)
    out2 = samples_dir / f"lot_report_sample{_suffix(lang)}.pdf"
    import wm811k_lot_report as lr
    _lot_demo(lr.resolve_lang(lang, quiet=True), out2)
    for p in (out1, out2):
        if p.stat().st_size > MAX_BYTES:
            raise RuntimeError(f"{p.name}: {p.stat().st_size:,} bytes > {MAX_BYTES:,}")
    return [out1, out2]


# ──────────────────────────────────────────
# 8. docs/img/README.md
# ──────────────────────────────────────────
README_ROWS = [
    ("wafer_patterns_synthetic.png", "patterns", "합성 웨이퍼 맵 8종 2x4 격자 (`tests/synthetic_wm811k.make_wafermap`). 노치는 아래(가정 notch_deg=-90)."),
    ("spc_demo.png", "spc", "`python wm811k_spc.py --demo` 의 관리도. 웨이퍼 3000부터 EDGE_RING 드리프트, 3750부터 저신뢰 증가, 4125부터 SCRATCH 계단을 심은 합성 시퀀스."),
    ("spc_demo_chamber.png", "spc_chamber", "같은 데모를 `--group-col chamber --event-col event` 로 층화한 것. 심은 이상은 B 챔버에만 있고 이벤트(pm_wet_clean, focus_ring_replaced)가 세로 점선."),
    ("pipeline.svg", "pipeline", "흐름도. 글자를 경로로 저장해 폰트 없는 환경에서도 한글이 보인다."),
    ("service_report_page.png", "service_report", "`batch_wafer_report.build_service_report_page` 의 서비스 리포트 양식 1페이지 (합성 링 로트 3장). Tool/Chamber 는 빈 양식."),
    ("lot_report_page.png", "lot_report", "`python wm811k_lot_report.py --demo` 가 만드는 PDF(demo_edge_loc_fixed)의 1페이지."),
]


def make_readme(img_dir: Path, lang: str) -> list[Path]:
    T = TEXT[lang]
    lines = [T["img_readme_title"], "",
             "이 폴더의 그림은 **전부 합성 데이터**로 `python make_figures.py` 가 만든다. "
             "그림 속 일치율·탐지 시점·판정은 로직 확인이지 성능이 아니다. 실측 수치는 README 의 WM-811K 결과뿐이다. "
             "실제 장비·고객 데이터는 없고, Tool/Chamber 같은 식별자는 빈 양식이다.", "",
             "| 파일 | 생성 (`python make_figures.py --only <name>`) | 내용 |", "|---|---|---|"]
    for fname, name, desc in README_ROWS:
        lines.append(f"| `{fname}` | `{name}` | {desc} |")
    lines += ["",
              "샘플 PDF 는 `docs/samples/` 에 있다 (`--only sample_pdf`): `batch_wafer_report_sample.pdf` (합성 로트 3개 x 웨이퍼 2장, "
              "서비스 리포트 전부 첨부), `lot_report_sample.pdf` (합성 로트 1개의 로트 트러블슈팅 리포트).", "",
              "규칙: PNG 는 dpi 120~130, 파일당 500KB 이하(넘으면 256색 팔레트로 축소). `--lang en` 은 `_en` 접미사로 영문판을 만든다. "
              "한글은 동봉 폰트(`docs/fonts/NanumGothic-Regular.ttf`, `_fonts.py`)로 그린다.", ""]
    out = img_dir / "README.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    return [out]


# ──────────────────────────────────────────
FIGURES: dict[str, str] = {           # 이름 -> 설명 (순서가 실행 순서)
    "patterns": "docs/img/wafer_patterns_synthetic.png",
    "spc": "docs/img/spc_demo.png",
    "spc_chamber": "docs/img/spc_demo_chamber.png",
    "pipeline": "docs/img/pipeline.svg",
    "service_report": "docs/img/service_report_page.png",
    "lot_report": "docs/img/lot_report_page.png",
    "sample_pdf": "docs/samples/*.pdf",
    "readme": "docs/img/README.md",
}


def build(names: list[str], img_dir: Path, samples_dir: Path, lang: str, work: Path, dpi: int = DPI,
          say: Callable[[str], None] = print) -> list[Path]:
    """지정한 그림을 만들고 생성 경로를 돌려준다. 폰트가 없으면 en 으로 전환한다."""
    if setup_korean_font() is None and lang == "ko":
        say(TEXT["ko"]["font_none"])
        lang = "en"
    made: list[Path] = []
    for name in names:
        if name == "patterns":
            out = make_patterns(img_dir, lang, dpi)
        elif name == "spc":
            out = make_spc(img_dir, lang, work, dpi)
        elif name == "spc_chamber":
            out = make_spc_chamber(img_dir, lang, work, dpi)
        elif name == "pipeline":
            out = make_pipeline(img_dir, lang, dpi)
        elif name == "service_report":
            out = make_service_report(img_dir, lang, dpi)
        elif name == "lot_report":
            out = make_lot_report(img_dir, lang, work, dpi)
        elif name == "sample_pdf":
            out = make_sample_pdf(samples_dir, lang, work, dpi)
        elif name == "readme":
            out = make_readme(img_dir, lang)
        else:
            raise ValueError(f"unknown figure {name!r}; choose from {list(FIGURES)}")
        for p in out:
            say(f"  {name:15s} {p.relative_to(HERE) if p.is_relative_to(HERE) else p}  ({p.stat().st_size / 1024:.0f} KB)")
        made.extend(out)
    return made


def main(argv: list[str] | None = None) -> list[Path]:
    ap = argparse.ArgumentParser(description="문서용 그림·샘플 PDF 생성 (전부 합성 데이터)")
    ap.add_argument("--only", nargs="+", choices=list(FIGURES), default=None, help="일부 그림만")
    ap.add_argument("--lang", choices=["ko", "en"], default="ko", help="그림 언어. en 은 파일명에 _en 접미사")
    ap.add_argument("--img-dir", type=Path, default=IMG_DIR)
    ap.add_argument("--samples-dir", type=Path, default=SAMPLES_DIR)
    ap.add_argument("--dpi", type=int, default=DPI, help="PNG dpi (기본 120; wm811k_spc 그림은 자체 130)")
    ap.add_argument("--work-dir", type=Path, default=None, help="중간 산출물 폴더 (기본: 임시 폴더, 끝나면 삭제)")
    args = ap.parse_args(argv)
    matplotlib.use("Agg")
    names = args.only or list(FIGURES)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        if args.work_dir is not None:
            args.work_dir.mkdir(parents=True, exist_ok=True)
            made = build(names, args.img_dir, args.samples_dir, args.lang, args.work_dir, args.dpi)
        else:
            with tempfile.TemporaryDirectory(prefix="make_figures_") as tmp:
                made = build(names, args.img_dir, args.samples_dir, args.lang, Path(tmp), args.dpi)
    n_glyph = sum(GLYPH_WARNING in str(w.message) for w in caught)
    print(f"{len(made)} files, Glyph-missing warnings: {n_glyph} (synthetic data only; logic check, not performance)")
    if n_glyph:
        print("[경고] 글자가 빈 사각형으로 그려졌을 수 있다. docs/fonts/ 의 동봉 폰트를 확인하라.", file=sys.stderr)
    return made


if __name__ == "__main__":
    main()
