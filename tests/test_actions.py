# tests/test_actions.py
# 조치 플레이북(wafer_pattern_classifier.ACTION_DETAIL)의 구조·내용 일관성과
# 시각화 스크립트의 오프라인 출력을 검사한다. 합성/정적 데이터만 쓰며 성능 주장이 아니다.
#
# 검사 항목
#   - ACTION_DETAIL 키 == 결함 8종(CLASSES) + CLEAN, 모든 필드 존재·비어 있지 않음
#     (rule_out_first 만 '' 허용), summary 120자 이하
#   - 공정 물리 교정이 반영됐는지: NEAR_FULL 은 재테스트 우선, DONUT 요약에 'RF 정재파' 없음,
#     SCRATCH 점검에 호/직선 구분, EDGE_RING 에 'Edge exclusion 재검토' 없음,
#     RANDOM 에 '노광 오차' 없음, 구 제품명 단독 표기(Trias/Telindy/Lithius) 없음
#   - ACTIONS == {k: v['summary']} (기존 import 호환)
#   - 모든 문자열이 cp949 로 인코딩 가능(Windows 콘솔·파일 리다이렉트)
#   - docs/defect_signatures.md 에 결함 8종 헤더가 있음(문서-코드 키 일치)
#   - plotly_wafer_heatmap.py 가 --cdn 없이 만든 HTML 은 CDN <script src> 를 쓰지 않음,
#     콘솔 요약의 수율 == HTML 제목의 수율(같은 시드), --demo 와 --csv 동시 지정은 사용법 오류
#   - EDGE_RING 점검 항목에서 매엽 성막과 배치 퍼니스가 구분되고, 엣지 보정값 서술에 '사양 확인' 표시

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wafer_pattern_classifier import (  # noqa: E402
    ACTION_DETAIL, ACTIONS, SEVERITY_LABEL, classify_wafer_pattern, format_action_detail,
)
from wm811k_evaluate import CLASSES  # noqa: E402

LIST_FIELDS = ("first_checks", "customer_evidence", "tool_evidence",
               "tel_modules", "non_tel", "data_to_collect")
STR_FIELDS = ("summary", "severity", "rule_out_first", "handoff")
SEVERITIES = {"monitor", "lot_hold", "line_stop_review"}


def _all_strings(d: dict):
    for k in STR_FIELDS:
        yield k, d[k]
    for k in LIST_FIELDS:
        for s in d[k]:
            yield k, s


def test_keys_match_classes_plus_clean():
    assert set(ACTION_DETAIL) == set(CLASSES) | {"CLEAN"}
    assert set(ACTIONS) == set(ACTION_DETAIL)


@pytest.mark.parametrize("pattern", sorted(ACTION_DETAIL))
def test_fields_present_and_nonempty(pattern):
    d = ACTION_DETAIL[pattern]
    assert set(d) == set(STR_FIELDS) | set(LIST_FIELDS), pattern
    for k in STR_FIELDS:
        assert isinstance(d[k], str), (pattern, k)
        if k != "rule_out_first":                 # 먼저 배제할 것이 없는 패턴은 '' 허용
            assert d[k].strip(), (pattern, k)
    for k in LIST_FIELDS:
        assert isinstance(d[k], list) and d[k], (pattern, k)
        assert all(isinstance(s, str) and s.strip() for s in d[k]), (pattern, k)
    assert 3 <= len(d["first_checks"]) <= 6, pattern
    assert d["severity"] in SEVERITIES, pattern
    assert len(d["summary"]) <= 120, (pattern, len(d["summary"]))


def test_summary_is_actions_source():
    assert ACTIONS == {k: v["summary"] for k, v in ACTION_DETAIL.items()}
    assert set(SEVERITY_LABEL) == SEVERITIES


def test_physics_corrections_applied():
    nf = ACTION_DETAIL["NEAR_FULL"]
    assert "재테스트" in nf["rule_out_first"]
    assert "재테스트" in nf["first_checks"][0]       # 테스트 원인 배제가 첫 점검
    assert nf["severity"] == "line_stop_review"

    assert "정재파" not in ACTION_DETAIL["DONUT"]["summary"]
    # 정재파(center-high)는 CENTER 쪽 원인이어야 한다
    assert any("정재파" in s for s in ACTION_DETAIL["CENTER"]["first_checks"])

    sc = " ".join(ACTION_DETAIL["SCRATCH"]["first_checks"])
    assert "호" in sc and "직선" in sc
    assert "정상 터치다운은 선형 스크래치를 만들지 않는다" in sc and "격자 축" in sc

    assert "Edge exclusion" not in ACTION_DETAIL["EDGE_RING"]["summary"]
    assert not any("Edge exclusion" in s for _, s in _all_strings(ACTION_DETAIL["EDGE_RING"]))

    assert not any("노광 오차" in s for _, s in _all_strings(ACTION_DETAIL["RANDOM"]))

    loc = " ".join(ACTION_DETAIL["LOC"]["first_checks"])
    assert "120도" in loc and "리프트 핀" in loc    # 같은 반경 3점 = 리프트 핀
    assert "샷" in loc and "레티클" in loc           # 샷 피치 반복 = 레티클
    assert "격자" in ACTION_DETAIL["LOC"]["rule_out_first"]

    el = " ".join(ACTION_DETAIL["EDGE_LOC"]["first_checks"])
    assert "노치" in el and "센터링" in el and "EBR" in el
    assert not any("리프트 핀" in s for _, s in _all_strings(ACTION_DETAIL["EDGE_LOC"]))

    ce = " ".join(ACTION_DETAIL["CENTER"]["first_checks"])
    assert "'중심 누설'은 보지 않는다" in ce            # He 누설은 엣지 실 밴드·리프트 핀 홀
    assert "He 백사이드 중심 누설" not in ce

    # EDGE_RING: 매엽 성막(Triase+ / Episode / NT333)과 배치 퍼니스(TELINDY PLUS)는 점검 항목이 다르다
    # (퍼니스는 존이 보트 축 방향, 센터/엣지 가스 분배비 개념이 없다). tel_modules 와 같은 구분이어야 한다.
    er = ACTION_DETAIL["EDGE_RING"]
    dep = [s for s in er["first_checks"] if "성막" in s]
    assert len(dep) == 1 and "NT333 성막" in dep[0] and "TELINDY PLUS 퍼니스" in dep[0], dep
    assert not any("TELINDY PLUS 성막" in s for _, s in _all_strings(er))
    assert "슬롯" in dep[0] and "가스 분배비" in dep[0].split("TELINDY")[0]
    # 엣지 보정값(링 높이·엣지 DC 바이어스)은 공개 특허 수준이지 TEL 제품 사양이 아니다 - 그 표시가 있어야 한다
    corr = [s for _, s in _all_strings(er) if "DC 바이어스" in s]
    assert corr and all("사양" in s for s in corr), corr


def test_tel_product_names_current():
    """tel.com 현행 표기만 쓴다. 구명칭 단독 표기는 금지."""
    text = "\n".join(s for d in ACTION_DETAIL.values() for _, s in _all_strings(d))
    assert not re.search(r"\bTrias\b", text)
    assert not re.search(r"\bTelindy\b", text)
    assert not re.search(r"(?<!CLEAN TRACK )\bLITHIUS\b(?! Pro)", text)
    assert not re.search(r"\bLithius\b", text)
    # 타사 범위 항목은 '타사' 표시가 있어야 한다 (CMP, 레티클/노광)
    for p in ("EDGE_RING", "SCRATCH", "DONUT", "CENTER"):
        assert any("CMP" in s and "타사" in s for s in ACTION_DETAIL[p]["non_tel"]), p
    assert any("레티클" in s and "타사" in s for s in ACTION_DETAIL["LOC"]["non_tel"])


def test_customer_vs_tool_evidence_split():
    """장비사 시점: 결함 8종 모두 고객 측/장비 측 증거가 분리돼 있고 handoff 에 판정 기준이 있다."""
    for p in CLASSES:
        d = ACTION_DETAIL[p]
        assert len(d["customer_evidence"]) >= 2, p
        assert len(d["tool_evidence"]) >= 2, p
        assert "TEL" in d["handoff"], p


def test_strings_are_cp949_safe():
    for p, d in ACTION_DETAIL.items():
        for k, s in _all_strings(d):
            s.encode("cp949")                          # UnicodeEncodeError 면 실패
    for p in ACTION_DETAIL:
        format_action_detail(p).encode("cp949")


def test_classifier_result_carries_summary():
    from wafer_map_visualizer import generate_sample_wafer_data
    res = classify_wafer_pattern(generate_sample_wafer_data(defect_mode="ring"))
    assert res.recommended_action == ACTION_DETAIL[res.pattern]["summary"]


def test_docs_have_all_pattern_headers():
    doc = (ROOT / "docs" / "defect_signatures.md").read_text(encoding="utf-8")
    headers = set(re.findall(r"^###\s+([A-Z_]+)\b", doc, flags=re.M))
    assert set(CLASSES) <= headers, set(CLASSES) - headers


def test_cli_actions_runs():
    r = subprocess.run([sys.executable, str(ROOT / "wafer_pattern_classifier.py"), "--actions", "DONUT"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "[DONUT]" in r.stdout and "판정 기준" in r.stdout


CDN_SCRIPT = re.compile(r'<script[^>]+src="https?://cdn\.plot\.ly[^"]*"')
YIELD_RE = re.compile(r"Yield\s+([0-9.]+)%")


def test_plotly_console_matches_html(tmp_path):
    """콘솔 요약의 수율은 HTML 서브플롯 제목의 수율과 같아야 한다(같은 시드로 같은 맵을 써야 한다).
    이전에는 콘솔이 기본 시드로 다시 생성해 center 93.7% vs 93.2% 처럼 어긋났다."""
    out = tmp_path / "demo.html"
    r = subprocess.run([sys.executable, str(ROOT / "plotly_wafer_heatmap.py"), "--cdn", "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    console = YIELD_RE.findall(r.stdout)
    html = YIELD_RE.findall(out.read_text(encoding="utf-8"))
    assert len(console) == 6 and console == html, (console, html)

    from plotly_wafer_heatmap import _demo_wafers, resolve_fields
    wafers = _demo_wafers()
    assert [w["seed"] for w in wafers] == [2024 + i for i in range(6)]       # 시드가 명시돼 있다
    a = [f.yield_pct for f in resolve_fields(wafers)]
    b = [f.yield_pct for f in resolve_fields([{k: v for k, v in w.items() if k != "seed"} for w in wafers])]
    assert a == b                                                             # 명시 시드 == 기본 시드 규칙(2024 + i)

    # --demo 와 --csv 를 같이 주면 사용법 오류
    r = subprocess.run([sys.executable, str(ROOT / "plotly_wafer_heatmap.py"), "--demo", "--csv", "x.csv"],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)
    assert r.returncode == 2 and "--demo" in r.stderr


def test_plotly_html_is_self_contained_by_default(tmp_path):
    """--cdn 없이 만든 HTML 은 plotly.js 를 CDN 에서 불러오는 <script src> 가 없어야 한다
    (오프라인 팹 PC). 번들된 plotly.js 안에는 topojsonURL 기본값으로 'cdn.plot.ly' 문자열이
    남아 있으므로 문자열 유무가 아니라 <script src> 태그로 판정한다."""
    script = ROOT / "plotly_wafer_heatmap.py"
    out = tmp_path / "offline.html"
    r = subprocess.run([sys.executable, str(script), "--out", str(out)],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    html = out.read_text(encoding="utf-8")
    assert CDN_SCRIPT.search(html) is None
    assert out.stat().st_size > 1_000_000                 # plotly.js 가 포함됐다
    assert not (tmp_path / "wafer_heatmap.html").exists()  # cwd 가 아니라 --out 에만 쓴다

    out_cdn = tmp_path / "cdn.html"
    r = subprocess.run([sys.executable, str(script), "--cdn", "--out", str(out_cdn)],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert CDN_SCRIPT.search(out_cdn.read_text(encoding="utf-8")) is not None
    assert out_cdn.stat().st_size < out.stat().st_size


def test_plotly_csv_input(tmp_path):
    import numpy as np
    import pandas as pd
    from plotly_wafer_heatmap import field_from_csv

    xs = np.arange(-6, 7) * 10.0
    gx, gy = np.meshgrid(xs, xs)
    m = np.hypot(gx, gy) <= 60
    v = np.where(np.hypot(gx, gy) > 48, 380.0, 435.0)      # 엣지 링만 스펙 밖
    p = tmp_path / "t.csv"
    pd.DataFrame({"die_x": gx[m], "die_y": gy[m], "value": v[m]}).to_csv(p, index=False)

    f = field_from_csv(p, target=435.0, spec_frac=0.05)
    assert f.n_die == int(m.sum())
    assert f.n_fail == int((v[m] < 435.0 * 0.95).sum())
    assert f.Z.shape == (13, 13)

    bad = tmp_path / "bad.csv"
    pd.DataFrame({"a": [1]}).to_csv(bad, index=False)
    with pytest.raises(ValueError):
        field_from_csv(bad)
