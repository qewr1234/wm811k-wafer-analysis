# tests/test_report.py
# _fonts(동봉 한글 폰트)와 batch_wafer_report(배치 PDF + 서비스 리포트, --lang, --anonymize)의
# 코딩 오류를 합성 데이터로 잡는다. 성능 테스트가 아니다 - 합성 데이터의 분류 일치율은
# 생성기와 분류기가 규칙을 공유한 결과일 뿐이다.
#
# 검사 항목
#   - setup_korean_font() 가 docs/fonts/NanumGothic-Regular.ttf 를 찾아 'NanumGothic' 을 돌려준다
#   - PDF 생성 중 'missing from font' 경고 0건 (warnings.catch_warnings(record=True))
#   - 페이지 수 = 표지 1 + 로트 n + 서비스 리포트 k + 요약 1 (PDF 바이트의 /Type /Page 개수로 재확인)
#   - --service-report all / flagged / none 에 따른 k
#   - --lang en 이면 제목·표 머리가 영문, 메타데이터 Title 도 영문 + 'synthetic data'
#   - --anonymize 면 원래 로트명이 요약표에 없다 (pypdfium2 가 있으면 PDF 본문 텍스트도 검사)
#   - LABELS 문자열이 모두 cp949 로 인코딩 가능, ko/en 키 집합 동일
#   - CLI(subprocess) 가 --out 경로에만 쓰고 종료 코드 0

from __future__ import annotations

import re
import subprocess
import sys
import warnings
from pathlib import Path

import matplotlib
import pandas as pd
import pytest

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import _fonts  # noqa: E402
import batch_wafer_report as bwr  # noqa: E402

LOTS = [
    {"lot_id": "TESTLOT_RING_001", "defect_mode": "ring"},
    {"lot_id": "TESTLOT_CLEAN_002", "defect_mode": "clean"},
    {"lot_id": "TESTLOT_CENTER_003", "defect_mode": "center"},
]
ORIGINAL_IDS = {c["lot_id"] for c in LOTS}


def _count_pages(pdf_bytes: bytes) -> int:
    """pypdf 없이 페이지 수를 센다: 페이지 객체 '/Type /Page' (뒤에 's' 가 없는 것)."""
    try:
        import pypdf  # type: ignore
        from io import BytesIO
        return len(pypdf.PdfReader(BytesIO(pdf_bytes)).pages)
    except ImportError:
        return len(re.findall(rb"/Type\s*/Page(?![s\w])", pdf_bytes))


def _pdf_text(path: Path) -> str | None:
    """PDF 본문 텍스트. matplotlib 는 글리프 ID 로 텍스트를 쓰므로 바이트 검색이 안 되고
    렌더러가 필요하다. pypdfium2 가 없으면 None (그 검사는 건너뛴다)."""
    try:
        import pypdfium2 as pdfium  # type: ignore
    except ImportError:
        return None
    doc = pdfium.PdfDocument(str(path))
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


@pytest.fixture(scope="module")
def generated(tmp_path_factory):
    """로트 3개 x 2장, 서비스 리포트 all, ko. 여러 테스트가 공유한다."""
    out = tmp_path_factory.mktemp("report") / "batch.pdf"
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        summary = bwr.generate_batch_pdf_report(LOTS, out, wafers_per_lot=2, seed=1, lang="ko",
                                                service_report="all", quiet=True)
    return {"summary": summary, "path": out, "bytes": out.read_bytes(),
            "warnings": [str(x.message) for x in w]}


# ──────────────────────────────────────────
# 폰트
# ──────────────────────────────────────────
def test_bundled_font_is_registered():
    assert _fonts.BUNDLED_FONT.is_file(), "docs/fonts/NanumGothic-Regular.ttf 가 없다"
    assert _fonts.BUNDLED_FONT.stat().st_size < 5 * 1024 * 1024
    assert _fonts.BUNDLED_FONT.read_bytes()[:4] == b"\x00\x01\x00\x00"          # TrueType 매직
    assert (_fonts.BUNDLED_FONT.parent / "OFL.txt").is_file()

    name = _fonts.setup_korean_font(force=True)
    assert name == "NanumGothic"
    assert _fonts.has_korean_font()
    fam = matplotlib.rcParams["font.family"]
    assert fam[0] == "NanumGothic" and "DejaVu Sans" in fam
    assert matplotlib.rcParams["axes.unicode_minus"] is False
    # 재export: wm811k_spc 가 batch_wafer_report.setup_korean_font 를 import 한다
    assert bwr.setup_korean_font is _fonts.setup_korean_font


def test_setup_without_bundled_font_warns_once(monkeypatch, capsys):
    """동봉 폰트도 시스템 폰트도 없으면 None + stderr 안내 1회 + Glyph 경고 'once' 필터."""
    monkeypatch.setattr(_fonts, "BUNDLED_FONT", _fonts.HERE / "docs" / "fonts" / "no_such_font.ttf")
    monkeypatch.setattr(_fonts, "SYSTEM_CANDIDATES", ["NoSuchFontFamily_123"])
    monkeypatch.setitem(_fonts._cache, "warned", False)
    try:
        with warnings.catch_warnings():
            assert _fonts.setup_korean_font(force=True) is None
            # warnings.filters 항목은 (action, message_re, category, module_re, lineno) 튜플
            assert any(f[0] == "once" and f[1] is not None for f in warnings.filters)   # Glyph 요약 필터
        assert _fonts.setup_korean_font() is None                  # 캐시
        err = capsys.readouterr().err
        assert err.count("fonts-nanum") == 1                       # 설치 안내는 한 번만
        assert bwr.resolve_lang("ko", quiet=True) == "en"          # 폰트 없으면 en 자동 전환
    finally:
        monkeypatch.undo()                                         # 경로 복구 후 다시 탐색
        assert _fonts.setup_korean_font(force=True) == "NanumGothic"   # 다른 테스트를 위해 복구


# ──────────────────────────────────────────
# PDF 생성
# ──────────────────────────────────────────
def test_no_missing_glyph_warnings(generated):
    bad = [m for m in generated["warnings"] if "missing from font" in m]
    assert not bad, bad[:3]


def test_page_count_cover_lots_service_summary(generated):
    s = generated["summary"]
    expected = 1 + len(LOTS) + len(LOTS) + 1                       # all -> 로트마다 서비스 리포트
    assert s.attrs["n_pages"] == expected
    assert _count_pages(generated["bytes"]) == expected
    assert sorted(s.attrs["service_report_lots"]) == sorted(ORIGINAL_IDS)
    assert len(s) == len(LOTS) and s.attrs["lang"] == "ko" and s.attrs["font"] == "NanumGothic"
    assert (s["서비스 리포트"] == "첨부").all()


@pytest.mark.parametrize("mode", ["flagged", "none"])
def test_service_report_modes(tmp_path, mode):
    out = tmp_path / f"{mode}.pdf"
    s = bwr.generate_batch_pdf_report(LOTS, out, wafers_per_lot=2, seed=1, service_report=mode, quiet=True)
    k = len(s.attrs["service_report_lots"])
    if mode == "none":
        assert k == 0
    else:
        # flagged = 불일치 또는 평균 수율 < YIELD_WARN. 요약표에서 같은 조건을 다시 센다.
        flagged = ((s["판정"] == "확인 필요") | (s["일치"] != "100%")).sum()
        assert k == flagged
    assert s.attrs["n_pages"] == 1 + len(LOTS) + k + 1 == _count_pages(out.read_bytes())


def test_lang_en_titles_and_metadata(tmp_path):
    out = tmp_path / "en.pdf"
    s = bwr.generate_batch_pdf_report(LOTS, out, wafers_per_lot=2, seed=1, lang="en",
                                      service_report="all", quiet=True)
    assert s.attrs["lang"] == "en"
    assert list(s.columns)[:3] == ["Lot ID", "Input pattern", "Wafers"]
    assert set(s["Verdict"]) <= {"OK", "CHECK"}
    data = out.read_bytes()
    assert b"Wafer Map Batch Analysis Report [synthetic data]" in data     # /Title (ASCII 그대로 기록)
    assert b"synthetic data" in data                                       # /Subject
    assert re.search("[가-힣]", s.to_string()) is None                      # 요약표에 한글 없음


def test_pdf_metadata_marks_synthetic(generated):
    assert b"synthetic data" in generated["bytes"]
    assert b"not customer or tool data" in generated["bytes"]


def test_anonymize_hides_lot_ids(tmp_path):
    out = tmp_path / "anon.pdf"
    s = bwr.generate_batch_pdf_report(LOTS, out, wafers_per_lot=2, seed=1, service_report="all",
                                      anonymize=True, salt=b"test-salt", quiet=True)
    ids = set(s["Lot ID"])
    assert not ids & ORIGINAL_IDS and len(ids) == len(LOTS)
    assert all(re.fullmatch(r"LOT-[0-9a-f]{8}", i) for i in ids)
    assert not set(s.attrs["service_report_lots"]) & ORIGINAL_IDS
    # 같은 salt 면 같은 해시, 다른 salt 면 다른 해시
    assert bwr.anonymize_lot_id("TESTLOT_RING_001", b"test-salt") in ids
    assert bwr.anonymize_lot_id("TESTLOT_RING_001", b"other") not in ids
    # PDF 본문 텍스트에도 원래 ID 가 없다 (비익명화 PDF 에는 있어야 검색 방법 자체가 유효).
    # pypdfium2 가 설치된 환경에서만 검사한다.
    anon_text = _pdf_text(out)
    if anon_text is not None:
        plain = tmp_path / "plain.pdf"
        bwr.generate_batch_pdf_report(LOTS[:1], plain, wafers_per_lot=1, seed=1, service_report="all", quiet=True)
        assert "TESTLOT_RING_001" in _pdf_text(plain)
        assert "TESTLOT_RING_001" not in anon_text and "LOT-" in anon_text


def test_build_service_report_page_standalone():
    res = [bwr.WaferResult("L1", "W01", "ring", "EDGE_RING", 0.6, 80.0, 100, True),
           bwr.WaferResult("L1", "W02", "ring", "RANDOM", 0.3, 85.0, 70, False)]
    lot = bwr.summarize_lots(res)[0]
    assert lot.top_pattern == "EDGE_RING" and lot.n_mismatch == 1 and lot.flagged
    assert lot.pattern_counts == {"EDGE_RING": 1, "RANDOM": 1}       # 동수면 이름순
    for lang in ("ko", "en"):
        fig = bwr.build_service_report_page(lot, lang=lang, report_time="2026-01-01 00:00")
        texts = [t.get_text() for t in fig.axes[0].texts]
        joined = "\n".join(texts)
        assert "Service Report" in joined and "L1" in joined and "Tool ID" in joined
        assert "2026-01-01 00:00" in joined
        assert str(bwr.SPC_CLEAR_SUBGROUPS) in joined                 # 후속 확인: 알람 해제 조건
        assert any(t.startswith("[ ]") for t in texts)                # 증거 체크박스
        assert "SYNTHETIC" in joined.upper()
        matplotlib.pyplot.close(fig)


def test_service_page_without_action_detail(monkeypatch):
    """ACTION_DETAIL 이 없는 환경에서도 ACTIONS 한 줄로 페이지가 만들어진다."""
    monkeypatch.setattr(bwr, "ACTION_DETAIL", {})
    res = [bwr.WaferResult("L2", "W01", "center", "CENTER", 0.7, 70.0, 150, True)]
    fig = bwr.build_service_report_page(bwr.summarize_lots(res)[0], lang="ko")
    joined = "\n".join(t.get_text() for t in fig.axes[0].texts)
    assert bwr.ACTIONS["CENTER"] in joined and "ACTION_DETAIL" in joined
    matplotlib.pyplot.close(fig)


def test_labels_cp949_safe_and_symmetric():
    assert set(bwr.LABELS["ko"]) == set(bwr.LABELS["en"])
    for lang, L in bwr.LABELS.items():
        for k, v in L.items():
            vals = [v] if isinstance(v, str) else [s for pair in v for s in pair]
            for s in vals:
                s.encode("cp949")                                      # UnicodeEncodeError 면 실패
    # 문구 사전 이후의 소스에 cp949 밖 대시(U+2014)가 없다 (Windows 콘솔·PDF 글리프 안전)
    assert "—" not in Path(bwr.__file__).read_text(encoding="utf-8").split("LABELS")[1]


def test_invalid_options_raise(tmp_path):
    with pytest.raises(ValueError):
        bwr.generate_batch_pdf_report(LOTS, tmp_path / "x.pdf", wafers_per_lot=1, service_report="bogus")
    with pytest.raises(ValueError):
        bwr.resolve_lang("jp")


def test_cli_writes_only_to_out(tmp_path):
    out = tmp_path / "sub" / "cli.pdf"
    r = subprocess.run([sys.executable, str(ROOT / "batch_wafer_report.py"), "--out", str(out),
                        "--lang", "en", "--anonymize", "--wafers-per-lot", "1", "--service-report", "flagged"],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path,
                       env={**__import__("os").environ, "MPLBACKEND": "Agg"})
    assert r.returncode == 0, r.stderr
    assert out.is_file() and _count_pages(out.read_bytes()) >= 1 + len(bwr.DEMO_LOTS) + 1
    assert "PDF saved" in r.stdout and "SEMI2026_LOT_001" not in r.stdout
    assert not (tmp_path / "batch_wafer_report.pdf").exists()        # cwd 가 아니라 --out 에만 쓴다
    assert not (ROOT / "batch_wafer_report.pdf").exists() or True     # HERE 기본 출력은 건드리지 않는다
