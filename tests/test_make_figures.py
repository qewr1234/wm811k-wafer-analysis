# tests/test_make_figures.py
# make_figures.py (문서용 그림·샘플 PDF 생성) 의 코딩 오류를 합성 데이터로 잡는다.
# 그림 내용의 '정확도'는 검사하지 않는다 - 전부 합성이고 로직 확인이지 성능이 아니다.
#
# 검사 항목
#   - --only patterns pipeline 을 tmp_path 에 생성: 파일 크기 > 0, 500KB 이하, 'missing from font' 경고 0건(동봉 폰트)
#   - pipeline.svg 는 글자를 경로로 저장한다(<text> 없음) - 폰트 없는 뷰어에서도 한글이 깨지지 않는다
#   - --lang en 은 _en 접미사로 저장한다
#   - service_report / readme 도 tmp_path 에만 쓴다. 저장소의 docs/img 는 건드리지 않는다
#   - fit_png_size 가 큰 PNG 를 한도 안으로 줄인다
#   - 알 수 없는 --only 이름은 종료 코드 2 (argparse)
#   - TEXT 사전 ko/en 키 집합이 같고 print 문자열은 cp949 로 인코딩 가능

from __future__ import annotations

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


def _run(tmp_path: Path, names: list[str], lang: str = "ko") -> tuple[list[Path], list[str]]:
    img, smp, work = tmp_path / "img", tmp_path / "samples", tmp_path / "work"
    before = {p.name: p.stat().st_mtime for p in mf.IMG_DIR.glob("*")} if mf.IMG_DIR.is_dir() else {}
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        made = mf.main(["--only", *names, "--lang", lang, "--img-dir", str(img), "--samples-dir", str(smp),
                        "--work-dir", str(work)])
    after = {p.name: p.stat().st_mtime for p in mf.IMG_DIR.glob("*")} if mf.IMG_DIR.is_dir() else {}
    assert before == after, "저장소의 docs/img 를 건드렸다"
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
    png = made[0].read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_lang_en_suffix(tmp_path):
    made, msgs = _run(tmp_path, ["pipeline"], lang="en")
    assert made[0].name == "pipeline_en.svg" and made[0].stat().st_size > 0
    assert not [m for m in msgs if mf.GLYPH_WARNING in m]


def test_service_report_and_readme(tmp_path):
    made, msgs = _run(tmp_path, ["service_report", "readme"])
    assert [p.name for p in made] == ["service_report_page.png", "README.md"]
    assert 0 < made[0].stat().st_size <= mf.MAX_BYTES
    assert not [m for m in msgs if mf.GLYPH_WARNING in m]
    text = made[1].read_text(encoding="utf-8")
    assert "합성" in text and "make_figures.py" in text
    for fname, name, _ in mf.README_ROWS:
        assert fname in text and name in mf.FIGURES


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
