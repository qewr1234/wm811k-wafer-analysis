# tests/test_make_figures.py
# make_figures.py (문서용 그림·샘플 PDF 생성) 의 코딩 오류를 합성 데이터로 잡는다.
# 그림 내용의 '정확도'는 검사하지 않는다 - 전부 합성이고 로직 확인이지 성능이 아니다.
#
# 검사 항목
#   - --only patterns pipeline 을 tmp_path 에 생성: 파일 크기 > 0, 500KB 이하, 'missing from font' 경고 0건(동봉 폰트)
#   - pipeline.svg 는 글자를 경로로 저장한다(<text> 없음) - 폰트 없는 뷰어에서도 한글이 깨지지 않는다.
#     대신 <title>/<desc> 가 <svg> 바로 뒤에 있다(대체 텍스트)
#   - --lang en 은 _en 접미사로 저장한다
#   - service_report / readme 도 tmp_path 에만 쓴다. 저장소의 docs/img 는 건드리지 않는다
#   - 재현성: 같은 그림을 두 번 만들면 바이트까지 같다(생성 시각 고정 - SOURCE_DATE_EPOCH, svg.hashsalt, 시계 고정)
#   - FIGURES 8개 전부 실행(전체 실행 경로): 산출물 이름·크기·PDF 페이지 수(8쪽 / 2쪽)
#   - 커밋된 docs/img/*.png·svg, docs/samples/*.pdf 가 존재하고 크기·페이지 수 규칙을 지키며,
#     docs/img/README.md 가 현재 코드가 만드는 것과 같다(표·설명이 코드와 어긋나지 않는다)
#   - LOC 패널 시드(PANEL_SEED)는 덩어리 1개 + 희박한 배경을 준다
#   - fit_png_size 가 큰 PNG 를 한도 안으로 줄인다
#   - 알 수 없는 --only 이름은 종료 코드 2 (argparse)
#   - TEXT 사전 ko/en 키 집합이 같고 print 문자열은 cp949 로 인코딩 가능

from __future__ import annotations

import re
import sys
import warnings
from pathlib import Path

import matplotlib
import numpy as np
import pytest

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import _fonts  # noqa: E402
import make_figures as mf  # noqa: E402

COMMITTED_IMG = ["wafer_patterns_synthetic.png", "spc_demo.png", "spc_demo_chamber.png", "pipeline.svg",
                 "service_report_page.png", "lot_report_page.png", "README.md"]
COMMITTED_PDF_PAGES = {"batch_wafer_report_sample.pdf": 8, "lot_report_sample.pdf": 2}


def _count_pages(pdf_bytes: bytes) -> int:
    try:
        import pypdf  # type: ignore
        from io import BytesIO
        return len(pypdf.PdfReader(BytesIO(pdf_bytes)).pages)
    except ImportError:
        return len(re.findall(rb"/Type\s*/Page(?![s\w])", pdf_bytes))


def _snapshot(d: Path) -> dict[str, float]:
    return {p.name: p.stat().st_mtime for p in d.glob("*")} if d.is_dir() else {}


def _run(tmp_path: Path, names: list[str], lang: str = "ko", sub: str = "") -> tuple[list[Path], list[str]]:
    base = tmp_path / sub if sub else tmp_path
    img, smp, work = base / "img", base / "samples", base / "work"
    before = _snapshot(mf.IMG_DIR), _snapshot(mf.SAMPLES_DIR)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        made = mf.main(["--only", *names, "--lang", lang, "--img-dir", str(img), "--samples-dir", str(smp),
                        "--work-dir", str(work)])
    assert (_snapshot(mf.IMG_DIR), _snapshot(mf.SAMPLES_DIR)) == before, "저장소의 docs/img, docs/samples 를 건드렸다"
    return made, [str(x.message) for x in w]


def test_patterns_and_pipeline(tmp_path):
    assert _fonts.setup_korean_font() == "NanumGothic"            # 동봉 폰트 전제
    made, msgs = _run(tmp_path, ["patterns", "pipeline"])
    names = [p.name for p in made]
    assert names == ["wafer_patterns_synthetic.png", "pipeline.svg"]
    for p in made:
        assert 0 < p.stat().st_size <= mf.MAX_BYTES, p
    assert not [m for m in msgs if mf.GLYPH_WARNING in m], msgs[:3]

    svg = made[1].read_text(encoding="utf-8")
    assert svg.lstrip().startswith("<?xml") and "<svg" in svg
    assert "<text" not in svg and svg.count("<path") > 50     # 글자가 경로로 저장됨
    # 대체 텍스트: <svg ...> 바로 뒤에 <title> 과 <desc>
    head = svg[svg.index("<svg"):]
    head = head[head.index(">") + 1:].lstrip()
    assert head.startswith("<title>") and "</title>\n <desc>" in head
    assert mf.TEXT["ko"]["pipeline_title"] in head and "8 보고" in head
    assert "<dc:date>2026-01-01T00:00:00+00:00</dc:date>" in svg  # 생성 시각 고정
    png = made[0].read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_lang_en_suffix(tmp_path):
    made, msgs = _run(tmp_path, ["pipeline"], lang="en")
    assert made[0].name == "pipeline_en.svg" and made[0].stat().st_size > 0
    assert not [m for m in msgs if mf.GLYPH_WARNING in m]
    assert "<title>From a wafer map to a report" in made[0].read_text(encoding="utf-8")


def test_service_report_and_readme(tmp_path):
    made, msgs = _run(tmp_path, ["service_report", "readme"])
    assert [p.name for p in made] == ["service_report_page.png", "README.md"]
    assert 0 < made[0].stat().st_size <= mf.MAX_BYTES
    assert not [m for m in msgs if mf.GLYPH_WARNING in m]
    text = made[1].read_text(encoding="utf-8")
    assert "합성" in text and "make_figures.py" in text and "| 대체 텍스트 |" in text
    for fname, name, alt, _ in mf.README_ROWS:
        assert fname in text and alt in text and name in mf.FIGURES
    assert "_en" in text                                          # 영문판 파일 규칙 행
    # readme 는 --lang 과 무관하게 한국어 한 벌(en 으로 돌려도 같은 파일)
    made_en, _ = _run(tmp_path, ["readme"], lang="en", sub="en")
    assert made_en[0].name == "README.md" and made_en[0].read_text(encoding="utf-8") == text


def test_outputs_are_reproducible(tmp_path):
    """같은 코드로 두 번 만들면 바이트까지 같다 - 커밋 diff 에 날짜 메타데이터 잡음이 끼지 않는다.
    (service_report: 생성일시, pipeline: dc:date·clip-path id, sample_pdf/lot_report: CreationDate·각주 시각)"""
    names = ["service_report", "pipeline", "lot_report", "sample_pdf"]
    a, _ = _run(tmp_path, names, sub="a")
    b, _ = _run(tmp_path, names, sub="b")
    assert [p.name for p in a] == [p.name for p in b]
    for pa, pb in zip(a, b):
        assert pa.read_bytes() == pb.read_bytes(), pa.name
    for p in a:
        if p.suffix == ".pdf":
            assert b"D:20260101000000Z" in p.read_bytes(), p.name   # CreationDate 고정
    import os
    assert "SOURCE_DATE_EPOCH" not in os.environ                   # 끝나면 환경을 되돌린다


def test_full_run_all_figures(tmp_path):
    """FIGURES 전부(spc·spc_chamber·lot_report·sample_pdf 포함) 한 번에. 이름·크기·PDF 페이지 수."""
    made, msgs = _run(tmp_path, list(mf.FIGURES))
    names = [p.name for p in made]
    assert names == COMMITTED_IMG[:-1] + list(COMMITTED_PDF_PAGES) + ["README.md"]
    assert not [m for m in msgs if mf.GLYPH_WARNING in m], msgs[:3]
    for p in made:
        assert 0 < p.stat().st_size <= mf.MAX_BYTES, p
        if p.suffix == ".pdf":
            assert _count_pages(p.read_bytes()) == COMMITTED_PDF_PAGES[p.name], p.name
        if p.suffix == ".png":
            from PIL import Image
            w, h = Image.open(p).size
            assert w >= 900 and h >= 800, (p.name, w, h)


def test_committed_figures_match_rules():
    """커밋된 그림·PDF 가 있고 규칙(크기·페이지 수)을 지키며, docs/img/README.md 는 현재 코드가 만드는 것과 같다."""
    for name in COMMITTED_IMG:
        p = mf.IMG_DIR / name
        assert p.is_file(), p
        assert 0 < p.stat().st_size <= mf.MAX_BYTES, p
    for name, pages in COMMITTED_PDF_PAGES.items():
        p = mf.SAMPLES_DIR / name
        assert p.is_file() and 0 < p.stat().st_size <= mf.MAX_BYTES, p
        data = p.read_bytes()
        assert _count_pages(data) == pages, name
        assert b"synthetic data" in data and b"D:20260101000000Z" in data, name
    svg = (mf.IMG_DIR / "pipeline.svg").read_text(encoding="utf-8")
    assert "<title>" in svg and "<desc>" in svg and "<text" not in svg
    # README.md: 생성해서 글자 단위로 비교 (표 행이 코드의 README_ROWS·FIGURES 와 같아야 한다)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        fresh = mf.make_readme(Path(tmp))[0].read_text(encoding="utf-8")
    assert (mf.IMG_DIR / "README.md").read_text(encoding="utf-8") == fresh, \
        "docs/img/README.md 가 코드와 다르다 - python make_figures.py --only readme 로 재생성"


def test_loc_panel_seed_gives_single_blob():
    """PANEL_SEED['loc'] 는 '가장자리에서 떨어진 한 곳의 덩어리' 로 보이는 예시를 고른 것: 크기 3 이상 성분이 1개뿐."""
    sys.path.insert(0, str(ROOT / "tests"))
    from scipy import ndimage
    from synthetic_wm811k import make_wafermap
    s = mf.PANEL_SEED["loc"]
    arr = make_wafermap("loc", s, np.random.default_rng(s))
    lab, _ = ndimage.label(arr == 2)
    sizes = np.bincount(lab.ravel())[1:]
    assert (sizes >= 3).sum() == 1 and sizes.max() >= 8, sizes
    assert (sizes < 3).sum() <= 12                                 # 배경 무작위 불량은 희박


def test_fit_png_size_quantizes(tmp_path):
    from PIL import Image
    rng = np.random.default_rng(0)
    p = tmp_path / "noise.png"
    Image.fromarray(rng.integers(0, 256, (600, 600, 3), dtype=np.uint8)).save(p)    # 무작위 RGB: 압축이 안 됨
    big = p.stat().st_size
    assert big > 300_000
    size = mf.fit_png_size(p, max_bytes=big - 1)
    assert size < big and Image.open(p).mode == "P"
    small = tmp_path / "small.png"
    Image.new("RGB", (10, 10), "white").save(small)
    assert mf.fit_png_size(small) == small.stat().st_size            # 한도 안이면 그대로


def test_unknown_figure_name_rejected(tmp_path):
    with pytest.raises(SystemExit) as e:
        mf.main(["--only", "no_such_figure", "--img-dir", str(tmp_path)])
    assert e.value.code == 2
    with pytest.raises(ValueError):
        mf.build(["no_such_figure"], tmp_path, tmp_path, "ko", tmp_path, say=lambda s: None)


def test_text_dict_symmetric_and_cp949_safe():
    assert set(mf.TEXT["ko"]) == set(mf.TEXT["en"])
    assert len(mf.TEXT["ko"]["steps"]) == len(mf.TEXT["en"]["steps"]) == 8
    assert [m for m, *_ in mf.PATTERNS] == ["ring", "center", "donut", "edge_loc", "scratch", "loc", "random", "near_full"]
    for key in ("font_none",):
        for lang in ("ko", "en"):
            mf.TEXT[lang][key].encode("cp949")                      # 콘솔 출력 문자열은 cp949 안전
    assert mf.add_svg_alt('<?xml?>\n<svg a="1">\n<g/></svg>', "t<", "d&") == \
        '<?xml?>\n<svg a="1">\n <title>t&lt;</title>\n <desc>d&amp;</desc>\n<g/></svg>'
