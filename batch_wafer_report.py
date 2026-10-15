# batch_wafer_report.py
# 여러 Lot 웨이퍼 맵 배치 PDF 리포트 + 로트별 1페이지 서비스 리포트(양식)
#
# 배경
#   장비사 기술지원 엔지니어의 산출물은 F1 점수가 아니라 고객에게 보내는 보고서다.
#   로트 단위로 웨이퍼 맵을 나란히 놓고 분류 결과·수율을 집계한 뒤, 문제 로트에는
#   '현상 -> 분류 -> 의심 원인 순위 -> 권고 조치 -> 후속 확인 -> 증거 체크' 순서의
#   서비스 리포트 양식을 붙인다. 조치 문구는 wafer_pattern_classifier.ACTION_DETAIL
#   한 곳에서 가져오므로 docs/defect_signatures.md 와 어긋나지 않는다.
#
# 무엇을 하나
#   1) 표지 - 로트 페이지(웨이퍼 맵 그리드 + 분류 결과) - 서비스 리포트 - 요약표 순으로
#      A4 PDF 를 만든다. 서비스 리포트는 기본값으로 '불일치 또는 수율 경고' 로트에만
#      붙는다(--service-report all|flagged|none).
#   2) --lang ko|en 으로 제목·표 머리·문구를 전환한다. 한글 폰트가 없으면 en 으로 자동 전환.
#   3) --anonymize 로 로트 ID 를 짧은 키드 해시로 치환한다(매핑 표는 저장하지 않는다).
#   4) 출력은 스크립트 옆(HERE)에 저장한다. PDF 메타데이터에 'synthetic data' 를 적는다.
#   5) SOURCE_DATE_EPOCH 가 설정돼 있으면 생성일시·CreationDate 를 그 시각으로 고정한다(재현 가능한 산출물;
#      make_figures.py 가 커밋용 샘플 PDF 를 만들 때 쓴다).
#
# 왜
#   - 폰트: matplotlib 기본 폰트에 한글이 없어 환경에 따라 리포트가 깨졌다. _fonts.py 가
#     동봉 폰트(docs/fonts/)를 등록하고, 모든 그리기 전에 setup_korean_font() 를 부른다.
#   - 익명화: 벤더 엔지니어는 고객 로트 ID 를 NDA 아래 다룬다. 저장소 밖으로 나가는
#     리포트는 ID 를 가릴 수 있어야 한다.
#
# 한계
#   합성 데이터다. 생성기와 분류기가 같은 규칙을 공유하므로 요약표의 '분류 일치율'은
#   성능이 아니라 파이프라인 무결성 확인이다. 실측 성능은 README 의 WM-811K 결과를 쓸 것.
#   서비스 리포트의 Tool/Chamber 필드는 비워 둔 양식이며 실제 장비 식별자를 넣지 않는다. '입력(기대)
#   패턴·분류 불일치' 는 생성기 전용 정보라 로트 페이지·요약표에만 있고 서비스 리포트 양식에는 없다.
#   ACTION_DETAIL 의 장비 서술은 공개 자료 기준이고 TEL 내부 구현·PM 주기는 모른다.
#
# 사용법
#   python batch_wafer_report.py                      # HERE/batch_wafer_report.pdf (ko, flagged)
#   python batch_wafer_report.py --lang en --anonymize --service-report all --out report.pdf
#   python batch_wafer_report.py --wafers-per-lot 3 --seed 7
#
# 원본 대비 수정 사항
#   (여기서 '원본'은 이 저장소 최초 커밋 1df6309 의 초기 스크립트다.)
#   [버그] generate_sample_wafer_data / plot_wafer_map / classify_wafer_pattern
#          import 누락 -> NameError.
#   [버그] res = classify_wafer_pattern(df) 인데 result.yield_pct 를 참조 -> NameError.
#   [버그] 로트 내 웨이퍼가 전부 픽셀 단위로 동일했다(seed 고정). -> 웨이퍼별 seed + noise.
#   [버그] wafers_per_lot=1 이면 plt.subplots 가 Axes 스칼라를 반환해 enumerate 가 실패.
#          -> squeeze=False.
#   [버그] 분류기를 호출하고도 결과를 버렸다. -> 분류 결과와 점수를 표시하고 입력과
#          불일치하면 표시한다.
#   [버그] 한글 글리프 없는 기본 폰트로 제목이 전부 사각형. -> _fonts.setup_korean_font.
#   [버그] bbox_inches="tight" 는 페이지마다 PDF 크기를 다르게 만든다. -> A4 고정.
#   [버그] plot_wafer_map 의 축별 범례가 아래 행 제목과 겹친다. -> figure 범례 1개.
#   [개선] 요약 페이지, 3열 그리드, defect_mode 7종, random.choice 시드.
#   [개선] 서비스 리포트 페이지, --lang, --anonymize, HERE 기준 저장, cp949 안전 문자열.

from __future__ import annotations

import argparse
import hashlib
import math
import os
import random
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from _fonts import has_korean_font, setup_korean_font  # noqa: F401  (setup_korean_font 재export)
from wafer_map_visualizer import (
    FAIL_COLOR,
    PASS_COLOR,
    generate_sample_wafer_data,
    plot_wafer_map,
)
import wafer_pattern_classifier as _wpc
from wafer_pattern_classifier import classify_wafer_pattern, expected_patterns

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE / "batch_wafer_report.pdf"

A4_LANDSCAPE = (11.69, 8.27)
A4_PORTRAIT = (8.27, 11.69)
MAX_COLS = 3
NOISE = 0.03
YIELD_WARN = 90.0
# SPC 알람 해제(조치 효과 확인) 기준 - 이 저장소의 운용 규칙 한 벌. docs/spc.md '알람 해제 기준',
# docs/handoff.md 종결 보고, docs/case_study_8d.md D6 가 같은 기준을 쓴다.
#   (1) 조치 이벤트 이후 완성된 부분군 SPC_CLEAR_SUBGROUPS 개에서 상승 규칙(R1~R4)·EWMA 알람 0 건
#   (2) 조치 전후 원시 비율의 이항 검정 p >= 0.05 (조치 후 비율이 baseline 과 다르지 않음; roadmap 10-d)
#   (3) 드문 패턴(부분군이 커서 조치 후 부분군이 아직 안 찬 것)은 (2) 로 먼저 판정하고 다음 부분군 완성 때 (1) 재확인
# '중심선 +-1 sigma 안' 은 쓰지 않는다 - WE 의 '15점 연속 1 sigma 안(층화 경고)' 과 방향이 겹친다.
# 5 는 케이스 스터디 A(D6: 부분군 5개 5174~5974) 와 같은 값. EWMA 는 lambda 0.2 의 기억 때문에
# 복귀가 몇 부분군 늦으므로 (1) 은 '새 상승 알람 없음' 으로 본다.
SPC_CLEAR_SUBGROUPS = 5
SPC_CLEAR_P = 0.05


def _now() -> datetime:
    """현재 시각. SOURCE_DATE_EPOCH 가 있으면 그 시각(UTC) - make_figures.py 가 커밋용 그림·PDF 를
    재현 가능하게 만들 때 쓴다(matplotlib 도 같은 변수로 PDF/SVG 날짜 메타데이터를 고정한다)."""
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
    return datetime.now()


def positive_int(text: str) -> int:
    """argparse type: 1 이상의 정수. --wafers-per-lot 0 은 ZeroDivisionError 대신 사용법 오류로."""
    try:
        v = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"integer expected: {text!r}") from None
    if v < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1: {text!r}")
    return v

ALL_MODES = ["ring", "center", "donut", "edge_loc", "scratch", "random", "clean"]
# 일치 판정은 wafer_pattern_classifier.expected_patterns(mode, NOISE) 로 한다.
# clean 로트에 NOISE 3%를 섞으면 CLEAN 임계값 2% 근처가 되어 CLEAN/RANDOM 둘 다 정답이다.

ACTIONS: dict[str, str] = _wpc.ACTIONS
ACTION_DETAIL: dict[str, dict] = getattr(_wpc, "ACTION_DETAIL", {})
SEVERITY_LABEL: dict[str, str] = getattr(_wpc, "SEVERITY_LABEL", {})

SERVICE_REPORT_MODES = ("all", "flagged", "none")

# ──────────────────────────────────────────
# 문구 사전. 모든 값은 cp949 로 인코딩 가능해야 한다(tests/test_report.py 가 검사).
# ──────────────────────────────────────────
LABELS: dict[str, dict[str, str]] = {
    "ko": {
        "cover_title": "웨이퍼 맵 자동 분석 리포트",
        "cover_time": "생성일시  {t}",
        "cover_counts": "총 {n} Lot  |  Lot당 {w}장  |  합계 {total}장",
        "cover_note": ("합성 데이터 기반. 생성기와 분류기가 동일한 규칙을 공유하므로\n"
                       "요약표의 분류 일치율은 파이프라인 무결성 확인이며 성능 지표가 아니다."),
        "cover_anon": "로트 ID 는 키드 해시로 익명화됨 (매핑 표 미저장)",
        "font_warn": "WARNING: Korean font not found - text may render as boxes",
        "wafer_title": "{w}  수율 {y:.1f}%  FAIL {f}\n분류: {p} (score {s:.2f})",
        "mismatch": "  [불일치]",
        "lot_title": "Lot {lot}   |   입력 패턴 {mode}   |   평균 수율 {avg:.1f}%",
        "lot_mismatch": "   |   분류 불일치 {n}장",
        "summary_title": "요약 - 로트별 집계",
        "col_lot": "Lot ID", "col_mode": "입력 패턴", "col_n": "웨이퍼", "col_avg": "평균 수율",
        "col_min": "최저 수율", "col_top": "분류 결과 (최다)", "col_match": "일치", "col_verdict": "판정",
        "col_service": "서비스 리포트",
        "verdict_warn": "확인 필요", "verdict_ok": "정상", "yes": "첨부", "no": "-",
        "summary_foot": ("전체 {total}장  |  평균 수율 {avg:.1f}%  |  "
                         "수율 {warn:.0f}% 미만 {low}장  |  분류 일치 {match:.0%}"),
        "summary_note": ("일치율은 입력 패턴과 분류 결과의 부합 여부다. 합성 데이터에서는\n"
                         "코딩 오류가 없다는 확인까지만 의미하며, 실측 정확도가 아니다."),
        # 서비스 리포트
        "sr_title": "서비스 리포트 / Service Report",
        "sr_banner": "합성 데이터 - 양식 예시 / SYNTHETIC DATA - form sample. 실제 장비·고객 데이터가 아니다.",
        # 머리 표 12칸(2열 x 6행). docs/handoff.md 2절 '초동 보고' 항목(현상·심각도·봉쇄 조치 제안·
        # 요청 데이터·다음 보고 시각)과 1:1 - 요청 데이터는 5절 '수집 데이터' 에 있다.
        "sr_meta": [("장비 ID / Tool ID", ""), ("챔버 / Chamber", ""), ("로트 / Lot", "{lot}"),
                    ("일자 / Date", "{date}"), ("작성자 / Engineer", ""), ("고객 담당 / Customer contact", ""),
                    ("보고서 번호 / Report No.", ""), ("심각도 / Severity", "{sev}"),
                    ("영향 범위 / Affected scope", "{scope}"), ("봉쇄 조치 제안 / Containment", "{contain}"),
                    ("보고 단계 / Report stage", "{stage}"), ("다음 보고 예정 / Next report", "")],
        "sr_stage": "초동 보고 / initial",
        "sr_scope": "로트 1 / {n}장 (수율 {warn:.0f}% 미만 {low}장)",
        "sr_contain": {"monitor": "홀드 없음 - 관리도 모니터링", "lot_hold": "로트 홀드 검토, 챔버 격리 여부 판단",
                       "line_stop_review": "로트 홀드 + 라인 정지 판단 요청", "": "-"},
        "sr_sev_escalated": " (+1: 로트 내 반복)",
        "sr_h_obs": "1. 현상 / Observation",
        "sr_obs": ("웨이퍼 {n}장 중 패턴 분포 {mix}. 평균 수율 {avg:.1f}% (최저 {mn:.1f}%), "
                   "수율 {warn:.0f}% 미만 {low}장."),
        "sr_h_cls": "2. 분류 결과와 점수 / Classification and score",
        "sr_cls_row": "{w}: {p} (score {s:.2f}), 수율 {y:.1f}%, FAIL {f}{flag}",
        "sr_cls_more": "... 외 {n}장 (로트 페이지 참조)",
        "sr_h_cause": "3. 의심 원인 순위 / Suspected causes (ranked)   - 대표 패턴 {p}",
        "sr_rule_out": "먼저 배제: {s}",
        "sr_tel": "TEL 모듈 / TEL modules:",
        "sr_non_tel": "타사 인계 / Non-TEL hand-off:",
        "sr_h_action": "4. 권고 조치 / Recommended action",
        "sr_action": "[{sev}] {s}",
        "sr_handoff": "판정 기준: {s}",
        "sr_h_follow": "5. 후속 확인 / Follow-up",
        "sr_follow": ("SPC 알람 해제 기준(docs/spc.md): (1) 조치 이벤트 이후 부분군 {n}개에서 상승 규칙(R1~R4)·EWMA 알람 0건, "
                      "(2) 조치 전후 원시 비율의 이항 검정 p >= {p:.2f}, (3) 드문 패턴은 (2)로 먼저 판정하고 다음 부분군 완성 때 (1) 재확인. "
                      "확인 시각을 alarms.csv 의 verified_at 에 적는다."),
        "sr_follow2": "수집 데이터 / Data to collect: {s}",
        "sr_h_evid": "6. 증거 체크 / Evidence checklist",
        "sr_evid_cust": "고객 측 / Customer-side",
        "sr_evid_tool": "장비 측 / Tool-side",
        "sr_h_notes": "7. 비고 / Notes (현장 기록: 확인한 것 / 배제한 것 / 다음 행동)",
        "sr_sign": "작성 / Prepared: ____________    검토 / Reviewed: ____________    고객 확인 / Customer ack: ____________",
        "sr_foot": ("조치 문구는 wafer_pattern_classifier.ACTION_DETAIL (docs/defect_signatures.md 와 동일 소스) 기준. "
                    "공개 자료 수준의 서술이며 TEL 내부 구현·매뉴얼 PM 주기는 모른다. '(추정)' 표시는 확인되지 않은 것."),
        "sr_truncated": "(지면 부족으로 생략 - 전체 항목은 python wafer_pattern_classifier.py --actions {p})",
        "sr_no_detail": "상세 플레이북(ACTION_DETAIL) 없음 - 한 줄 요약(ACTIONS)만 표시.",
        "pdf_title": "웨이퍼 맵 자동 분석 배치 리포트 [synthetic data]",
        # 콘솔
        "c_font": "한글 폰트: {f}",
        "c_font_none": "[경고] 한글 폰트를 찾지 못해 리포트 언어를 en 으로 전환한다.",
        "c_lot": "  {lot:20s} {mode:9s} {n}장 평균 수율 {avg:5.1f}%",
        "c_mis": "  불일치 {n}장",
        "c_sr": "  [서비스 리포트]",
        "c_saved": "\nPDF 저장: {p} (페이지 {pages}: 표지 1 + 로트 {lots} + 서비스 리포트 {sr} + 요약 1, 웨이퍼 {wafers}장)",
    },
    "en": {
        "cover_title": "Wafer Map Automatic Analysis Report",
        "cover_time": "Generated  {t}",
        "cover_counts": "{n} lots  |  {w} wafers per lot  |  {total} wafers total",
        "cover_note": ("Synthetic data. The generator and the classifier share the same rules, so the\n"
                       "match rate in the summary verifies pipeline integrity; it is not a performance metric."),
        "cover_anon": "Lot IDs anonymized with a keyed hash (mapping table not stored)",
        "font_warn": "WARNING: Korean font not found - text may render as boxes",
        "wafer_title": "{w}  yield {y:.1f}%  FAIL {f}\nclass: {p} (score {s:.2f})",
        "mismatch": "  [MISMATCH]",
        "lot_title": "Lot {lot}   |   input pattern {mode}   |   mean yield {avg:.1f}%",
        "lot_mismatch": "   |   {n} mismatched",
        "summary_title": "Summary - per-lot aggregate",
        "col_lot": "Lot ID", "col_mode": "Input pattern", "col_n": "Wafers", "col_avg": "Mean yield",
        "col_min": "Min yield", "col_top": "Classified (mode)", "col_match": "Match", "col_verdict": "Verdict",
        "col_service": "Service report",
        "verdict_warn": "CHECK", "verdict_ok": "OK", "yes": "attached", "no": "-",
        "summary_foot": ("{total} wafers  |  mean yield {avg:.1f}%  |  "
                         "{low} wafers below {warn:.0f}%  |  classification match {match:.0%}"),
        "summary_note": ("Match = agreement between the input pattern and the classifier output. On synthetic\n"
                         "data this only shows there is no coding error; it is not measured accuracy."),
        "sr_title": "Service Report",
        "sr_banner": "SYNTHETIC DATA - form sample. Not real tool or customer data.",
        "sr_meta": [("Tool ID", ""), ("Chamber", ""), ("Lot", "{lot}"), ("Date", "{date}"),
                    ("Engineer", ""), ("Customer contact", ""), ("Report No.", ""), ("Severity", "{sev}"),
                    ("Affected scope", "{scope}"), ("Containment proposal", "{contain}"),
                    ("Report stage", "{stage}"), ("Next report due", "")],
        "sr_stage": "initial",
        "sr_scope": "1 lot / {n} wafers ({low} below {warn:.0f}%)",
        "sr_contain": {"monitor": "no hold - monitor the chart", "lot_hold": "lot hold review; decide chamber isolation",
                       "line_stop_review": "lot hold + request line-stop decision", "": "-"},
        "sr_sev_escalated": " (+1: repeats in lot)",
        "sr_h_obs": "1. Observation",
        "sr_obs": ("{n} wafers; pattern mix {mix}. Mean yield {avg:.1f}% (min {mn:.1f}%), "
                   "{low} wafers below {warn:.0f}%."),
        "sr_h_cls": "2. Classification and score",
        "sr_cls_row": "{w}: {p} (score {s:.2f}), yield {y:.1f}%, FAIL {f}{flag}",
        "sr_cls_more": "... and {n} more (see lot page)",
        "sr_h_cause": "3. Suspected causes (ranked)   - dominant pattern {p}",
        "sr_rule_out": "Rule out first: {s}",
        "sr_tel": "TEL modules:",
        "sr_non_tel": "Non-TEL hand-off:",
        "sr_h_action": "4. Recommended action",
        "sr_action": "[{sev}] {s}",
        "sr_handoff": "Decision rule: {s}",
        "sr_h_follow": "5. Follow-up",
        "sr_follow": ("SPC alarm clearance (docs/spc.md): (1) zero upward-rule (R1-R4) and EWMA alarms in the {n} subgroups "
                      "completed after the action event, (2) binomial test of the raw rate before vs after the action p >= {p:.2f}, "
                      "(3) for rare patterns decide on (2) first and re-check (1) when the next subgroup completes. "
                      "Record the time in alarms.csv verified_at."),
        "sr_follow2": "Data to collect: {s}",
        "sr_h_evid": "6. Evidence checklist",
        "sr_evid_cust": "Customer-side",
        "sr_evid_tool": "Tool-side",
        "sr_h_notes": "7. Notes (field record: confirmed / ruled out / next action)",
        "sr_sign": "Prepared: ____________    Reviewed: ____________    Customer ack: ____________",
        "sr_foot": ("Action text comes from wafer_pattern_classifier.ACTION_DETAIL (same source as docs/defect_signatures.md). "
                    "Public-source level only; TEL internal implementation and manual PM intervals are unknown. "
                    "Items marked '(estimate)' are unverified. Korean item text is kept as-is (single source)."),
        "sr_truncated": "(truncated for space - full list: python wafer_pattern_classifier.py --actions {p})",
        "sr_no_detail": "No detailed playbook (ACTION_DETAIL) - one-line summary (ACTIONS) only.",
        "pdf_title": "Wafer Map Batch Analysis Report [synthetic data]",
        "c_font": "Korean font: {f}",
        "c_font_none": "[warning] Korean font not found - switching report language to en.",
        "c_lot": "  {lot:20s} {mode:9s} {n} wafers mean yield {avg:5.1f}%",
        "c_mis": "  {n} mismatched",
        "c_sr": "  [service report]",
        "c_saved": "\nPDF saved: {p} (pages {pages}: cover 1 + lots {lots} + service reports {sr} + summary 1, {wafers} wafers)",
    },
}

SEVERITY_EN = {"monitor": "monitor", "lot_hold": "lot hold review", "line_stop_review": "line stop review"}


def resolve_lang(lang: str, quiet: bool = False) -> str:
    """--lang ko 인데 한글 폰트가 없으면 en 으로 전환한다."""
    if lang not in LABELS:
        raise ValueError(f"lang must be one of {list(LABELS)}: {lang!r}")
    if lang == "ko" and not has_korean_font():
        if not quiet:
            print(LABELS["ko"]["c_font_none"], file=sys.stderr)
        return "en"
    return lang


def anonymize_lot_id(lot_id: str, salt: bytes) -> str:
    """로트 ID 를 키드 해시 8 hex 로. 같은 salt 면 같은 값(한 실행 안에서 일관), 매핑 표는 저장하지 않는다."""
    return "LOT-" + hashlib.blake2b(str(lot_id).encode("utf-8"), key=salt, digest_size=4).hexdigest()


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


@dataclass
class LotSummary:
    """서비스 리포트 한 장의 입력. summarize_lots() 가 WaferResult 목록에서 만든다."""
    lot_id: str
    mode: str
    wafers: list[WaferResult] = field(default_factory=list)

    @property
    def n(self) -> int:
        return len(self.wafers)

    @property
    def avg_yield(self) -> float:
        return sum(w.yield_pct for w in self.wafers) / self.n

    @property
    def min_yield(self) -> float:
        return min(w.yield_pct for w in self.wafers)

    @property
    def n_low_yield(self) -> int:
        return sum(w.yield_pct < YIELD_WARN for w in self.wafers)

    @property
    def n_mismatch(self) -> int:
        return sum(not w.matched for w in self.wafers)

    @property
    def pattern_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for w in self.wafers:
            counts[w.pattern] = counts.get(w.pattern, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))

    @property
    def top_pattern(self) -> str:
        return next(iter(self.pattern_counts))

    @property
    def mean_score(self) -> float:
        return sum(w.score for w in self.wafers) / self.n

    @property
    def flagged(self) -> bool:
        """'불일치 또는 수율 경고' - 서비스 리포트 기본 대상."""
        return self.n_mismatch > 0 or self.avg_yield < YIELD_WARN


def summarize_lots(results: list[WaferResult]) -> list[LotSummary]:
    lots: dict[str, LotSummary] = {}
    for r in results:
        lots.setdefault(r.lot_id, LotSummary(r.lot_id, r.mode)).wafers.append(r)
    return list(lots.values())


def wants_service_report(lot: LotSummary, mode: str) -> bool:
    if mode not in SERVICE_REPORT_MODES:
        raise ValueError(f"service_report must be one of {SERVICE_REPORT_MODES}: {mode!r}")
    return mode == "all" or (mode == "flagged" and lot.flagged)


# ──────────────────────────────────────────
# 페이지 구성
# ──────────────────────────────────────────
def _cover_page(pdf: PdfPages, n_lots: int, wafers_per_lot: int, report_time: str,
                font_ok: bool, L: dict[str, str], anonymized: bool) -> None:
    fig = plt.figure(figsize=A4_LANDSCAPE)
    fig.patch.set_facecolor("#1A237E")
    ax = fig.add_subplot(111)
    ax.set_facecolor("#1A237E")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    ax.text(0.5, 0.68, L["cover_title"], ha="center", va="center",
            fontsize=28, fontweight="bold", color="white")
    ax.text(0.5, 0.55, L["cover_time"].format(t=report_time), ha="center", va="center",
            fontsize=13, color="#90CAF9")
    ax.text(0.5, 0.48, L["cover_counts"].format(n=n_lots, w=wafers_per_lot, total=n_lots * wafers_per_lot),
            ha="center", va="center", fontsize=13, color="#90CAF9")
    ax.text(0.5, 0.30, L["cover_note"], ha="center", va="center", fontsize=9, color="#B0BEC5")
    if anonymized:
        ax.text(0.5, 0.20, L["cover_anon"], ha="center", va="center", fontsize=9, color="#B0BEC5")
    if not font_ok:
        ax.text(0.5, 0.10, L["font_warn"], ha="center", va="center", fontsize=9, color="#FFCDD2")

    pdf.savefig(fig)          # bbox_inches 미지정 -> A4 고정
    plt.close(fig)


def _summary_page(pdf: PdfPages | None, results: list[WaferResult], L: dict[str, str],
                  service_lots: set[str]) -> pd.DataFrame:
    """로트별 집계표. 리포트를 넘겨보는 사람이 결론을 얻는 페이지. pdf 가 None 이면 표만 만든다."""
    df = pd.DataFrame([r.__dict__ for r in results])

    rows = []
    for lot in summarize_lots(results):
        top = lot.top_pattern
        rows.append({
            L["col_lot"]: lot.lot_id,
            L["col_mode"]: lot.mode,
            L["col_n"]: lot.n,
            L["col_avg"]: f"{lot.avg_yield:.1f}%",
            L["col_min"]: f"{lot.min_yield:.1f}%",
            L["col_top"]: f"{top} ({lot.pattern_counts[top]}/{lot.n})",
            L["col_match"]: f"{1 - lot.n_mismatch / lot.n:.0%}",
            L["col_verdict"]: L["verdict_warn"] if lot.avg_yield < YIELD_WARN else L["verdict_ok"],
            L["col_service"]: L["yes"] if lot.lot_id in service_lots else L["no"],
        })
    summary = pd.DataFrame(rows).sort_values(L["col_lot"], kind="stable").reset_index(drop=True)
    if pdf is None:
        return summary

    fig = plt.figure(figsize=A4_LANDSCAPE)
    fig.suptitle(L["summary_title"], fontsize=16, fontweight="bold", y=0.95)
    ax = fig.add_subplot(111)
    ax.axis("off")

    # bbox 로 표 위치·높이를 고정한다. loc="upper center" + scale 조합은
    # 행 수에 따라 표가 커지면서 아래 문구와 간격이 제멋대로 벌어진다.
    h = min(0.46, 0.055 * (len(summary) + 1))
    table = ax.table(cellText=summary.values, colLabels=summary.columns,
                     cellLoc="center", bbox=(0.0, 0.92 - h, 1.0, h))
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.auto_set_column_width(col=list(range(len(summary.columns))))

    for (r, c), cell in table.get_celld().items():
        cell.set_edgecolor("#CFD8DC")
        if r == 0:
            cell.set_facecolor("#1565C0")
            cell.set_text_props(color="white", fontweight="bold")
        elif summary.iloc[r - 1][L["col_verdict"]] == L["verdict_warn"]:
            cell.set_facecolor("#FFEBEE")

    total = len(df)
    y_foot = 0.92 - h - 0.10
    ax.text(0.5, y_foot,
            L["summary_foot"].format(total=total, avg=df["yield_pct"].mean(), warn=YIELD_WARN,
                                     low=int((df["yield_pct"] < YIELD_WARN).sum()),
                                     match=df["matched"].mean()),
            transform=ax.transAxes, ha="center", fontsize=11, fontweight="bold")
    ax.text(0.5, y_foot - 0.07, L["summary_note"], transform=ax.transAxes,
            ha="center", fontsize=8, color="#666")

    pdf.savefig(fig)
    plt.close(fig)
    return summary


def _lot_page(pdf: PdfPages, lot_id: str, mode: str, wafers_per_lot: int,
              seed_base: int, L: dict[str, str]) -> list[WaferResult]:
    n = wafers_per_lot
    cols = min(MAX_COLS, n)
    rows = math.ceil(n / cols)

    # squeeze=False -> n=1 에서도 항상 2차원 배열이 온다
    fig, axes = plt.subplots(rows, cols, figsize=A4_LANDSCAPE, squeeze=False)
    flat = axes.ravel()

    out: list[WaferResult] = []
    for i in range(n):
        ax = flat[i]
        # 웨이퍼마다 시드를 바꾼다. 원본은 전 장이 동일했다.
        df = generate_sample_wafer_data(defect_mode=mode, noise=NOISE, seed=seed_base + i)
        res = classify_wafer_pattern(df)
        wafer_id = f"W{i + 1:02d}"

        plot_wafer_map(df, lot_id=lot_id, wafer_id=wafer_id, ax=ax, show_die_coords=False)

        # 축별 범례는 아래 행 제목과 겹친다 -> 제거하고 figure 범례로 대체
        leg = ax.get_legend()
        if leg:
            leg.remove()

        matched = res.pattern in expected_patterns(mode, NOISE)
        ax.set_title(
            L["wafer_title"].format(w=wafer_id, y=res.yield_pct, f=res.fail_count,
                                    p=res.pattern, s=res.score)
            + ("" if matched else L["mismatch"]),
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
        L["lot_title"].format(lot=lot_id, mode=mode.upper(), avg=avg)
        + (L["lot_mismatch"].format(n=n_mis) if n_mis else ""),
        fontsize=13, fontweight="bold", y=0.97,
        color="#C62828" if (avg < YIELD_WARN or n_mis) else "#1A237E",
    )
    fig.legend(
        handles=[
            plt.Line2D([], [], marker="s", linestyle="", markersize=9, color=PASS_COLOR, label="PASS"),
            plt.Line2D([], [], marker="s", linestyle="", markersize=9, color=FAIL_COLOR, label="FAIL"),
        ],
        loc="lower center", ncol=2, frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.015),
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    pdf.savefig(fig)
    plt.close(fig)
    return out


# ──────────────────────────────────────────
# 서비스 리포트 (A4 세로 1페이지)
# ──────────────────────────────────────────
class _Page:
    """위에서 아래로 줄을 쌓는 간단한 텍스트 레이아웃. 지면이 끝나면 더 쓰지 않는다."""

    LINE = {7: 0.0115, 8: 0.013, 9: 0.0145, 10: 0.016, 12: 0.019, 15: 0.024}
    INK, MUTED, HEAD = "#263238", "#607D8B", "#1A237E"

    def __init__(self, ax: plt.Axes, lang: str, top: float = 0.955, bottom: float = 0.085,
                 left: float = 0.045, right: float = 0.955) -> None:
        self.ax, self.lang, self.y = ax, lang, top
        self.bottom, self.left, self.right = bottom, left, right
        self.truncated = False

    # 8pt 라틴 문자 기준으로 본문 폭(0.91 x 8.27in)에 들어가는 글자 수. 한글(CJK)은 글자가
    # 넓으므로 문장의 CJK 비율로 폭을 줄인다. 조치 문구는 --lang en 이어도 한글(단일 소스)이라
    # 언어가 아니라 실제 글자로 판단해야 한다.
    LATIN_WIDTH_8PT = 118
    LATIN_EM, CJK_EM = 0.55, 0.85

    @classmethod
    def wrap_width(cls, text: str, size: int, frac: float = 1.0) -> int:
        """text 를 size pt 로 그릴 때 폭 frac(전체 폭 대비)에 들어가는 글자 수."""
        if not text:
            return 20
        em = sum(cls.CJK_EM if ord(c) > 0x2E80 else cls.LATIN_EM for c in text) / len(text)
        return max(16, int(cls.LATIN_WIDTH_8PT * (8 / size) * frac * cls.LATIN_EM / em))

    def _step(self, size: int) -> float:
        return self.LINE.get(size, 0.0016 * size)

    def fits(self, n_lines: int = 1, size: int = 8) -> bool:
        return self.y - n_lines * self._step(size) >= self.bottom

    def line(self, text: str, size: int = 8, bold: bool = False, color: str | None = None,
             indent: float = 0.0, wrap: bool = True) -> bool:
        """한 항목을 쓴다(필요하면 줄바꿈). 지면이 모자라면 False."""
        width = self.wrap_width(text, size, frac=1.0 - indent / (self.right - self.left))
        lines = textwrap.wrap(text, width=width) if wrap else [text]
        if not lines:
            lines = [""]
        if not self.fits(len(lines), size):
            self.truncated = True
            return False
        for ln in lines:
            self.ax.text(self.left + indent, self.y, ln, fontsize=size, va="top", ha="left",
                         fontweight="bold" if bold else "normal", color=color or self.INK,
                         transform=self.ax.transAxes)
            self.y -= self._step(size)
        return True

    def heading(self, text: str) -> bool:
        self.gap(0.006)
        ok = self.line(text, size=10, bold=True, color=self.HEAD)
        if ok:
            self.ax.plot([self.left, self.right], [self.y + 0.004, self.y + 0.004],
                         color="#B0BEC5", linewidth=0.6, transform=self.ax.transAxes)
            self.gap(0.004)
        return ok

    def gap(self, dy: float) -> None:
        self.y -= dy

    def items(self, items: list[str], size: int = 8, numbered: bool = False, indent: float = 0.012,
              max_items: int | None = None) -> int:
        """목록을 쓰고 실제로 쓴 개수를 돌려준다."""
        written = 0
        for i, s in enumerate(items[:max_items] if max_items else items, 1):
            prefix = f"{i}. " if numbered else "- "
            if not self.line(prefix + s, size=size, indent=indent):
                break
            written += 1
        return written

    def ruled_lines(self, size: int = 9, min_lines: int = 2) -> int:
        """남은 지면을 손으로 적는 빈 줄(가로선)로 채운다. 그은 줄 수를 돌려준다(공간이 min_lines 미만이면 0)."""
        step = self._step(size)
        n = int((self.y - self.bottom) / step)
        if n < min_lines:
            return 0
        for _ in range(n):
            self.y -= step
            self.ax.plot([self.left, self.right], [self.y, self.y], color="#CFD8DC", linewidth=0.5,
                         transform=self.ax.transAxes)
        return n

    def checklist(self, left_title: str, left_items: list[str], right_title: str,
                  right_items: list[str], size: int = 7, max_rows: int | None = None) -> None:
        """두 열 체크박스. 각 열은 반 폭을 쓴다. max_rows 가 None 이면 지면이 허용하는 만큼 전부."""
        if not self.fits(2, 9):
            self.truncated = True
            return
        col_w = (self.right - self.left) / 2
        y0 = self.y
        for k, (title, items) in enumerate(((left_title, left_items), (right_title, right_items))):
            x = self.left + k * col_w
            y = y0
            self.ax.text(x, y, title, fontsize=9, fontweight="bold", va="top", ha="left",
                         color=self.HEAD, transform=self.ax.transAxes)
            y -= self._step(9)
            shown = items if max_rows is None else items[:max_rows]
            for s in shown:
                lines = textwrap.wrap("[ ] " + s, width=self.wrap_width(s, size, frac=0.47)) or [""]
                if y - len(lines) * self._step(size) < self.bottom:
                    self.truncated = True
                    break
                for j, ln in enumerate(lines):
                    self.ax.text(x + (0.014 if j else 0.0), y, ln, fontsize=size, va="top", ha="left",
                                 color=self.INK, transform=self.ax.transAxes)
                    y -= self._step(size)
            if len(items) > len(shown):
                self.ax.text(x, y, f"    (+{len(items) - len(shown)})", fontsize=size, va="top",
                             ha="left", color=self.MUTED, transform=self.ax.transAxes)
                y -= self._step(size)
            self.y = min(self.y, y)


def _severity_text(key: str, lang: str) -> str:
    if lang == "en":
        return SEVERITY_EN.get(key, key)
    return SEVERITY_LABEL.get(key, key)


def build_service_report_page(lot_summary: LotSummary, lang: str = "ko",
                              report_time: str | None = None) -> plt.Figure:
    """로트 하나의 A4 세로 1페이지 서비스 리포트 Figure 를 만든다. 저장은 호출 측이 한다.

    상단 메타(Tool/Chamber 는 빈 양식; 영향 범위·봉쇄 조치 제안·보고 단계·다음 보고 예정은 docs/handoff.md
    초동 보고 항목) -> 현상 -> 분류 결과 -> 의심 원인 순위 -> 권고 조치 -> 후속 확인(SPC 알람 해제 기준)
    -> 고객 측/장비 측 증거 체크박스 -> 남는 지면은 비고 빈 줄. 조치 문구는 ACTION_DETAIL 이 있으면
    그것을, 없으면 ACTIONS 한 줄을 쓴다. 목록은 자르지 않고 지면이 끝나면 '생략' 표시를 남긴다.
    '입력(기대) 패턴·분류 불일치' 는 합성 생성기 전용 정보라 로트 페이지에만 있고 이 양식에는 없다.
    """
    setup_korean_font()
    L = LABELS[lang]
    lot = lot_summary
    report_time = report_time or _now().strftime("%Y-%m-%d %H:%M")
    top = lot.top_pattern
    detail = ACTION_DETAIL.get(top)
    sev_key = detail["severity"] if detail else ""
    sev_text = _severity_text(sev_key, lang) if sev_key else "-"
    # 로트 안에서 같은 패턴이 반복되면 한 단계 올린다(ACTION_DETAIL 의 severity 규칙).
    if detail and lot.pattern_counts[top] >= 2 and sev_key == "monitor" and top != "CLEAN":
        sev_key = "lot_hold"
        sev_text = _severity_text(sev_key, lang) + L["sr_sev_escalated"]
    scope = L["sr_scope"].format(n=lot.n, warn=YIELD_WARN, low=lot.n_low_yield)
    contain = L["sr_contain"].get(sev_key, L["sr_contain"][""])

    fig = plt.figure(figsize=A4_PORTRAIT)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    page = _Page(ax, lang)

    # 제목 + 합성 표시 배너
    ax.text(page.left, page.y, L["sr_title"], fontsize=16, fontweight="bold", va="top", ha="left",
            color=page.HEAD, transform=ax.transAxes)
    ax.text(page.right, page.y, f"{lot.lot_id}", fontsize=11, fontweight="bold", va="top", ha="right",
            color=page.INK, transform=ax.transAxes)
    page.gap(0.030)
    ax.add_patch(plt.Rectangle((page.left, page.y - 0.018), page.right - page.left, 0.022,
                               facecolor="#FFF3E0", edgecolor="#FB8C00", linewidth=0.8,
                               transform=ax.transAxes))
    ax.text(page.left + 0.006, page.y - 0.007, L["sr_banner"], fontsize=7.5, va="center", ha="left",
            color="#E65100", transform=ax.transAxes)
    page.gap(0.030)

    # 메타 표 (2열 x 6행)
    meta = [(k, v.format(lot=lot.lot_id, date=report_time, sev=sev_text, scope=scope, contain=contain,
                         stage=L["sr_stage"])) for k, v in L["sr_meta"]]
    col_w = (page.right - page.left) / 2
    row_h = 0.021
    for i, (k, v) in enumerate(meta):
        r, c = divmod(i, 2)
        x = page.left + c * col_w
        y = page.y - r * row_h
        ax.add_patch(plt.Rectangle((x, y - row_h), col_w, row_h, facecolor="#F5F7F9" if c == 0 else "white",
                                   edgecolor="#CFD8DC", linewidth=0.6, transform=ax.transAxes))
        ax.text(x + 0.005, y - row_h / 2, k, fontsize=7.5, va="center", ha="left", color=page.MUTED,
                transform=ax.transAxes)
        ax.text(x + col_w * 0.46, y - row_h / 2, v if v else "________________",
                fontsize=8 if len(v) <= 28 else 6.5,
                va="center", ha="left", color=page.INK if v else "#B0BEC5", transform=ax.transAxes)
    page.gap(row_h * math.ceil(len(meta) / 2) + 0.006)

    # 1. 현상
    page.heading(L["sr_h_obs"])
    mix = ", ".join(f"{p} {n}" for p, n in lot.pattern_counts.items())
    page.line(L["sr_obs"].format(n=lot.n, mix=mix, avg=lot.avg_yield, mn=lot.min_yield, warn=YIELD_WARN,
                                 low=lot.n_low_yield))

    # 2. 분류 결과
    page.heading(L["sr_h_cls"])
    max_rows = 6
    for w in lot.wafers[:max_rows]:
        page.line(L["sr_cls_row"].format(w=w.wafer_id, p=w.pattern, s=w.score, y=w.yield_pct, f=w.fail_count,
                                         flag=("" if w.matched else L["mismatch"])),
                  indent=0.012, color=None if w.matched else "#C62828")
    if lot.n > max_rows:
        page.line(L["sr_cls_more"].format(n=lot.n - max_rows), indent=0.012, color=page.MUTED)

    # 3. 의심 원인 순위
    page.heading(L["sr_h_cause"].format(p=top))
    if detail:
        if detail.get("rule_out_first"):
            page.line(L["sr_rule_out"].format(s=detail["rule_out_first"]), bold=True, color="#C62828")
        page.items(detail["first_checks"], numbered=True)
        page.line(L["sr_tel"], bold=True, color=page.MUTED)
        page.items(detail["tel_modules"], size=7)
        page.line(L["sr_non_tel"], bold=True, color=page.MUTED)
        page.items(detail["non_tel"], size=7)
    else:
        page.line(L["sr_no_detail"], color=page.MUTED)
        page.line(ACTIONS.get(top, "-"), indent=0.012)

    # 4. 권고 조치
    page.heading(L["sr_h_action"])
    page.line(L["sr_action"].format(sev=sev_text, s=ACTIONS.get(top, "-")), bold=True)
    if detail:
        page.line(L["sr_handoff"].format(s=detail["handoff"]), indent=0.012)

    # 5. 후속 확인
    page.heading(L["sr_h_follow"])
    page.line(L["sr_follow"].format(n=SPC_CLEAR_SUBGROUPS, p=SPC_CLEAR_P))
    if detail:
        page.line(L["sr_follow2"].format(s="; ".join(detail["data_to_collect"])), size=7, indent=0.012)

    # 6. 증거 체크
    page.heading(L["sr_h_evid"])
    if detail:
        page.checklist(L["sr_evid_cust"], detail["customer_evidence"], L["sr_evid_tool"], detail["tool_evidence"])
    else:
        page.checklist(L["sr_evid_cust"], ["-"], L["sr_evid_tool"], ["-"])

    # 7. 비고 - 남는 지면을 손으로 적는 빈 줄로 채운다(현장 기록란). 자리가 없으면 생략.
    if not page.truncated and page.fits(4, 10):
        page.heading(L["sr_h_notes"])
        page.ruled_lines()

    if page.truncated:
        ax.text(page.left, page.bottom + 0.004, L["sr_truncated"].format(p=top), fontsize=6.5, va="bottom",
                ha="left", color="#C62828", transform=ax.transAxes)

    # 서명란 + 각주
    ax.plot([page.left, page.right], [0.072, 0.072], color="#B0BEC5", linewidth=0.6, transform=ax.transAxes)
    ax.text(page.left, 0.060, L["sr_sign"], fontsize=8, va="center", ha="left", color=page.INK,
            transform=ax.transAxes)
    ax.text(page.left, 0.040, "\n".join(textwrap.wrap(L["sr_foot"], width=page.wrap_width(L["sr_foot"], 6.5))),
            fontsize=6.5,
            va="top", ha="left", color=page.MUTED, transform=ax.transAxes)
    return fig


# ──────────────────────────────────────────
def generate_batch_pdf_report(
    lot_configs: list[dict],
    output_path: str | Path | None = None,
    wafers_per_lot: int = 5,
    seed: int = 42,
    lang: str = "ko",
    service_report: str = "flagged",
    anonymize: bool = False,
    salt: bytes | None = None,
    quiet: bool = False,
) -> pd.DataFrame:
    """여러 Lot 의 웨이퍼 맵과 분류 결과를 PDF 로 일괄 생성한다.

    Parameters
    ----------
    lot_configs    : [{"lot_id": str, "defect_mode": str}, ...]  defect_mode 생략 시 무작위(시드 고정)
    output_path    : 저장할 PDF 경로. None 이면 HERE/batch_wafer_report.pdf, 상대 경로면 HERE 기준
    wafers_per_lot : Lot 당 웨이퍼 수
    seed           : 재현성 시드
    lang           : 'ko' | 'en'. 한글 폰트가 없으면 ko 는 en 으로 자동 전환
    service_report : 'all' | 'flagged'(불일치 또는 수율 경고 로트만) | 'none'
    anonymize      : 로트 ID 를 키드 해시로 치환
    salt           : --anonymize 해시 키(bytes). None 이면 실행마다 새로 뽑는다(os.urandom). 같은 salt 면 같은 해시
    quiet          : 콘솔 출력 생략

    생성일시·PDF CreationDate 는 SOURCE_DATE_EPOCH 가 있으면 그 시각(UTC)으로 고정된다(_now 참고).

    Returns
    -------
    pd.DataFrame : 로트별 요약표. attrs["n_pages"], attrs["service_report_lots"], attrs["lang"],
                   attrs["font"] 에 페이지 수·서비스 리포트 로트·실제 언어·폰트를 담는다.
    """
    if service_report not in SERVICE_REPORT_MODES:
        raise ValueError(f"service_report must be one of {SERVICE_REPORT_MODES}: {service_report!r}")
    font = setup_korean_font()                        # 모든 그리기 전에
    lang = resolve_lang(lang, quiet=quiet)
    L = LABELS[lang]
    say = (lambda *a, **k: None) if quiet else print
    say(L["c_font"].format(f=font))

    out = Path(output_path) if output_path is not None else DEFAULT_OUTPUT
    if not out.is_absolute():
        out = HERE / out
    out.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)          # 전역 random 오염 방지 + 재현성
    salt = os.urandom(8) if salt is None else salt
    now = _now()
    report_time = now.strftime("%Y-%m-%d %H:%M")

    all_results: list[WaferResult] = []
    service_lots: set[str] = set()
    with PdfPages(out) as pdf:
        _cover_page(pdf, len(lot_configs), wafers_per_lot, report_time, font is not None, L, anonymize)

        for li, cfg in enumerate(lot_configs):
            lot_id = str(cfg["lot_id"])
            shown = anonymize_lot_id(lot_id, salt) if anonymize else lot_id
            mode = cfg.get("defect_mode") or rng.choice(ALL_MODES)
            res = _lot_page(pdf, shown, mode, wafers_per_lot, seed_base=seed + li * 1000, L=L)
            all_results.extend(res)

            lot = summarize_lots(res)[0]
            msg = L["c_lot"].format(lot=shown, mode=mode, n=lot.n, avg=lot.avg_yield)
            if lot.n_mismatch:
                msg += L["c_mis"].format(n=lot.n_mismatch)
            if wants_service_report(lot, service_report):
                fig = build_service_report_page(lot, lang=lang, report_time=report_time)
                pdf.savefig(fig)
                plt.close(fig)
                service_lots.add(shown)
                msg += L["c_sr"]
            say(msg)

        summary = _summary_page(pdf, all_results, L, service_lots)

        d = pdf.infodict()
        d["Title"] = L["pdf_title"]
        d["Subject"] = (f"{len(lot_configs)} lots / {len(all_results)} wafers; synthetic data "
                        f"(generator and classifier share rules) - not customer or tool data")
        d["Keywords"] = "synthetic data, wafer map, defect pattern, service report, WM-811K-style demo"
        d["Creator"] = "batch_wafer_report.py (wm811k-wafer-analysis)"
        d["CreationDate"] = now

    n_pages = 1 + len(lot_configs) + len(service_lots) + 1
    summary.attrs.update({"n_pages": n_pages, "service_report_lots": sorted(service_lots),
                          "lang": lang, "font": font, "output_path": str(out)})
    say(L["c_saved"].format(p=out, pages=n_pages, lots=len(lot_configs), sr=len(service_lots),
                            wafers=len(all_results)))
    return summary


DEMO_LOTS = [
    {"lot_id": "SEMI2026_LOT_001", "defect_mode": "ring"},
    {"lot_id": "SEMI2026_LOT_002", "defect_mode": "center"},
    {"lot_id": "SEMI2026_LOT_003", "defect_mode": "scratch"},
    {"lot_id": "SEMI2026_LOT_004", "defect_mode": "donut"},
    {"lot_id": "SEMI2026_LOT_005", "defect_mode": "clean"},
    {"lot_id": "SEMI2026_LOT_006"},                      # 무작위 배정
]


def main(argv: list[str] | None = None) -> pd.DataFrame:
    ap = argparse.ArgumentParser(description="합성 로트의 웨이퍼 맵 배치 PDF 리포트 (+ 서비스 리포트 양식)")
    ap.add_argument("--out", default=None, help=f"출력 PDF. 기본 {DEFAULT_OUTPUT.name} (스크립트 옆). 상대 경로는 스크립트 기준")
    ap.add_argument("--lang", choices=list(LABELS), default="ko", help="리포트 언어. 한글 폰트가 없으면 en 으로 자동 전환")
    ap.add_argument("--service-report", choices=SERVICE_REPORT_MODES, default="flagged",
                    help="서비스 리포트 페이지를 붙일 로트: all / flagged(불일치 또는 수율 경고) / none")
    ap.add_argument("--anonymize", action="store_true", help="로트 ID 를 키드 해시로 치환 (매핑 표 미저장)")
    ap.add_argument("--wafers-per-lot", type=positive_int, default=3, help="Lot 당 웨이퍼 수 (1 이상)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)
    # 입력은 항상 합성 데모 로트 6개(DEMO_LOTS)다. 실측 입력 경로는 없으므로 --demo 같은 선택 플래그를 두지 않는다.

    summary = generate_batch_pdf_report(DEMO_LOTS, args.out, wafers_per_lot=args.wafers_per_lot,
                                        seed=args.seed, lang=args.lang, service_report=args.service_report,
                                        anonymize=args.anonymize)
    print()
    print(summary.to_string(index=False))
    return summary


if __name__ == "__main__":
    main()
