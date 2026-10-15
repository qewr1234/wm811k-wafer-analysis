# wm811k_lot_report.py
# 로트 단위 트러블슈팅 리포트 - 패턴 믹스, 방위각·스크래치 모양·슬롯 분포·공통성 판정, 의심 모듈과
# 점검 순서, OCAP 레벨, 8D D2 초안을 A4 1~2페이지 PDF + JSON 으로
#
# 배경
#   장비사 기술지원 엔지니어가 고객에게서 받는 단위는 "웨이퍼 한 장"이 아니라 "이 로트가 이상하다"다.
#   그때 할 일은 정해져 있다(docs/defect_signatures.md 현장 순서): 로트 안에서 같은 패턴이 반복되는가
#   (공정 조건) 한두 장인가(이벤트·핸들링), 반복이면 어느 각도·어느 슬롯에 몰리는가, 스크래치면 직선인가
#   호인가, 이력이 있으면 어느 장비를 같이 지났는가, 그래서 우리 장비(TEL 모듈) 의심인가 타사 인계인가,
#   무엇을 먼저 점검하고 어느 수준으로 에스컬레이션하는가. 이 저장소에는 그 계산이 모듈별로 흩어져
#   있었다(wm811k_azimuth / wm811k_scratch_shape / wm811k_slot / wm811k_commonality / ACTION_DETAIL).
#   이 모듈은 그것들을 로트 하나에 대해 한 번에 호출해 사람이 읽는 리포트로 묶는다.
#
# 무엇을 하나
#   analyze_lot(records_df, preds_df, lot, history=None, notch_deg=-90) -> LotFindings
#       records_df : waferMap, lot, wafer_index (wm811k_azimuth.load_records 출력 또는 같은 열)
#       preds_df   : lot, wafer_index(또는 순서), y_pred, confidence(선택). None 이면 records 의 y_true.
#       history    : 로트 이력 DataFrame(docs/lot_history_schema.md). 있으면 공통성 상위 3개.
#   LotFindings    : 로트 요약(mix, dominant, repeat_verdict), 방위각/스크래치/슬롯 판정, 공통성 상위,
#                    테스트 원인 배제 플래그, 의심 모듈 순위(suspects), OCAP 레벨, 증거 체크리스트,
#                    인계 판정 문장, 8D D2 문제 정의 초안.
#   render_lot_pdf(findings, records_df, out_path, lang='ko', anonymize=False) -> Path
#       1페이지: 헤더(로트·장수·평균 불량률·패턴 믹스 막대·저신뢰 장수·합성 여부) + 라벨 있는 웨이퍼
#                전부 썸네일(슬롯 순, 노치 표시, 라벨·점수) + 로즈 다이어그램(EDGE_LOC/LOC 3장 이상일 때)
#       2페이지: 판정 블록, 테스트 원인 배제, 의심 모듈과 점검 순서, 고객 측/장비 측 증거 체크박스,
#                다음 행동(OCAP 레벨, 8D D2 초안, docs/case_study_8d.md 링크), 노치 기준 각도 가정.
#       썸네일이 한 페이지(36장)를 넘으면 썸네일 페이지가 이어진다(25장 격자를 가정하지 않는다).
#   findings_to_json(findings) -> dict (JSON 직렬화 가능), save_findings_json(findings, path).
#   grid_repeat_score(arr) : 격자 주기 반복(레티클 리피터·프로브 카드 사이트) 의심 휴리스틱.
#
# 판정 규칙 (docstring 에도 있다)
#   repeat_verdict  n < 3 -> insufficient; 지배 패턴 비율 >= 0.5 -> process(공정 조건);
#                   지배 패턴 1~2장 -> event(이벤트·핸들링); 그 외(3장 이상인데 비율 < 0.5) -> mixed.
#   ocap_level      L3 라인 정지 판단: NEAR_FULL 2장 이상(재테스트와 동시에 고객 수율팀과 판단)
#                   L2 로트 홀드·PM 전진: repeat=process 이고 지배 패턴 severity 가 lot_hold 이상
#                   L1 엔지니어 확인: 그 외(이벤트, 장수 부족, monitor 패턴, NEAR_FULL 1장은 재테스트 먼저)
#   suspects        ACTION_DETAIL[지배 패턴] 의 first_checks 를 판정 조합으로 재정렬한다.
#                   EDGE_LOC+fixed_angle -> 챔버 비대칭 요소·EBR 편심 먼저, scattered -> 로봇 센터링·핸들링 먼저
#                   SCRATCH+reproducible_line -> 반송계 먼저, arc 다수 -> CMP(타사) 인계 먼저
#                   LOC+fixed_angle -> 리프트 핀·고정 요소 먼저, 격자 반복 의심 -> 리피터·프로브 카드 배제 먼저
#                   NEAR_FULL -> rule_out_first(재테스트) 를 0순위로
#
# 왜
#   분류 결과가 "다음에 무엇을 보라"로 이어지지 않으면 현장에서 쓸모가 없다. 조치 문구는
#   wafer_pattern_classifier.ACTION_DETAIL 한 곳에서만 가져와 docs 와 어긋나지 않게 한다.
#
# 한계 (중요)
#   - 합성(--demo, tests/)은 로직 확인이지 성능이 아니다. 판정 임계값(0.5, 3장, 0.7 등)은 운용 규칙이지
#     실측으로 최적화한 값이 아니다.
#   - 노치 방향(기본 -90도)은 가정이다(wm811k_azimuth 와 동일). 리포트에 명시한다.
#   - wafer_index 는 물리 슬롯의 '대리 변수'다(wm811k_slot 과 동일). 슬롯 블록은 로트 안 분포만 보여주고,
#     끝 슬롯 검정은 로트 하나로는 못 하므로 wm811k_slot.py 를 전체 예측에 돌리라고 적는다.
#   - 격자 반복 휴리스틱(grid_repeat_score)은 1차원 자기상관의 2차 피크를 보는 것이라 '의심' 표시까지다.
#   - ACTION_DETAIL 의 장비 서술은 공개 자료 기준이며 TEL 내부 구현·PM 주기는 모른다. 고객 데이터·실제
#     장비 식별자는 쓰지 않는다. --anonymize 는 로트명을 키드 해시로 바꾼다(매핑 표 미저장).
#
# 사용법
#   python wm811k_lot_report.py --demo --output lot_demo                      # 합성 로트 3개 -> PDF 3 + JSON 3
#   python wm811k_lot_report.py data/wm811k_defects.pkl --pred test_predictions.csv --lot lot1234 --output out
#   python wm811k_lot_report.py records.pkl --pred p.csv --lot L1 --history h.csv --notch-deg -90 --lang en --anonymize
#   출력: <DIR>/lot_report_<lot>.pdf, <DIR>/lot_report_<lot>.json

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import textwrap
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.colors import to_rgb

from _fonts import has_korean_font, setup_korean_font
from batch_wafer_report import anonymize_lot_id
from wafer_map_visualizer import FAIL_COLOR, PASS_COLOR
from wafer_pattern_classifier import ACTION_DETAIL, SEVERITY_LABEL
from wm811k_azimuth import (
    DEFAULT_NOTCH_DEG, NOTCH_NOTE, load_records, lot_azimuth_summary, plot_azimuth_rose,
    wafer_azimuth_table, wafer_frame,
)
from wm811k_commonality import commonality_table, load_lot_history, lot_pattern_status
from wm811k_scratch_shape import lot_scratch_summary, wafer_scratch_table
from wm811k_slot import DEFAULT_END_SLOTS, SLOT_NOTE, slot_rate_table

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
A4_PORTRAIT = (8.27, 11.69)
LOW_CONF = 0.7                    # wm811k_spc 의 저신뢰 기준과 같다
MIN_N_REPEAT = 3                  # 로트 판정에 필요한 최소 장수
PROCESS_FRAC = 0.5                # 지배 패턴 비율이 이 이상이면 '공정 조건'
EVENT_MAX = 2                     # 지배 패턴이 이 장수 이하면 '이벤트'
MIN_N_ROSE = 3                    # 로즈 다이어그램을 그리는 EDGE_LOC/LOC 최소 장수
THUMBS_PER_PAGE = 36
GRID_REPEAT_MIN_CORR = 0.3        # 2차 피크 자기상관 하한 (두 축 모두)
GRID_REPEAT_MIN_RISE = 0.25       # 2차 피크 - 그 앞 최소값 (두 축 모두)
AZIMUTH_CLASSES = ("EDGE_LOC", "LOC")
DEFECT_ORDER = ("NEAR_FULL", "EDGE_RING", "EDGE_LOC", "CENTER", "DONUT", "SCRATCH", "LOC", "RANDOM", "CLEAN")
CASE_STUDY_LINK = "docs/case_study_8d.md"

OCAP_LEVELS: dict[str, dict[str, str]] = {
    "L1": {"ko": "L1 엔지니어 확인", "en": "L1 engineer check"},
    "L2": {"ko": "L2 로트 홀드·PM 전진", "en": "L2 lot hold / pull PM forward"},
    "L3": {"ko": "L3 라인 정지 판단", "en": "L3 line-stop decision"},
}
REPEAT_TEXT = {
    "process": {"ko": "공정 조건(로트 안 반복)", "en": "process condition (repeats in lot)"},
    "event": {"ko": "이벤트·핸들링(1~2장)", "en": "event / handling (1-2 wafers)"},
    "mixed": {"ko": "혼합(지배 패턴 3장 이상이나 과반 미만)", "en": "mixed (dominant >= 3 wafers but < 50%)"},
    "insufficient": {"ko": "장수 부족(3장 미만)", "en": "insufficient (< 3 wafers)"},
}

# 문구 사전. 전부 cp949 로 인코딩 가능해야 한다(tests/test_lot_report.py 가 검사).
LABELS: dict[str, dict[str, str]] = {
    "ko": {
        "title": "로트 트러블슈팅 리포트 / Lot Troubleshooting Report",
        "banner_syn": "합성 데이터 - 로직 확인용 / SYNTHETIC DATA - logic check only. 실제 장비·고객 데이터가 아니다.",
        "banner_real": "분류 결과는 입력 예측(y_pred)을 그대로 믿는다. 오분류는 걸러지지 않는다.",
        "hdr_n": "웨이퍼 {n}장 (라벨 있는 것 전부)",
        "hdr_ff": "평균 불량률 {ff:.1%}  (최저 {lo:.1%} / 최고 {hi:.1%})",
        "hdr_dom": "지배 패턴 {p} {k}/{n} -> {rep}",
        "hdr_low": "저신뢰(confidence < {t:g}) {k}장",
        "hdr_low_none": "confidence 열 없음 - 저신뢰 집계 생략",
        "hdr_anon": "로트명 키드 해시 익명화 (매핑 표 미저장)",
        "mix_title": "패턴 믹스",
        "thumb_title": "웨이퍼 썸네일 (슬롯 순, 노치 = 회색 삼각형, 가정 notch_deg={notch:g})",
        "thumb_more": "(썸네일 {a}~{b}장, 다음 페이지에 계속)",
        "rose_title": "{p} 방위각 (노치 0도)",
        "rose_note": "최대 성분 무게중심의 노치 기준 방위각. 같은 로트 안 상대 각도는 노치 가정과 무관.",
        "h_verdict": "1. 판정 / Verdict",
        "v_repeat": "로트 내 반복: {rep}  (지배 패턴 {p} {k}/{n}, 기준: 비율 >= {f:g} 이면 공정, 1~2장이면 이벤트, 3장 미만이면 보류)",
        "v_az": "방위각({cls}, n={n}): r_bar={r:.2f}, 평균각 {m:.0f}도, p={p:.3g} -> {v}  [{read}]",
        "v_az_read": {"fixed_angle": "챔버/스테이션 고정 요소 의심", "scattered": "핸들링·이벤트 쪽", "insufficient": "장수 부족"},
        "v_sc": "스크래치 모양(n={n}): 직선 {l} / 호 {a} / 애매 {m} / 짧음 {s}, 축 집중도 {c} -> {v}  [{read}]",
        "v_sc_read": {"reproducible_line": "노치 기준 같은 방향 직선 반복 - 고정 접촉점(반송계) 의심",
                      "random": "모양·방향 제각각 - 산발 입자·CMP(타사) 쪽", "insufficient": "장수 부족"},
        "v_slot": "슬롯 분포({p}): 슬롯 {lo}-{hi} 중 발생 {hits} / 발생률 끝(1-3,23-25) {re} vs 가운데 {rm} -> {conc} / 최장 연속 {run}",
        "slot_conc": "끝 슬롯 집중", "slot_noconc": "끝 슬롯 집중 아님",
        "v_slot_note": "wafer_index 는 슬롯 대리 변수. 끝 슬롯 검정은 로트 하나로 못 한다 - python wm811k_slot.py <예측> --pattern {p}",
        "v_cm": "공통성 상위(이력 기준, 패턴 {p}, 로트 {nl}개 중 양성 {nb}개):",
        "v_cm_row": "{i}. {unit}: 양성 {a}/{n1} ({r:.2f}) vs 나머지 {ro:.2f}, 비 {rr:.2f}, q={q:.2g}{pass_}",
        "v_cm_pass": "  <- 이 로트 통과", "v_cm_nopass": "",
        "v_cm_note": "공통성은 상관이지 인과가 아니다. q >= 0.05 면 지목 근거가 약하다 - 지목 장비의 PM·부품 이력과 시점을 맞댄다.",
        "v_cm_none": "공통성: 이력 없음 (--history 로 docs/lot_history_schema.md 형식 CSV 를 주면 상위 3개 장비를 낸다)",
        "h_excl": "2. 테스트 원인 배제 / Rule out test causes first",
        "excl_none": "해당 플래그 없음 (NEAR_FULL 없음, 격자 반복 의심 없음).",
        "h_susp": "3. 의심 모듈과 점검 순서 / Suspected modules, check order   - {p} x {combo}",
        "susp_row": "{i}. [{mod}] {chk}",
        "susp_basis": "      근거: {b}",
        "h_evid": "4. 증거 체크 / Evidence checklist",
        "evid_cust": "고객 측 / Customer-side", "evid_tool": "장비 측 / Tool-side",
        "h_next": "5. 다음 행동 / Next action",
        "next_ocap": "OCAP 레벨: {lvl}  - {why}",
        "next_d2": "8D D2 문제 정의 초안: {d2}",
        "next_handoff": "인계 판정 기준: {s}",
        "next_link": "미해결 시 8D 로: {link} (D3 봉쇄 = 로트 홀드·재테스트·챔버 격리, D4 = 위 의심 모듈 순서로 배제)",
        "foot": ("{notch}. 조치 문구는 wafer_pattern_classifier.ACTION_DETAIL(docs/defect_signatures.md 와 동일 소스). "
                 "공개 자료 수준의 서술이며 TEL 내부 구현·매뉴얼 PM 주기는 모른다. 생성 {t}, wm811k_lot_report.py"),
        "pdf_title": "Lot troubleshooting report {lot}{syn}",
        "c_saved": "저장: {pdf}, {js}",
        "c_demo": "[demo] 합성 로트 3개: {lots}. 로직 확인이지 성능이 아니다.",
        "c_font_none": "[경고] 한글 폰트를 찾지 못해 리포트 언어를 en 으로 전환한다.",
    },
    "en": {
        "title": "Lot Troubleshooting Report",
        "banner_syn": "SYNTHETIC DATA - logic check only. Not real tool or customer data.",
        "banner_real": "Classification is taken from the input predictions (y_pred) as-is; misclassification is not filtered.",
        "hdr_n": "{n} wafers (all labeled wafers in the lot)",
        "hdr_ff": "mean fail fraction {ff:.1%}  (min {lo:.1%} / max {hi:.1%})",
        "hdr_dom": "dominant pattern {p} {k}/{n} -> {rep}",
        "hdr_low": "low confidence (< {t:g}): {k} wafers",
        "hdr_low_none": "no confidence column - low-confidence count skipped",
        "hdr_anon": "lot name anonymized with a keyed hash (mapping not stored)",
        "mix_title": "pattern mix",
        "thumb_title": "wafer thumbnails (slot order, notch = grey triangle, assumed notch_deg={notch:g})",
        "thumb_more": "(thumbnails {a}-{b}, continued on next page)",
        "rose_title": "{p} azimuth (notch = 0 deg)",
        "rose_note": "Azimuth of the largest component centroid, notch reference. Relative angles within a lot do not depend on the notch assumption.",
        "h_verdict": "1. Verdict",
        "v_repeat": "repeat in lot: {rep}  (dominant {p} {k}/{n}; rule: fraction >= {f:g} -> process, 1-2 wafers -> event, < 3 wafers -> insufficient)",
        "v_az": "azimuth ({cls}, n={n}): r_bar={r:.2f}, mean {m:.0f} deg, p={p:.3g} -> {v}  [{read}]",
        "v_az_read": {"fixed_angle": "fixed element of chamber/station suspected", "scattered": "handling / event side", "insufficient": "too few wafers"},
        "v_sc": "scratch shape (n={n}): line {l} / arc {a} / ambiguous {m} / short {s}, axial consistency {c} -> {v}  [{read}]",
        "v_sc_read": {"reproducible_line": "same-direction lines repeat (notch ref) - fixed contact point (transfer system) suspected",
                      "random": "shape/direction vary - sporadic particles / CMP (non-TEL) side", "insufficient": "too few wafers"},
        "v_slot": "slot distribution ({p}): hits {hits} in slots {lo}-{hi} / rate end (1-3,23-25) {re} vs mid {rm} -> {conc} / longest run {run}",
        "slot_conc": "end-slot concentration", "slot_noconc": "no end-slot concentration",
        "v_slot_note": "wafer_index is a slot proxy. End-slot test needs all lots: python wm811k_slot.py <preds> --pattern {p}",
        "v_cm": "tool commonality (history, pattern {p}, {nb} positive of {nl} lots):",
        "v_cm_row": "{i}. {unit}: positive {a}/{n1} ({r:.2f}) vs rest {ro:.2f}, ratio {rr:.2f}, q={q:.2g}{pass_}",
        "v_cm_pass": "  <- this lot passed through", "v_cm_nopass": "",
        "v_cm_note": "Commonality is correlation, not cause. q >= 0.05 means weak evidence - match the unit's PM / part history and timing.",
        "v_cm_none": "commonality: no lot history (pass --history CSV in docs/lot_history_schema.md format for top-3 tools)",
        "h_excl": "2. Rule out test causes first",
        "excl_none": "No flag (no NEAR_FULL, no grid-repeat suspicion).",
        "h_susp": "3. Suspected modules and check order   - {p} x {combo}",
        "susp_row": "{i}. [{mod}] {chk}",
        "susp_basis": "      basis: {b}",
        "h_evid": "4. Evidence checklist",
        "evid_cust": "Customer-side", "evid_tool": "Tool-side",
        "h_next": "5. Next action",
        "next_ocap": "OCAP level: {lvl}  - {why}",
        "next_d2": "8D D2 problem statement draft: {d2}",
        "next_handoff": "Hand-off rule: {s}",
        "next_link": "If unresolved, go to 8D: {link} (D3 containment = lot hold, retest, chamber isolation; D4 = rule out in the order above)",
        "foot": ("{notch}. Action text from wafer_pattern_classifier.ACTION_DETAIL (same source as docs/defect_signatures.md; "
                 "Korean item text kept as-is, single source). Public-source level only; TEL internals and manual PM intervals unknown. "
                 "Generated {t}, wm811k_lot_report.py"),
        "pdf_title": "Lot troubleshooting report {lot}{syn}",
        "c_saved": "saved: {pdf}, {js}",
        "c_demo": "[demo] 3 synthetic lots: {lots}. Logic check, not performance.",
        "c_font_none": "[warning] Korean font not found - switching report language to en.",
    },
}
SEVERITY_EN = {"monitor": "monitor", "lot_hold": "lot hold review", "line_stop_review": "line stop review"}


# ──────────────────────────────────────────
# 1. 데이터 구조
# ──────────────────────────────────────────
@dataclass
class LotFindings:
    """로트 하나의 판정 결과. findings_to_json 으로 그대로 직렬화된다.

    repeat_verdict  'process' | 'event' | 'mixed' | 'insufficient' (머리 주석의 규칙)
    azimuth         EDGE_LOC/LOC 가 1장 이상이면 lot_azimuth_summary 한 행 + 웨이퍼별 theta, 아니면 None
    scratch         SCRATCH 가 1장 이상이면 lot_scratch_summary 한 행 + 웨이퍼별 shape, 아니면 None
    slot            로트 안 슬롯 분포만(검정 아님). wafer_index 가 전부 결측이면 None
    commonality_top 이력이 있을 때 evidence ok 상위 3개(없으면 빈 리스트)
    suspects        [{rank, module, check, basis, source}] - ACTION_DETAIL 에서 판정 조합으로 재정렬
    ocap_level      'L1' | 'L2' | 'L3' (OCAP_LEVELS 에 표시 문구), ocap_reason 에 이유
    evidence        {'customer': [...], 'tool': [...]} (ACTION_DETAIL 의 체크리스트)
    """
    lot: str
    n: int
    mix: dict[str, int]
    dominant: str
    dominant_count: int
    dominant_frac: float
    repeat_verdict: str
    mean_fail_frac: float
    min_fail_frac: float
    max_fail_frac: float
    n_low_conf: int | None
    azimuth: dict | None
    scratch: dict | None
    slot: dict | None
    commonality_top: list[dict]
    test_exclusion_flags: list[str]
    suspects: list[dict]
    ocap_level: str
    ocap_reason: dict[str, str]
    evidence: dict[str, list[str]]
    handoff: str
    d2_draft: str
    notch_deg: float
    synthetic: bool
    wafers: list[dict] = field(default_factory=list)
    label_source: str = "y_pred"


# ──────────────────────────────────────────
# 2. 보조 계산
# ──────────────────────────────────────────
def fail_fraction(arr: np.ndarray) -> float:
    """다이 중 불량 비율. 다이가 없으면 NaN."""
    a = np.asarray(arr)
    n_die = int((a > 0).sum())
    return float((a == 2).sum() / n_die) if n_die else float("nan")


def _autocorr_1d(fail: np.ndarray, die: np.ndarray, axis: int) -> np.ndarray:
    """다이 영역 안에서 lag k = 1..L//2 의 피어슨 자기상관. 겹치는 다이가 20 미만이면 NaN."""
    m = np.moveaxis(fail, axis, 1)
    d = np.moveaxis(die, axis, 1)
    L = m.shape[1]
    out = []
    for k in range(1, L // 2 + 1):
        both = d[:, :-k] & d[:, k:]
        if both.sum() < 20:
            out.append(np.nan)
            continue
        u, v = m[:, :-k][both], m[:, k:][both]
        out.append(0.0 if (u.std() < 1e-9 or v.std() < 1e-9) else float(np.corrcoef(u, v)[0, 1]))
    return np.asarray(out, dtype=float)


def grid_repeat_score(arr: np.ndarray, min_lag: int = 3) -> dict:
    """격자 주기 반복(레티클 리피터·프로브 카드 사이트) 의심 휴리스틱.

    불량 지시자의 행 방향(x)·열 방향(y) 1차원 자기상관 corr[k] (k = 1..min(h,w)//2) 를 구하고, 덩어리·링처럼
    단조 감쇠하는 패턴과 달리 어떤 피치 k 에서 다시 오르는 '2차 피크'를 축마다 찾는다.
      rise = corr[k] - min(corr[1..k-1]),  k >= min_lag
    suspect = 두 축 모두에서 corr[k] >= GRID_REPEAT_MIN_CORR(0.3) 이고 rise >= GRID_REPEAT_MIN_RISE(0.25).
    한 축만 보면 호(弧)·고리의 현(chord) 길이에서도 2차 피크가 생겨 오탐이 난다(합성 40장 x 8패턴, 임계 0.2/0.15
    에서 donut 11/40, edge_loc 2/40). 두 축을 모두 요구하고 임계를 0.3/0.25 로 두면 합성 320장(8패턴 x 40)에서
    오탐 0, 피치 4~8 다이·노이즈 5%·맵 크기 5종의 심은 격자 80장은 전부 잡혔다(합성 기준 로직 확인이지 실측
    성능이 아니다). 그래도 '의심' 표시까지다 - 리피터 분석은 고객 측 도구로 한다.
    반환 dict(score=두 축 rise 의 최소, lag_x, lag_y, corr_x, corr_y, suspect). 불량이 없거나 맵이 작으면 False.
    lag 은 그 축에서 rise 가 최대의 80% 이상인 피치 중 가장 작은 것(기본 주기; 2배·3배 고조파가 아니라).
    """
    a = np.asarray(arr)
    die = a > 0
    fail = (a == 2).astype(float)
    out = {"score": 0.0, "lag_x": 0, "lag_y": 0, "corr_x": 0.0, "corr_y": 0.0, "suspect": False}
    if int(fail.sum()) == 0 or min(a.shape) < 2 * min_lag + 2:
        return out
    ok = True
    rises = []
    for axis, name in ((1, "x"), (0, "y")):
        c = _autocorr_1d(fail, die, axis)
        cand: list[tuple[int, float, float]] = []            # (k, rise, corr)
        for k in range(min_lag, len(c) + 1):
            if not np.isfinite(c[k - 1]):
                continue
            prev = c[: k - 1]
            prev = prev[np.isfinite(prev)]
            if len(prev) == 0:
                continue
            cand.append((k, float(c[k - 1] - prev.min()), float(c[k - 1])))
        best_rise = max((r for _, r, _ in cand), default=0.0)
        best_k, best_c = 0, 0.0
        for k, r, cc in cand:                                 # 기본 주기: 최대 rise 의 80% 이상인 가장 작은 lag
            if best_rise > 0 and r >= 0.8 * best_rise:
                best_k, best_c = k, cc
                break
        out[f"lag_{name}"], out[f"corr_{name}"] = int(best_k), best_c
        rises.append(best_rise)
        ok &= best_c >= GRID_REPEAT_MIN_CORR and best_rise >= GRID_REPEAT_MIN_RISE
    out["score"] = float(min(rises))
    out["suspect"] = bool(ok)
    return out


def _longest_run(slots: list[int]) -> int:
    """정렬된 슬롯 번호 리스트에서 연속 슬롯의 최장 길이."""
    if not slots:
        return 0
    s = sorted(set(int(x) for x in slots))
    best = run = 1
    for a, b in zip(s, s[1:]):
        run = run + 1 if b == a + 1 else 1
        best = max(best, run)
    return best


def _lot_frame(records_df: pd.DataFrame, preds_df: pd.DataFrame | None, lot: str) -> tuple[pd.DataFrame, str]:
    """로트 하나의 (waferMap, lot, wafer_index, y_pred, confidence) 표와 라벨 출처.

    preds_df 가 있으면 (lot, wafer_index) 키로, 양쪽에 wafer_index 가 없으면 행 순서로 결합한다.
    preds_df 가 None 이면 records 의 y_pred 또는 y_true 를 쓴다. 라벨 없는 웨이퍼는 제외한다.
    """
    rec = records_df[records_df["lot"].astype(str) == str(lot)].copy()
    if len(rec) == 0:
        raise ValueError(f"records 에 로트 {lot!r} 이 없다.")
    if "wafer_index" not in rec.columns:
        rec["wafer_index"] = np.nan
    rec["wafer_index"] = pd.to_numeric(rec["wafer_index"], errors="coerce")
    rec = rec.reset_index(drop=True)
    if preds_df is not None:
        if "y_pred" not in preds_df.columns or "lot" not in preds_df.columns:
            raise ValueError("preds_df 에 lot, y_pred 열이 필요하다.")
        p = preds_df[preds_df["lot"].astype(str) == str(lot)].copy()
        keep = [c for c in ("y_pred", "confidence") if c in p.columns]
        if "wafer_index" in p.columns and rec["wafer_index"].notna().all():
            p["wafer_index"] = pd.to_numeric(p["wafer_index"], errors="coerce")
            p = p.drop_duplicates(["wafer_index"])
            rec = rec.drop(columns=[c for c in keep if c in rec.columns], errors="ignore")
            rec = rec.merge(p[["wafer_index"] + keep], on="wafer_index", how="left")
        elif len(p) == len(rec):
            for c in keep:
                rec[c] = p[c].to_numpy()
        else:
            raise ValueError(f"로트 {lot!r}: 예측을 결합할 수 없다 (wafer_index 가 없고 행 수도 다르다: "
                             f"{len(p)} vs {len(rec)}).")
        src = "y_pred"
    elif "y_pred" in rec.columns:
        src = "y_pred"
    elif "y_true" in rec.columns:
        rec["y_pred"] = rec["y_true"]
        src = "y_true"
    else:
        raise ValueError("preds_df 가 없으면 records 에 y_pred 또는 y_true 열이 필요하다.")
    if "confidence" not in rec.columns:
        rec["confidence"] = np.nan
    rec = rec[rec["y_pred"].notna()].copy()
    rec["y_pred"] = rec["y_pred"].astype(str)
    rec["confidence"] = pd.to_numeric(rec["confidence"], errors="coerce")
    if rec["wafer_index"].notna().any():
        rec = rec.sort_values("wafer_index", kind="stable", na_position="last")
    rec = rec.reset_index(drop=True)
    if len(rec) == 0:
        raise ValueError(f"로트 {lot!r} 에 라벨 있는 웨이퍼가 없다.")
    return rec, src


def repeat_verdict(n: int, dominant_count: int) -> str:
    """n < 3 -> insufficient; 비율 >= PROCESS_FRAC -> process; 지배 1~2장 -> event; 그 외 mixed."""
    if n < MIN_N_REPEAT:
        return "insufficient"
    if dominant_count / n >= PROCESS_FRAC:
        return "process"
    if dominant_count <= EVENT_MAX:
        return "event"
    return "mixed"


def ocap_level(dominant: str, repeat: str, mix: dict[str, int]) -> tuple[str, dict[str, str]]:
    """OCAP 레벨과 이유(ko/en).

    L3 라인 정지 판단 : NEAR_FULL 2장 이상 - 재테스트로 테스트 원인을 배제하는 동시에 고객 수율팀과 판단
    L2 로트 홀드·PM 전진: repeat == process 이고 지배 패턴 severity 가 lot_hold / line_stop_review
    L1 엔지니어 확인   : 그 외 (이벤트, 장수 부족, mixed, monitor 패턴, NEAR_FULL 1장은 재테스트 먼저)
    """
    n_nf = int(mix.get("NEAR_FULL", 0))
    sev = ACTION_DETAIL.get(dominant, {}).get("severity", "monitor")
    if n_nf >= 2:
        return "L3", {"ko": f"NEAR_FULL {n_nf}장 - 재테스트와 동시에 라인 정지·로트 홀드를 고객 수율팀과 판단(초동 보고)",
                      "en": f"NEAR_FULL x{n_nf} - retest and decide line stop / lot hold with the customer yield team (initial report)"}
    if repeat == "process" and sev in ("lot_hold", "line_stop_review"):
        return "L2", {"ko": f"{dominant} 가 로트 안 반복(공정 조건)이고 severity={sev} - 로트 홀드 검토, 해당 모듈 PM·부품 점검 전진",
                      "en": f"{dominant} repeats in lot (process condition), severity={sev} - review lot hold, pull PM / part check forward"}
    if n_nf == 1:
        return "L1", {"ko": "NEAR_FULL 1장 - 재테스트가 가장 싸다. 재테스트 결과 전에는 장비 조치 보류",
                      "en": "single NEAR_FULL - retest is cheapest; hold tool action until retest result"}
    why = {"process": {"ko": f"{dominant} 반복이지만 severity={sev} - 관리도(wm811k_spc.py)로 추세 감시",
                       "en": f"{dominant} repeats but severity={sev} - watch the trend on the control chart (wm811k_spc.py)"},
           "event": {"ko": "1~2장 이벤트 - 해당 웨이퍼 핸들링·반송 이력 확인, 재발 시 상향",
                     "en": "1-2 wafer event - check handling / transfer history of those wafers, escalate on recurrence"},
           "mixed": {"ko": "패턴 혼합 - 웨이퍼별 판정을 사람이 확인하고 패턴별로 나눠 다시 본다",
                     "en": "mixed patterns - review per-wafer calls by hand and split by pattern"},
           "insufficient": {"ko": "3장 미만 - 판정 보류, 같은 로트 다른 웨이퍼 맵 요청",
                            "en": "fewer than 3 wafers - hold the verdict, request the rest of the lot"}}
    return "L1", why.get(repeat, why["insufficient"])


def _find_checks(pattern: str, keywords: list[str]) -> list[tuple[int, str]]:
    """ACTION_DETAIL[pattern].first_checks 에서 키워드를 포함하는 항목을 (index, text) 로. 키워드 순서대로."""
    checks = ACTION_DETAIL.get(pattern, {}).get("first_checks", [])
    out: list[tuple[int, str]] = []
    for kw in keywords:
        for i, c in enumerate(checks):
            if kw in c and all(i != j for j, _ in out):
                out.append((i, c))
                break
    return out


def _module_of(check: str) -> str:
    """점검 문구 앞의 모듈 라벨(':' 앞)을 뽑는다. 없으면 '공통'."""
    head = check.split(":")[0]
    if len(head) <= 40 and ("TEL" in head or "/" in head or "Tactras" in head or "CLEAN TRACK" in head
                            or "Triase" in head or "CELLESTA" in head or "EXPEDIUS" in head or "Precio" in head
                            or "VHF" in head or "모든" in head or "프로브" in head or "CMP" in head):
        return head.strip()
    return "common"


def rank_suspects(dominant: str, repeat: str, az_verdict: str | None, sc_verdict: str | None,
                  sc_shapes: dict[str, int] | None, slot_end_concentrated: bool, grid_suspect: bool,
                  mix: dict[str, int]) -> list[dict]:
    """ACTION_DETAIL[dominant] 의 first_checks 를 판정 조합으로 재정렬한 의심 모듈 순위.

    반환 [{rank, module, check, basis, source}]. module 은 점검 문구 앞의 모듈 라벨(없으면 'common'),
    check 는 그 라벨을 뗀 본문. source 는 'rule_out_first' 또는 'first_checks[i]'.
    조합 규칙은 머리 주석. 키워드로 항목을 고르므로 ACTION_DETAIL 문구가 바뀌면 순서만 기본값으로 돌아간다.
    """
    d = ACTION_DETAIL.get(dominant)
    if not d:
        return []
    picked: list[tuple[int, str, str]] = []        # (index, text, basis)
    basis_default = "ACTION_DETAIL 기본 순서 (default order)"

    def add(items: list[tuple[int, str]], basis: str) -> None:
        for i, c in items:
            if all(i != j for j, _, _ in picked):
                picked.append((i, c, basis))

    if dominant == "EDGE_LOC":
        if az_verdict == "fixed_angle":
            add(_find_checks(dominant, ["챔버 비대칭", "EBR 편심"]), "방위각 fixed_angle: 로트 안 같은 각도 -> 챔버/스테이션 고정 요소")
            add(_find_checks(dominant, ["반송 로봇 센터링"]), "고정 요소가 아니면 티칭 오프셋(같은 각도 재현 가능)")
        elif az_verdict == "scattered":
            add(_find_checks(dominant, ["반송 로봇 센터링", "엣지 치핑"]), "방위각 scattered: 각도 제각각 -> 핸들링·이벤트")
            add(_find_checks(dominant, ["EBR 편심"]), "코터 척 센터링도 웨이퍼마다 다를 수 있다")
    elif dominant == "SCRATCH":
        n_line = (sc_shapes or {}).get("line", 0)
        n_arc = (sc_shapes or {}).get("arc", 0)
        if sc_verdict == "reproducible_line":
            add(_find_checks(dominant, ["반송계"]), "직선이 노치 기준 같은 방향으로 반복 -> 고정 접촉점(TEL 공통 반송계)")
            add(_find_checks(dominant, ["CLEAN TRACK"]), "트랙 노즐 계열 선형 결함도 로트 안 재현된다")
        elif n_arc > n_line and n_arc > 0:
            add(_find_checks(dominant, ["CMP 슬러리"]), f"호 모양 {n_arc}장 > 직선 {n_line}장 -> CMP(타사) 인계 후보(경험칙)")
            add(_find_checks(dominant, ["호인지 직선인지"]), "로트 내 재현 여부로 재확인")
        else:
            add(_find_checks(dominant, ["호인지 직선인지", "반송계"]), "모양·방향 제각각 또는 장수 부족 -> 모양 판별과 반송계 확인부터")
    elif dominant == "LOC":
        if grid_suspect:
            add([(-1, d["rule_out_first"])], "격자 주기 반복 의심(grid_repeat_score) -> 리피터·프로브 카드 사이트 먼저 배제")
        if az_verdict == "fixed_angle":
            add(_find_checks(dominant, ["리프트 핀", "같은가"]), "방위각 fixed_angle: 같은 위치 반복 -> 리프트 핀·챔버 고정 요소")
        elif az_verdict == "scattered":
            add(_find_checks(dominant, ["파티클 샤워", "뒷면 파티클"]), "방위각 scattered: 위치 제각각 -> 파티클 이벤트")
    elif dominant == "NEAR_FULL":
        add([(-1, d["rule_out_first"])], "전면 불량은 테스트 원인(프로브 카드·프로그램)부터 배제 - 재테스트가 가장 싸다")
        if int(mix.get("NEAR_FULL", 0)) >= 2:
            add(_find_checks(dominant, ["로트 이력에서 비정상 종료"]), "2장 이상이면 공정 사고 쪽 - 장비 알람·이벤트 로그와 대조")
    elif dominant == "EDGE_RING" and slot_end_concentrated:
        add(_find_checks(dominant, ["퍼니스"]), "로트 안 끝 슬롯 집중(발생률 가운데의 2배 이상) -> 배치 퍼니스 보트 양끝 조건(일반 물리)")

    if repeat == "event" and dominant not in ("NEAR_FULL", "CLEAN"):
        add(_find_checks(dominant, ["반송", "핸들링", "엣지 치핑", "이벤트"]), "1~2장 이벤트 -> 핸들링·단일 웨이퍼 이벤트 쪽")

    for i, c in enumerate(d["first_checks"]):
        if all(i != j for j, _, _ in picked):
            picked.append((i, c, basis_default))
    out = []
    for r, (i, c, b) in enumerate(picked, 1):
        mod = _module_of(c)
        body = c.split(":", 1)[1].strip() if mod != "common" else c
        out.append({"rank": r, "module": mod, "check": body, "basis": b,
                    "source": "rule_out_first" if i < 0 else f"first_checks[{i}]"})
    return out


def exclusion_flags(mix: dict[str, int], grid: list[dict], n: int) -> list[str]:
    """테스트 원인 배제 플래그 문구. NEAR_FULL 1장 -> '재테스트 먼저', 2장 이상 -> 재테스트 + 공정 사고 확인,
    격자 반복 의심 웨이퍼 -> 리피터·프로브 카드 사이트 배제 문구."""
    flags: list[str] = []
    n_nf = int(mix.get("NEAR_FULL", 0))
    if n_nf == 1:
        flags.append("NEAR_FULL 1장: 재테스트 먼저 - 프로브 카드 접촉·테스트 프로그램 리밋·웨이퍼 ID 혼동을 배제하기 전에는 "
                      "장비 조치를 하지 않는다 (Precio / Prexa 프로버면 카드 클리닝·터치다운 카운터 확인)")
    elif n_nf >= 2:
        flags.append(f"NEAR_FULL {n_nf}장/{n}: 재테스트로 테스트 원인 배제 + 로트 이력에서 비정상 종료 공정·장비 알람 로그 대조 "
                     "(2장 이상이면 공정 사고 쪽 비중이 커진다)")
    sus = [g for g in grid if g.get("suspect")]
    if sus:
        w = ", ".join((f"w{g['wafer_index']}" if g.get("wafer_index") is not None else "w?")
                      + f"(pitch x{g['lag_x']}/y{g['lag_y']})" for g in sus[:6])
        more = f" 외 {len(sus) - 6}장" if len(sus) > 6 else ""
        flags.append(f"격자 주기 반복 의심 {len(sus)}장: {w}{more} - 두 축 자기상관 2차 피크(휴리스틱, 확정 아님). "
                     "레티클 리피터(타사 노광) 또는 프로브 카드 사이트 불량 - 리피터 분석·재테스트로 먼저 배제")
    return flags


def make_d2_draft(lot: str, n: int, dominant: str, k: int, repeat: str, ff: float, az: dict | None,
                  sc: dict | None, notch_deg: float, synthetic: bool, lang: str = "ko") -> str:
    """8D D2 문제 정의 초안 한 단락. 사실(수치)만 적고 원인은 적지 않는다."""
    rep = REPEAT_TEXT.get(repeat, REPEAT_TEXT["insufficient"])[lang]
    if lang == "ko":
        s = (f"로트 {lot} 웨이퍼 {n}장 중 {dominant} {k}장({k / n:.0%}), 평균 불량률 {ff:.1%}. 로트 내 반복 판정: {rep}.")
        if az:
            s += (f" 방위각(노치 기준, 가정 notch_deg={notch_deg:g}): n={az['n']}, 평균 {az['mean_deg']:.0f}도, "
                  f"r_bar={az['r_bar']:.2f}, 판정 {az['verdict']}.")
        if sc:
            s += f" 스크래치 모양: 직선 {sc['n_line']}/호 {sc['n_arc']}, 판정 {sc['verdict']}."
        s += " 영향 범위(다른 로트·시각)와 손실 다이 수는 고객 수율 집계로 확정한다. 원인은 D4 에서 다룬다."
        if synthetic:
            s += " [합성 데이터]"
    else:
        s = (f"Lot {lot}: {k} of {n} wafers {dominant} ({k / n:.0%}), mean fail fraction {ff:.1%}. Repeat verdict: {rep}.")
        if az:
            s += (f" Azimuth (notch ref, assumed notch_deg={notch_deg:g}): n={az['n']}, mean {az['mean_deg']:.0f} deg, "
                  f"r_bar={az['r_bar']:.2f}, verdict {az['verdict']}.")
        if sc:
            s += f" Scratch shape: line {sc['n_line']} / arc {sc['n_arc']}, verdict {sc['verdict']}."
        s += " Scope (other lots, time window) and lost dies to be confirmed from the customer yield data. Cause is D4."
        if synthetic:
            s += " [synthetic data]"
    return s


# ──────────────────────────────────────────
# 3. 로트 분석
# ──────────────────────────────────────────
def analyze_lot(records_df: pd.DataFrame, preds_df: pd.DataFrame | None, lot: str,
                history: pd.DataFrame | None = None, notch_deg: float = DEFAULT_NOTCH_DEG,
                synthetic: bool = False) -> LotFindings:
    """로트 하나를 분석해 LotFindings 를 만든다.

    Parameters
    ----------
    records_df : waferMap, lot, wafer_index (+ y_true/y_pred/confidence 가 있어도 된다)
    preds_df   : lot, wafer_index(선택), y_pred, confidence(선택). None 이면 records 의 y_pred/y_true.
    lot        : 분석할 로트명
    history    : 로트 이력(lot, step, tool, chamber ...). 공통성은 preds_df 전체(모든 로트)로 계산한다.
    notch_deg  : 맵 좌표계에서 노치 방향(도). 기본 -90 은 가정.
    synthetic  : 합성 데이터 표시(PDF 배너·JSON 필드)
    """
    rec, src = _lot_frame(records_df, preds_df, lot)
    n = int(len(rec))
    mix_counts = rec["y_pred"].value_counts()
    mix = {k: int(mix_counts[k]) for k in sorted(mix_counts.index, key=lambda k: (-mix_counts[k], k))}
    defect = {k: v for k, v in mix.items() if k != "CLEAN"}
    dominant = next(iter(defect)) if defect else next(iter(mix))
    k_dom = mix[dominant]
    rep = repeat_verdict(n, k_dom) if dominant != "CLEAN" else "insufficient"

    ff = rec["waferMap"].apply(lambda m: fail_fraction(np.asarray(m))).to_numpy(dtype=float)
    conf = rec["confidence"].to_numpy(dtype=float)
    has_conf = bool(np.isfinite(conf).any())
    n_low = int((conf < LOW_CONF).sum()) if has_conf else None

    # 웨이퍼별 표 + 격자 반복 휴리스틱
    grids = []
    wafers = []
    for i, r in rec.iterrows():
        arr = np.asarray(r["waferMap"])
        g = grid_repeat_score(arr)
        wi = None if pd.isna(r["wafer_index"]) else int(r["wafer_index"])
        g["wafer_index"] = wi
        grids.append(g)
        wafers.append({"wafer_index": wi, "y_pred": r["y_pred"],
                       "confidence": None if not np.isfinite(conf[i]) else float(conf[i]),
                       "fail_frac": float(ff[i]), "shape": None, "theta_deg": None,
                       "grid_repeat": {"suspect": bool(g["suspect"]), "score": float(g["score"]),
                                       "lag_x": int(g["lag_x"]), "lag_y": int(g["lag_y"])}})

    # 방위각 (EDGE_LOC / LOC)
    az: dict | None = None
    if any(p in mix for p in AZIMUTH_CLASSES):
        az_lots = lot_azimuth_summary(rec, classes=AZIMUTH_CLASSES, min_n=MIN_N_REPEAT, notch_deg=notch_deg)
        az_w = wafer_azimuth_table(rec, AZIMUTH_CLASSES, notch_deg)
        row = az_lots.iloc[0].to_dict()
        az = {"classes": list(AZIMUTH_CLASSES), "n": int(row["n"]), "r_bar": float(row["r_bar"]),
              "mean_deg": float(row["mean_deg"]), "span_med": float(row["span_med"]), "p": float(row["p"]),
              "verdict": str(row["verdict"]), "theta_deg": [float(t) for t in az_w["theta_deg"]],
              "wafer_index": [None if pd.isna(w) else int(w) for w in az_w["wafer_index"]]}
        th = dict(zip(az["wafer_index"], az["theta_deg"]))
        for w in wafers:
            if w["y_pred"] in AZIMUTH_CLASSES and w["wafer_index"] in th:
                w["theta_deg"] = th[w["wafer_index"]]

    # 스크래치 모양
    sc: dict | None = None
    if "SCRATCH" in mix:
        sc_lots = lot_scratch_summary(rec, notch_deg=notch_deg, min_n=MIN_N_REPEAT)
        sc_w = wafer_scratch_table(rec, notch_deg)
        row = sc_lots.iloc[0].to_dict()
        sc = {"n_scratch": int(row["n_scratch"]), "n_line": int(row["n_line"]), "n_arc": int(row["n_arc"]),
              "n_ambiguous": int(row["n_ambiguous"]), "n_too_short": int(row["n_too_short"]),
              "angle_consistency": float(row["angle_consistency"]), "mean_axis_deg": float(row["mean_axis_deg"]),
              "p_axial": float(row["p_axial"]), "verdict": str(row["verdict"]),
              "shapes": {str(a): str(b) for a, b in zip(sc_w["wafer_index"], sc_w["shape"])}}
        shp = dict(zip(sc_w["wafer_index"], sc_w["shape"]))
        for w in wafers:
            if w["y_pred"] == "SCRATCH" and w["wafer_index"] in shp:
                w["shape"] = str(shp[w["wafer_index"]])

    # 슬롯 분포 (로트 안만, 검정 아님). 끝 슬롯 집중 = 끝 슬롯 발생률이 가운데의 2배 이상이고 양쪽에 2장 이상.
    slot: dict | None = None
    if rec["wafer_index"].notna().any() and dominant != "CLEAN":
        tab = slot_rate_table(rec, dominant, slot_col="wafer_index", pred_col="y_pred")
        slots = [int(s) for s in tab["slot"]]
        hits = [int(s) for s, k in zip(tab["slot"], tab["k"]) if k > 0]
        is_end = np.array([s in DEFAULT_END_SLOTS for s in slots])
        n_end, n_mid = int(is_end.sum()), int((~is_end).sum())
        k_end = int(sum(1 for s in hits if s in DEFAULT_END_SLOTS))
        k_mid = len(hits) - k_end
        rate_end = k_end / n_end if n_end else float("nan")
        rate_mid = k_mid / n_mid if n_mid else float("nan")
        slot = {"pattern": dominant, "slots": slots, "hit_slots": hits, "n_end": n_end, "n_mid": n_mid,
                "n_end_slot_hits": k_end, "rate_end": rate_end, "rate_mid": rate_mid,
                "end_concentrated": bool(n_end >= 2 and n_mid >= 2 and k_end >= 2 and np.isfinite(rate_mid)
                                         and rate_end >= 2.0 * max(rate_mid, 1e-9)),
                "longest_run": _longest_run(hits), "note": SLOT_NOTE}

    # 공통성 (이력이 있을 때, 모든 로트의 예측으로)
    cm_top: list[dict] = []
    if history is not None and dominant != "CLEAN":
        base = preds_df if preds_df is not None else records_df
        if "y_pred" not in base.columns and "y_true" in base.columns:
            base = base.rename(columns={"y_true": "y_pred"})
        status = lot_pattern_status(base, dominant)
        if len(status):
            tab = commonality_table(history, status)
            lot_hist = history[history["lot"].astype(str) == str(lot)]
            ch = lot_hist["chamber"].astype(str) if "chamber" in lot_hist.columns else pd.Series("", index=lot_hist.index)
            ok = tab[tab["evidence"] == "ok"].head(3)
            for _, r in ok.iterrows():
                hit = (lot_hist["step"].astype(str) == str(r["step"])) & (lot_hist["tool"].astype(str) == str(r["tool"]))
                if str(r["chamber"]):
                    hit &= ch == str(r["chamber"])
                passed = bool(hit.any())
                cm_top.append({"step": str(r["step"]), "tool": str(r["tool"]), "chamber": str(r["chamber"]),
                               "n_lots": int(r["n_lots"]), "n_bad": int(r["n_bad"]), "rate": float(r["rate"]),
                               "rate_other": float(r["rate_other"]), "rate_ratio": float(r["rate_ratio"]),
                               "q_bh": float(r["q_bh"]), "this_lot_passed": passed,
                               "n_lots_total": int(tab.attrs.get("n_lots_total", 0)),
                               "n_bad_total": int(tab.attrs.get("n_bad_total", 0))})

    flags = exclusion_flags(mix, grids, n)
    grid_any = any(g["suspect"] for g, w in zip(grids, wafers) if w["y_pred"] == dominant)
    suspects = rank_suspects(dominant, rep, az["verdict"] if az else None, sc["verdict"] if sc else None,
                             {"line": sc["n_line"], "arc": sc["n_arc"]} if sc else None,
                             bool(slot and slot["end_concentrated"]), grid_any, mix)
    lvl, why = ocap_level(dominant, rep, mix)
    d = ACTION_DETAIL.get(dominant, {})
    evidence = {"customer": list(d.get("customer_evidence", [])), "tool": list(d.get("tool_evidence", []))}
    d2 = make_d2_draft(str(lot), n, dominant, k_dom, rep, float(np.nanmean(ff)), az, sc, notch_deg, synthetic)

    return LotFindings(
        lot=str(lot), n=n, mix=mix, dominant=dominant, dominant_count=k_dom, dominant_frac=k_dom / n,
        repeat_verdict=rep, mean_fail_frac=float(np.nanmean(ff)), min_fail_frac=float(np.nanmin(ff)),
        max_fail_frac=float(np.nanmax(ff)), n_low_conf=n_low, azimuth=az, scratch=sc, slot=slot,
        commonality_top=cm_top, test_exclusion_flags=flags, suspects=suspects, ocap_level=lvl,
        ocap_reason=why, evidence=evidence, handoff=str(d.get("handoff", "")), d2_draft=d2,
        notch_deg=float(notch_deg), synthetic=bool(synthetic), wafers=wafers, label_source=src,
    )


# ──────────────────────────────────────────
# 4. JSON
# ──────────────────────────────────────────
def _jsonable(v):
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if not np.isfinite(v) else float(v)
    if isinstance(v, np.ndarray):
        return _jsonable(v.tolist())
    if v is None or isinstance(v, str):
        return v
    return str(v)


def findings_to_json(findings: LotFindings, anonymize: bool = False, salt: bytes | None = None) -> dict:
    """LotFindings -> JSON 직렬화 가능한 dict (NaN -> null, numpy -> 기본형). 메타·면책 문구를 붙인다."""
    d = _jsonable(asdict(findings))
    if anonymize:
        d["lot"] = anonymize_lot_id(findings.lot, salt or os.urandom(8))
        d["anonymized"] = True
        d["d2_draft"] = d["d2_draft"].replace(findings.lot, d["lot"])
    else:
        d["anonymized"] = False
    d["ocap_label"] = OCAP_LEVELS[findings.ocap_level]
    d["notch_note"] = NOTCH_NOTE.format(notch=findings.notch_deg)
    d["generated_at"] = datetime.now().isoformat(timespec="seconds")
    d["generator"] = "wm811k_lot_report.py"
    d["disclaimer"] = ("Synthetic data - logic check, not performance." if findings.synthetic else
                       "Classification taken from input predictions as-is.") + \
                      " Action text from wafer_pattern_classifier.ACTION_DETAIL (public-source level; TEL internals unknown)."
    return d


def save_findings_json(findings: LotFindings, path: Path, anonymize: bool = False, salt: bytes | None = None) -> dict:
    d = findings_to_json(findings, anonymize, salt)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return d


# ──────────────────────────────────────────
# 5. PDF
# ──────────────────────────────────────────
class _Flow:
    """A4 세로 페이지에 위에서 아래로 줄을 쌓고, 지면이 끝나면 자동으로 다음 페이지를 연다.

    첫 페이지는 render_lot_pdf 가 헤더·썸네일·로즈를 그린 뒤 남은 높이(start_y)부터 시작한다. 페이지가
    바뀔 때마다 작은 제목 줄과 각주·페이지 번호를 찍는다. 그래서 리포트는 로트 크기에 따라 1~2페이지
    (썸네일이 많으면 그 이상)가 된다.
    """

    LINE = {6.5: 0.0105, 7: 0.0115, 7.5: 0.0125, 8: 0.013, 9: 0.0145, 10: 0.016, 12: 0.019}
    INK, MUTED, HEAD, WARN = "#263238", "#607D8B", "#1A237E", "#C62828"
    LATIN_WIDTH_8PT = 118
    LATIN_EM, CJK_EM = 0.55, 0.85
    TOP, BOTTOM, LEFT, RIGHT = 0.955, 0.085, 0.045, 0.955

    def __init__(self, pdf: PdfPages, fig, start_y: float, shown_lot: str, L: dict, foot: str, page_no: int = 1):
        self.pdf, self.L, self.shown_lot, self.foot = pdf, L, shown_lot, foot
        self.page_no = page_no
        self.fig = fig
        self.ax = fig.add_axes((0, 0, 1, 1))
        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(0, 1)
        self.ax.axis("off")
        self.y = start_y

    @classmethod
    def wrap_width(cls, text: str, size: float, frac: float = 1.0) -> int:
        if not text:
            return 20
        em = sum(cls.CJK_EM if ord(c) > 0x2E80 else cls.LATIN_EM for c in text) / len(text)
        return max(16, int(cls.LATIN_WIDTH_8PT * (8 / size) * frac * cls.LATIN_EM / em))

    def _step(self, size: float) -> float:
        return self.LINE.get(size, 0.0016 * size)

    def _finish_page(self) -> None:
        self.ax.plot([self.LEFT, self.RIGHT], [0.062, 0.062], color="#B0BEC5", linewidth=0.6)
        self.ax.text(self.LEFT, 0.055, "\n".join(textwrap.wrap(self.foot, width=self.wrap_width(self.foot, 6.5))),
                     fontsize=6.5, va="top", ha="left", color=self.MUTED)
        self.ax.text(self.RIGHT, 0.02, f"{self.shown_lot}  p.{self.page_no}", fontsize=6.5, ha="right", color=self.MUTED)
        self.pdf.savefig(self.fig)
        plt.close(self.fig)

    def new_page(self) -> None:
        self._finish_page()
        self.page_no += 1
        self.fig = plt.figure(figsize=A4_PORTRAIT)
        self.ax = self.fig.add_axes((0, 0, 1, 1))
        self.ax.set_xlim(0, 1)
        self.ax.set_ylim(0, 1)
        self.ax.axis("off")
        self.ax.text(self.LEFT, self.TOP, self.L["title"], fontsize=12, fontweight="bold", va="top", ha="left", color=self.HEAD)
        self.ax.text(self.RIGHT, self.TOP, self.shown_lot, fontsize=11, fontweight="bold", va="top", ha="right", color=self.INK)
        self.y = self.TOP - 0.028

    def close(self) -> int:
        self._finish_page()
        return self.page_no

    def ensure(self, n_lines: int, size: float) -> None:
        if self.y - n_lines * self._step(size) < self.BOTTOM:
            self.new_page()

    def n_lines(self, text: str, size: float, indent: float = 0.0) -> int:
        return len(textwrap.wrap(text, width=self.wrap_width(text, size, frac=1.0 - indent / (self.RIGHT - self.LEFT))) or [""])

    def line(self, text: str, size: float = 8, bold: bool = False, color: str | None = None, indent: float = 0.0) -> None:
        width = self.wrap_width(text, size, frac=1.0 - indent / (self.RIGHT - self.LEFT))
        lines = textwrap.wrap(text, width=width) or [""]
        self.ensure(min(len(lines), 3), size)              # 첫 3줄은 같은 페이지에, 나머지는 넘어가며 쓴다
        for ln in lines:
            self.ensure(1, size)
            self.ax.text(self.LEFT + indent, self.y, ln, fontsize=size, va="top", ha="left",
                         fontweight="bold" if bold else "normal", color=color or self.INK)
            self.y -= self._step(size)

    def heading(self, text: str) -> None:
        self.ensure(4, 10)                                 # 제목이 페이지 끝에 홀로 남지 않게
        self.y -= 0.006
        self.line(text, size=10, bold=True, color=self.HEAD)
        self.ax.plot([self.LEFT, self.RIGHT], [self.y + 0.004, self.y + 0.004], color="#B0BEC5", linewidth=0.6)
        self.y -= 0.004

    def checklist(self, left_title: str, left_items: list[str], right_title: str, right_items: list[str],
                  size: float = 7, max_rows: int = 6) -> None:
        """두 열 체크박스. 열 전체가 한 페이지에 들어가도록 먼저 높이를 재고 필요하면 페이지를 넘긴다."""
        def height(items: list[str]) -> float:
            h = self._step(9)
            for s in items[:max_rows]:
                h += len(textwrap.wrap("[ ] " + s, width=self.wrap_width(s, size, frac=0.47)) or [""]) * self._step(size)
            if len(items) > max_rows:
                h += self._step(size)
            return h
        need = max(height(left_items), height(right_items))
        if self.y - need < self.BOTTOM:
            self.new_page()
        col_w = (self.RIGHT - self.LEFT) / 2
        y0 = self.y
        for k, (title, items) in enumerate(((left_title, left_items), (right_title, right_items))):
            x, y = self.LEFT + k * col_w, y0
            self.ax.text(x, y, title, fontsize=9, fontweight="bold", va="top", ha="left", color=self.HEAD)
            y -= self._step(9)
            for s in items[:max_rows]:
                for j, ln in enumerate(textwrap.wrap("[ ] " + s, width=self.wrap_width(s, size, frac=0.47)) or [""]):
                    self.ax.text(x + (0.014 if j else 0.0), y, ln, fontsize=size, va="top", ha="left", color=self.INK)
                    y -= self._step(size)
            if len(items) > max_rows:
                self.ax.text(x, y, f"    (+{len(items) - max_rows})", fontsize=size, va="top", ha="left", color=self.MUTED)
                y -= self._step(size)
            self.y = min(self.y, y)


def _thumb_image(arr: np.ndarray) -> np.ndarray:
    a = np.asarray(arr)
    img = np.full(a.shape + (3,), 0.925)          # #ECEFF1 근처
    img[a == 1] = to_rgb(PASS_COLOR)
    img[a == 2] = to_rgb(FAIL_COLOR)
    return img


def draw_thumbnail(ax, arr: np.ndarray, title: str, notch_deg: float, color: str = "#263238") -> None:
    """맵 한 장 썸네일: imshow + 다이 bbox 원 + 노치 삼각형(notch_deg 방향) + 제목."""
    a = np.asarray(arr)
    ax.imshow(_thumb_image(a), interpolation="nearest")
    try:
        cy, cx, ry, rx = wafer_frame(a)
    except ValueError:
        cy, cx, ry, rx = (a.shape[0] - 1) / 2, (a.shape[1] - 1) / 2, a.shape[0] / 2, a.shape[1] / 2
    th = np.linspace(0, 2 * np.pi, 120)
    ax.plot(cx + (rx + 0.6) * np.cos(th), cy - (ry + 0.6) * np.sin(th), color="#78909C", lw=0.6)
    nx = cx + (rx + 0.6) * math.cos(math.radians(notch_deg))
    ny = cy - (ry + 0.6) * math.sin(math.radians(notch_deg))
    ax.plot([nx], [ny], marker="^", markersize=5, color="#455A64", markeredgecolor="white", markeredgewidth=0.4,
            linestyle="")
    ax.set_xlim(-1.5, a.shape[1] + 0.5)
    ax.set_ylim(a.shape[0] + 0.5, -1.5)
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title(title, fontsize=6.5, pad=2, color=color)


def _wafer_title(w: dict) -> tuple[str, str]:
    idx = f"w{w['wafer_index']:02d}" if w["wafer_index"] is not None else "w?"
    s = f"{idx} {w['y_pred']}"
    if w["confidence"] is not None:
        s += f" ({w['confidence']:.2f})"
    extra = []
    if w.get("shape"):
        extra.append(w["shape"])
    if w.get("theta_deg") is not None and np.isfinite(w["theta_deg"]):
        extra.append(f"{w['theta_deg']:.0f}deg")
    if w.get("grid_repeat", {}).get("suspect"):
        extra.append("grid?")
    s += f"\n{w['fail_frac']:.1%}" + (f" {' '.join(extra)}" if extra else "")
    color = "#C62828" if (w["confidence"] is not None and w["confidence"] < LOW_CONF) else "#263238"
    return s, color


def _header(fig, f: LotFindings, shown_lot: str, L: dict, lang: str, anonymized: bool) -> float:
    """1페이지 헤더(제목·배너·요약 줄·패턴 믹스 막대). 다음 블록이 시작할 y 를 돌려준다."""
    ax = fig.add_axes((0, 0, 1, 1), label="header")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.text(0.045, 0.965, L["title"], fontsize=15, fontweight="bold", va="top", ha="left", color=_Flow.HEAD)
    ax.text(0.955, 0.965, shown_lot, fontsize=13, fontweight="bold", va="top", ha="right", color=_Flow.INK)
    banner = L["banner_syn"] if f.synthetic else L["banner_real"]
    bg, fg, edge = ("#FFF3E0", "#E65100", "#FB8C00") if f.synthetic else ("#E3F2FD", "#0D47A1", "#64B5F6")
    ax.add_patch(plt.Rectangle((0.045, 0.918), 0.91, 0.022, facecolor=bg, edgecolor=edge, linewidth=0.8))
    ax.text(0.051, 0.929, banner, fontsize=7.5, va="center", ha="left", color=fg)
    rep = REPEAT_TEXT.get(f.repeat_verdict, REPEAT_TEXT["insufficient"])[lang]
    lines = [L["hdr_n"].format(n=f.n),
             L["hdr_ff"].format(ff=f.mean_fail_frac, lo=f.min_fail_frac, hi=f.max_fail_frac),
             L["hdr_dom"].format(p=f.dominant, k=f.dominant_count, n=f.n, rep=rep),
             L["hdr_low"].format(t=LOW_CONF, k=f.n_low_conf) if f.n_low_conf is not None else L["hdr_low_none"],
             f"OCAP: {OCAP_LEVELS[f.ocap_level][lang]}"]
    if anonymized:
        lines.append(L["hdr_anon"])
    y = 0.905
    for i, s in enumerate(lines):
        ax.text(0.045, y, s, fontsize=8.5 if i < 3 else 7.5, va="top", ha="left",
                color=_Flow.WARN if i == 4 else _Flow.INK, fontweight="bold" if i == 2 else "normal")
        y -= 0.016
    mx = fig.add_axes((0.62, 0.80, 0.33, 0.10))
    pats = list(f.mix)
    cnt = [f.mix[p] for p in pats]
    pos = list(range(len(pats)))[::-1]
    mx.barh(pos, cnt, color=["#1565C0" if p == f.dominant else "#90A4AE" for p in pats], height=0.7)
    mx.set_yticks(pos)
    mx.set_yticklabels(pats, fontsize=6.5)
    mx.set_xlim(0, max(cnt) * 1.25)
    for yy, c in zip(pos, cnt):
        mx.text(c + max(cnt) * 0.03, yy, str(c), fontsize=6.5, va="center")
    mx.tick_params(axis="x", labelsize=6)
    mx.set_title(L["mix_title"], fontsize=7.5, pad=2)
    for s in mx.spines.values():
        s.set_color("#B0BEC5")
    return 0.785


def _thumbnails(pdf: PdfPages, f: LotFindings, rec: pd.DataFrame, shown_lot: str, L: dict, lang: str,
                anonymized: bool) -> tuple[object, float, int]:
    """헤더 + 썸네일(+ 로즈). 마지막 썸네일 페이지의 fig, 그 페이지에서 비는 y, 그때까지 페이지 수(마지막 제외)."""
    arrs = list(rec["waferMap"])
    order = f.wafers[:len(arrs)]
    n = len(order)
    rose = (f.azimuth is not None and f.azimuth["n"] >= MIN_N_ROSE)
    pages_done = 0
    fig, y_free = None, 0.0
    for start in range(0, max(n, 1), THUMBS_PER_PAGE):
        if fig is not None:
            fig.text(0.955, 0.02, f"{shown_lot}  p.{pages_done + 1}", fontsize=6.5, ha="right", color=_Flow.MUTED)
            pdf.savefig(fig)
            plt.close(fig)
            pages_done += 1
        chunk = order[start:start + THUMBS_PER_PAGE]
        fig = plt.figure(figsize=A4_PORTRAIT)
        if pages_done == 0:
            top = _header(fig, f, shown_lot, L, lang, anonymized) - 0.01
        else:
            fig.text(0.045, 0.955, L["title"], fontsize=12, fontweight="bold", va="top", ha="left", color=_Flow.HEAD)
            fig.text(0.955, 0.955, shown_lot, fontsize=11, fontweight="bold", va="top", ha="right", color=_Flow.INK)
            top = 0.91
        k = len(chunk)
        ncol = int(min(6, max(3, math.ceil(math.sqrt(max(k, 1) * 1.3)))))
        nrow = max(1, math.ceil(k / ncol))
        cell_w = 0.91 / ncol
        cell_h = min((top - 0.09) / nrow, cell_w * A4_PORTRAIT[0] / A4_PORTRAIT[1] * 1.22)
        fig.text(0.045, top + 0.004, L["thumb_title"].format(notch=f.notch_deg) +
                 (f"  {L['thumb_more'].format(a=start + 1, b=start + k)}" if start + k < n else ""),
                 fontsize=7.5, va="bottom", ha="left", color=_Flow.MUTED)
        for i, w in enumerate(chunk):
            r, c = divmod(i, ncol)
            ax = fig.add_axes((0.045 + c * cell_w + cell_w * 0.06, top - (r + 1) * cell_h + cell_h * 0.04,
                               cell_w * 0.88, cell_h * 0.78))
            title, color = _wafer_title(w)
            draw_thumbnail(ax, np.asarray(arrs[start + i]), title, f.notch_deg, color)
        y_free = top - nrow * cell_h - 0.01
    if rose and y_free - 0.255 < 0.06:        # 로즈 높이 0.20 + 제목 여백 0.055
        # 로즈가 들어갈 자리가 없으면 새 페이지에
        fig.text(0.955, 0.02, f"{shown_lot}  p.{pages_done + 1}", fontsize=6.5, ha="right", color=_Flow.MUTED)
        pdf.savefig(fig)
        plt.close(fig)
        pages_done += 1
        fig = plt.figure(figsize=A4_PORTRAIT)
        fig.text(0.045, 0.955, L["title"], fontsize=12, fontweight="bold", va="top", ha="left", color=_Flow.HEAD)
        fig.text(0.955, 0.955, shown_lot, fontsize=11, fontweight="bold", va="top", ha="right", color=_Flow.INK)
        y_free = 0.91
    if rose:
        h = 0.20
        y_free -= 0.055                        # 로즈 제목 2줄 + 극좌표 라벨이 썸네일과 겹치지 않게
        rx = fig.add_axes((0.09, y_free - h, 0.30, h), projection="polar")
        plot_azimuth_rose(f.azimuth["theta_deg"], rx, f.notch_deg,
                          title=L["rose_title"].format(p="/".join(p for p in AZIMUTH_CLASSES if p in f.mix)))
        rx.set_title(rx.get_title(), fontsize=7.5)
        rx.tick_params(labelsize=6)
        note = L["v_az_read"].get(f.azimuth["verdict"], "")
        fig.text(0.46, y_free - h / 2, f"verdict: {f.azimuth['verdict']}\n{note}\n"
                 f"n={f.azimuth['n']}, r_bar={f.azimuth['r_bar']:.2f}, mean={f.azimuth['mean_deg']:.0f} deg, "
                 f"p={f.azimuth['p']:.3g}\n{L['rose_note']}", fontsize=7.5, va="center", ha="left", color=_Flow.INK)
        y_free = y_free - h - 0.04
    return fig, y_free, pages_done


def _write_sections(flow: _Flow, f: LotFindings, L: dict, lang: str, d2: str) -> None:
    """판정 / 테스트 원인 배제 / 의심 모듈 / 증거 체크 / 다음 행동 을 flow 에 쓴다(페이지 자동 넘김)."""
    # 1. 판정
    flow.heading(L["h_verdict"])
    rep = REPEAT_TEXT.get(f.repeat_verdict, REPEAT_TEXT["insufficient"])[lang]
    flow.line(L["v_repeat"].format(rep=rep, p=f.dominant, k=f.dominant_count, n=f.n, f=PROCESS_FRAC), bold=True)
    if f.azimuth:
        a = f.azimuth
        flow.line(L["v_az"].format(cls="/".join(p for p in a["classes"] if p in f.mix), n=a["n"], r=a["r_bar"],
                                   m=a["mean_deg"], p=a["p"], v=a["verdict"], read=L["v_az_read"].get(a["verdict"], "")),
                  indent=0.012)
    if f.scratch:
        s = f.scratch
        cons = f"{s['angle_consistency']:.2f}" if np.isfinite(s["angle_consistency"]) else "nan"
        flow.line(L["v_sc"].format(n=s["n_scratch"], l=s["n_line"], a=s["n_arc"], m=s["n_ambiguous"], s=s["n_too_short"],
                                   c=cons, v=s["verdict"], read=L["v_sc_read"].get(s["verdict"], "")), indent=0.012)
    if f.slot:
        sl = f.slot
        re_, rm = sl["rate_end"], sl["rate_mid"]
        flow.line(L["v_slot"].format(p=sl["pattern"], lo=min(sl["slots"]), hi=max(sl["slots"]),
                                     hits=",".join(str(s) for s in sl["hit_slots"]) or "-",
                                     re=f"{re_:.2f}" if np.isfinite(re_) else "-", rm=f"{rm:.2f}" if np.isfinite(rm) else "-",
                                     conc=L["slot_conc"] if sl["end_concentrated"] else L["slot_noconc"],
                                     run=sl["longest_run"]), indent=0.012)
        flow.line(L["v_slot_note"].format(p=sl["pattern"]), size=7, indent=0.012, color=flow.MUTED)
    if f.commonality_top:
        t0 = f.commonality_top[0]
        flow.line(L["v_cm"].format(p=f.dominant, nl=t0["n_lots_total"], nb=t0["n_bad_total"]), indent=0.012)
        for i, r in enumerate(f.commonality_top, 1):
            unit = f"{r['step']} {r['tool']}" + (f"/{r['chamber']}" if r["chamber"] else "")
            flow.line(L["v_cm_row"].format(i=i, unit=unit, a=r["n_bad"], n1=r["n_lots"], r=r["rate"], ro=r["rate_other"],
                                           rr=r["rate_ratio"], q=r["q_bh"],
                                           pass_=L["v_cm_pass"] if r["this_lot_passed"] else L["v_cm_nopass"]),
                      size=7.5, indent=0.024)
        flow.line(L["v_cm_note"], size=7, indent=0.012, color=flow.MUTED)
    else:
        flow.line(L["v_cm_none"], size=7, indent=0.012, color=flow.MUTED)

    # 2. 테스트 원인 배제
    flow.heading(L["h_excl"])
    if f.test_exclusion_flags:
        for s in f.test_exclusion_flags:
            flow.line("! " + s, bold=True, color=flow.WARN, indent=0.012)
    else:
        flow.line(L["excl_none"], color=flow.MUTED, indent=0.012)

    # 3. 의심 모듈
    combo = [f.repeat_verdict]
    if f.azimuth:
        combo.append(f"azimuth={f.azimuth['verdict']}")
    if f.scratch:
        combo.append(f"scratch={f.scratch['verdict']}")
    flow.heading(L["h_susp"].format(p=f.dominant, combo=", ".join(combo)))
    for s in f.suspects[:6]:
        row = L["susp_row"].format(i=s["rank"], mod=s["module"], chk=s["check"])
        basis = L["susp_basis"].format(b=s["basis"])
        flow.ensure(flow.n_lines(row, 7.5, 0.012) + flow.n_lines(basis, 6.5, 0.012), 7.5)   # 항목과 근거를 같은 페이지에
        flow.line(row, indent=0.012, size=7.5)
        flow.line(basis, indent=0.012, size=6.5, color=flow.MUTED)

    # 4. 증거
    flow.heading(L["h_evid"])
    flow.checklist(L["evid_cust"], f.evidence["customer"], L["evid_tool"], f.evidence["tool"], max_rows=5)

    # 5. 다음 행동
    flow.heading(L["h_next"])
    flow.line(L["next_ocap"].format(lvl=OCAP_LEVELS[f.ocap_level][lang], why=f.ocap_reason.get(lang, "")),
              bold=True, color=flow.WARN)
    flow.line(L["next_d2"].format(d2=d2), size=7.5)
    if f.handoff:
        flow.line(L["next_handoff"].format(s=f.handoff), size=7.5)
    flow.line(L["next_link"].format(link=CASE_STUDY_LINK), size=7.5, color=flow.MUTED)


def resolve_lang(lang: str, quiet: bool = False) -> str:
    """--lang ko 인데 한글 폰트가 없으면 en 으로 전환한다."""
    if lang not in LABELS:
        raise ValueError(f"lang must be one of {list(LABELS)}: {lang!r}")
    if lang == "ko" and not has_korean_font():
        if not quiet:
            print(LABELS["ko"]["c_font_none"], file=sys.stderr)
        return "en"
    return lang


def render_lot_pdf(findings: LotFindings, records_df: pd.DataFrame, out_path: Path, lang: str = "ko",
                   anonymize: bool = False, salt: bytes | None = None, quiet: bool = True) -> Path:
    """LotFindings 를 A4 PDF 로. 헤더 + 썸네일(+ 로즈) 뒤에 판정·배제·의심 모듈·증거·다음 행동이 이어진다.

    지면이 끝나면 자동으로 다음 페이지를 열므로 보통 1~2페이지(썸네일 36장 초과면 그 이상)다.
    records_df 는 analyze_lot 에 준 것과 같아야 한다(썸네일용 waferMap). anonymize 면 로트명을 키드 해시로
    바꾼다(같은 salt 면 JSON 과 같은 값). 페이지 수는 PDF 메타데이터 Subject 에 적는다. 반환: 저장 경로.
    """
    setup_korean_font()
    lang = resolve_lang(lang, quiet=quiet)
    L = LABELS[lang]
    f = findings
    shown = anonymize_lot_id(f.lot, salt or os.urandom(8)) if anonymize else f.lot
    # 썸네일 순서를 analyze_lot 의 f.wafers(슬롯 순)와 맞춘다. wafer_index 가 없으면 records 의 행 순서.
    rec = records_df[records_df["lot"].astype(str) == f.lot].copy()
    if len(rec) == 0:
        raise ValueError(f"records_df 에 로트 {f.lot!r} 이 없다.")
    rec["wafer_index"] = pd.to_numeric(rec["wafer_index"], errors="coerce") if "wafer_index" in rec.columns else np.nan
    idx = [w["wafer_index"] for w in f.wafers]
    if idx and all(i is not None for i in idx) and len(set(idx)) == len(idx) and rec["wafer_index"].notna().all():
        rec = rec.drop_duplicates("wafer_index")
        rec = rec.set_index(rec["wafer_index"].astype(int)).loc[[int(i) for i in idx]].reset_index(drop=True)
    else:
        rec = rec.reset_index(drop=True)
    d2 = f.d2_draft if lang == "ko" else make_d2_draft(f.lot, f.n, f.dominant, f.dominant_count, f.repeat_verdict,
                                                       f.mean_fail_frac, f.azimuth, f.scratch, f.notch_deg,
                                                       f.synthetic, "en")
    if anonymize:
        d2 = d2.replace(f.lot, shown)
    foot = L["foot"].format(notch=NOTCH_NOTE.format(notch=f.notch_deg), t=datetime.now().strftime("%Y-%m-%d %H:%M"))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(out_path) as pdf:
        fig, y_free, pages_done = _thumbnails(pdf, f, rec, shown, L, lang, anonymize)
        flow = _Flow(pdf, fig, y_free, shown, L, foot, page_no=pages_done + 1)
        if y_free < 0.20:                      # 썸네일 아래 공간이 너무 좁으면(제목 + 몇 줄 미만) 다음 페이지에서 시작
            flow.new_page()
        _write_sections(flow, f, L, lang, d2)
        n_pages = flow.close()
        info = pdf.infodict()
        info["Title"] = L["pdf_title"].format(lot=shown, syn=" [synthetic data]" if f.synthetic else "")
        info["Subject"] = (("synthetic data - logic check, not performance; " if f.synthetic else "") +
                           f"lot {shown}, {f.n} wafers, dominant {f.dominant}, repeat {f.repeat_verdict}, "
                           f"OCAP {f.ocap_level}, {n_pages} pages" + ("; lot id anonymized" if anonymize else ""))
        info["Keywords"] = "wafer map, lot troubleshooting report, OCAP, 8D D2, WM-811K" + (", synthetic data" if f.synthetic else "")
        info["Creator"] = "wm811k_lot_report.py (wm811k-wafer-analysis)"
        info["CreationDate"] = datetime.now()
    return out_path


# ──────────────────────────────────────────
# 6. 합성 데모 (로직 확인용 - 성능 아님)
# ──────────────────────────────────────────
DEMO_LOTS = ("demo_edge_loc_fixed", "demo_scratch_line", "demo_near_full_one")


def demo_records(seed: int = 0, n_background_lots: int = 60) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """합성 로트 3개 + 배경 로트(make_lswmd) 와 그에 맞는 예측·이력.

    demo_edge_loc_fixed  EDGE_LOC 8장, 생성기 고정 각도      -> fixed_angle, process, L2
    demo_scratch_line    SCRATCH 5장, 생성기 고정 30도 직선   -> reproducible_line, process, L2
    demo_near_full_one   RANDOM 6장 + NEAR_FULL 1장          -> 재테스트 플래그, L1
    배경 로트는 make_lswmd(n_lots) 로 만들고 라벨을 예측으로 쓴다(공통성 상위 계산에 로트 수가 필요).
    이력은 wm811k_commonality.synthetic_history 로 만들되 EDGE_LOC 양성 로트를 ETCH-02 에 몰아 공통성이
    무언가를 가리키게 한다. 전부 가상 ID 다. 반환 (records, preds, history).
    """
    sys.path.insert(0, str(HERE / "tests"))
    from synthetic_wm811k import LABELS as SYN_LABELS, make_lswmd, make_wafermap  # noqa: E402
    from wm811k_commonality import synthetic_history  # noqa: E402

    rng = np.random.default_rng(seed)
    rows = []
    for w in range(8):
        rows.append({"waferMap": make_wafermap("edge_loc", 100 + w, rng), "lot": DEMO_LOTS[0], "wafer_index": w + 1,
                     "y_pred": "EDGE_LOC"})
    for w in range(5):
        rows.append({"waferMap": make_wafermap("scratch", 200 + w, rng), "lot": DEMO_LOTS[1], "wafer_index": w + 1,
                     "y_pred": "SCRATCH"})
    for w in range(6):
        rows.append({"waferMap": make_wafermap("random", 300 + w, rng), "lot": DEMO_LOTS[2], "wafer_index": w + 1,
                     "y_pred": "RANDOM"})
    rows.append({"waferMap": make_wafermap("near_full", 399, rng), "lot": DEMO_LOTS[2], "wafer_index": 7,
                 "y_pred": "NEAR_FULL"})
    bg = make_lswmd(n_lots=n_background_lots, n_unlabeled=0, seed=seed + 1)
    inv = {v: k for k, v in SYN_LABELS.items()}
    to_cls = {"ring": "EDGE_RING", "center": "CENTER", "scratch": "SCRATCH", "random": "RANDOM", "donut": "DONUT",
              "edge_loc": "EDGE_LOC", "loc": "LOC", "near_full": "NEAR_FULL"}
    for _, r in bg.iterrows():
        lab = to_cls[inv[str(np.asarray(r["failureType"]).reshape(-1)[0])]]
        rows.append({"waferMap": r["waferMap"], "lot": "bg_" + str(r["lotName"]), "wafer_index": int(r["waferIndex"]) + 1,
                     "y_pred": lab})
    rec = pd.DataFrame(rows)
    rec["confidence"] = np.round(rng.uniform(0.55, 0.99, len(rec)), 3)
    preds = rec[["lot", "wafer_index", "y_pred", "confidence"]].copy()
    records = rec[["waferMap", "lot", "wafer_index"]].copy()

    hist = synthetic_history(rec["lot"].unique(), seed=seed, planted={"ETCH_M1": "ETCH-02"})
    status = lot_pattern_status(preds, "EDGE_LOC")
    pos = set(status.index[status].astype(str))
    m = (hist["step"] == "ETCH_M1")
    for i in hist.index[m]:
        if str(hist.at[i, "lot"]) in pos:
            if rng.random() < 0.9:
                hist.at[i, "tool"] = "ETCH-02"
        elif hist.at[i, "tool"] == "ETCH-02" and rng.random() < 0.7:
            hist.at[i, "tool"] = "ETCH-01" if rng.random() < 0.5 else "ETCH-03"
    return records, preds, hist


def run_demo(out_dir: Path, lang: str = "ko", anonymize: bool = False, quiet: bool = False) -> dict[str, LotFindings]:
    """합성 로트 3개의 PDF + JSON 을 out_dir 에 쓰고 기대 판정과 비교한다. 로직 확인이지 성능이 아니다."""
    records, preds, hist = demo_records()
    out_dir.mkdir(parents=True, exist_ok=True)
    salt = os.urandom(8)
    say = (lambda *a, **k: None) if quiet else print
    say(LABELS["ko" if lang == "ko" else "en"]["c_demo"].format(lots=", ".join(DEMO_LOTS)))
    results: dict[str, LotFindings] = {}
    for lot in DEMO_LOTS:
        f = analyze_lot(records, preds, lot, history=hist, synthetic=True)
        shown = anonymize_lot_id(lot, salt) if anonymize else lot
        pdf = render_lot_pdf(f, records, out_dir / f"lot_report_{shown}.pdf", lang=lang, anonymize=anonymize,
                             salt=salt, quiet=quiet)
        save_findings_json(f, out_dir / f"lot_report_{shown}.json", anonymize=anonymize, salt=salt)
        results[lot] = f
        say(f"  {lot}: n={f.n} dominant={f.dominant} {f.dominant_count}/{f.n} repeat={f.repeat_verdict} "
            f"azimuth={f.azimuth['verdict'] if f.azimuth else '-'} scratch={f.scratch['verdict'] if f.scratch else '-'} "
            f"ocap={f.ocap_level} flags={len(f.test_exclusion_flags)} suspects[0]={f.suspects[0]['module'] if f.suspects else '-'}")
        say("  " + LABELS[lang]["c_saved"].format(pdf=pdf, js=out_dir / f"lot_report_{shown}.json"))
    exp = {DEMO_LOTS[0]: ("process", "fixed_angle", "L2"), DEMO_LOTS[1]: ("process", "reproducible_line", "L2"),
           DEMO_LOTS[2]: ("process", None, "L1")}
    ok = True
    for lot, (rep, sub, lvl) in exp.items():
        f = results[lot]
        got_sub = (f.azimuth or {}).get("verdict") if lot == DEMO_LOTS[0] else (f.scratch or {}).get("verdict") if lot == DEMO_LOTS[1] else None
        good = f.repeat_verdict == rep and got_sub == sub and f.ocap_level == lvl
        if lot == DEMO_LOTS[2]:
            good &= any("재테스트" in s for s in f.test_exclusion_flags)
        ok &= good
        say(f"  expected {lot}: repeat={rep} sub={sub} ocap={lvl} -> {'OK' if good else 'MISMATCH'}")
    say(f"[demo] {'all as expected' if ok else 'MISMATCH - check logic'} (logic check, not performance)")
    if not ok:
        raise SystemExit(1)
    return results


# ──────────────────────────────────────────
# 7. CLI
# ──────────────────────────────────────────
def _cli(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="로트 단위 트러블슈팅 리포트 (PDF + JSON): 패턴 믹스, 방위각·스크래치·슬롯·"
                                             "공통성 판정, 의심 모듈 순서, OCAP 레벨, 8D D2 초안")
    ap.add_argument("path", nargs="?", type=Path, default=None,
                    help="wm811k_defects.pkl 또는 records.pkl (waferMap, lotName/lot, waferIndex/wafer_index)")
    ap.add_argument("--pred", type=Path, default=None, help="예측 CSV (lot, wafer_index, y_pred, confidence). 없으면 y_true")
    ap.add_argument("--lot", default=None, help="분석할 로트명")
    ap.add_argument("--history", type=Path, default=None, help="로트 이력 CSV (docs/lot_history_schema.md)")
    ap.add_argument("--notch-deg", type=float, default=DEFAULT_NOTCH_DEG,
                    help=f"맵 좌표계에서 노치 방향(도). 기본 {DEFAULT_NOTCH_DEG:g} 는 가정이다")
    ap.add_argument("--lang", choices=list(LABELS), default="ko", help="리포트 언어. 한글 폰트가 없으면 en 으로 자동 전환")
    ap.add_argument("--anonymize", action="store_true", help="로트명을 키드 해시로 치환 (매핑 표 미저장)")
    ap.add_argument("--output", type=Path, default=None, help="출력 폴더 (기본 HERE/lot_report_out, --demo 는 HERE/lot_report_demo)")
    ap.add_argument("--demo", action="store_true", help="합성 로트 3개로 PDF/JSON 생성 (로직 확인, 성능 아님)")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None):
    a = _cli(argv)
    if a.demo:
        return run_demo(a.output or HERE / "lot_report_demo", lang=a.lang, anonymize=a.anonymize)
    if a.path is None or a.lot is None:
        sys.exit("입력 pkl 과 --lot 이 필요하다 (또는 --demo).")
    records = load_records(a.path, None)
    preds = None
    if a.pred is not None:
        preds = pd.read_csv(a.pred)
        preds["lot"] = preds["lot"].astype(str)
    else:
        print("[주의] --pred 가 없어 y_true(라벨)를 판정으로 쓴다.")
    hist = load_lot_history(a.history) if a.history is not None else None
    f = analyze_lot(records, preds, a.lot, history=hist, notch_deg=a.notch_deg)
    out = a.output or HERE / "lot_report_out"
    salt = os.urandom(8)
    shown = anonymize_lot_id(a.lot, salt) if a.anonymize else a.lot
    pdf = render_lot_pdf(f, records, out / f"lot_report_{shown}.pdf", lang=a.lang, anonymize=a.anonymize, salt=salt,
                         quiet=False)
    js = out / f"lot_report_{shown}.json"
    save_findings_json(f, js, anonymize=a.anonymize, salt=salt)
    print(f"lot {shown}: n={f.n} dominant={f.dominant} {f.dominant_count}/{f.n} repeat={f.repeat_verdict} "
          f"ocap={f.ocap_level} ({OCAP_LEVELS[f.ocap_level]['ko']})")
    for s in f.test_exclusion_flags:
        print(f"  ! {s}")
    for s in f.suspects[:3]:
        print(f"  {s['rank']}. [{s['module']}] {s['check']}")
    print(LABELS[a.lang]["c_saved"].format(pdf=pdf, js=js))
    return f


if __name__ == "__main__":
    matplotlib.use("Agg")
    main()
