# wm811k_spc.py
# 분류 결과 위에 SPC 관리도를 붙인다 - 패턴별 p 관리도 + 저신뢰 비율 관리도 + EWMA,
# 그룹(챔버/슬롯) 층화, 부품 교체/PM 이벤트 대조, 현장용 알람 요약 보고서
#
# 배경
#   웨이퍼 한 장의 판정은 wafer_pattern_classifier(규칙 분류기) 또는 wm811k_validate(RF)가 한다.
#   이 스크립트는 그 위 단계다. 판정 결과를 시간 순서로 부분군(subgroup)에 묶어
#   "이 패턴의 비율이 평소보다 늘고 있는가"를 관리도로 본다. 한 장씩은 정상 범위인데
#   방향이 한쪽으로 기우는 것(소모품 마모, 챔버 오염 축적)을 잡는 것이 목적이다.
#
#   업계 용어로 옮기면:
#     패턴별 p 관리도  = FDC(fault detection and classification)의 fault detection 지표를
#                        장비 센서가 아니라 결과(웨이퍼 맵) 쪽에서 만든 것
#     Phase I / II     = 한계 설정(limit setting) / 감시(monitoring)
#     EWMA             = run-to-run 드리프트 감시. R2R 제어기가 보정하는 느린 이동을 결과 쪽에서 확인
#     저신뢰 관리도    = 모델 드리프트(model drift) 감시. 분류기가 낡았는지 보는 관리도
#   장비 쪽 FDC/APC 소프트웨어(TEL 의 경우 Ingenio 가 APC/FDC 상표, TELeMetrics 가 원격 모니터링
#   서비스 - 2016년 보도 기준, 2015년 출시)가 센서 데이터를 다루고, 이 스크립트는 결과 데이터를 다룬다.
#   --time-col / --event-col 로 둘을 같은 시간축에 놓는 것이 결합 지점이다. 내부 구현은 모른다.
#
#   SEMI E10 관점: 장비 상태는 예정 정지(scheduled downtime, PM)와 비예정 정지(unscheduled
#   downtime)로 나뉜다. 여기서 상승 알람은 "소모품이 수명에 가까워지고 있다"는 조기 신호이므로,
#   그대로 두면 비예정 정지가 될 사건을 예정 정지(PM 앞당기기, 부품 선수배)로 바꾸는 데 쓴다.
#   알람 한 건의 가치는 탐지 자체가 아니라 '비예정 -> 예정' 전환에 있다.
#
# 무엇을 하나
#   [p 관리도]  부분군마다 패턴 X로 판정된 웨이퍼 비율. 부분군 크기 n_i가 달라도
#               한계를 n_i마다 다시 계산한다: p_bar +- 3*sqrt(p_bar(1-p_bar)/n_i)
#               정규 근사 조건은 n*p_bar >= 5 와 n*(1-p_bar) >= 5 둘 다. 드문 패턴은
#               부분군을 기본 크기의 배수로 자동으로 키운다. x축은 부분군 번호가 아니라
#               웨이퍼 순번이라 크기가 달라도 같은 축에 놓인다.
#   [분모]      예측 CSV 에 CLEAN(또는 none) 판정이 있으면 분모가 '검사한 전체 웨이퍼'인
#               발생률 관리도다. 없으면 분모가 '결함 웨이퍼'인 점유율 관리도가 되는데,
#               점유율은 합이 1이라 한 패턴이 오르면 다른 패턴이 기계적으로 내려간다
#               (구성비 효과). 어느 쪽인지 자동 판정해 제목과 콘솔에 적고, 하강 알람은
#               기본으로 점검 항목에서 뺀다(--up-only, alarms.csv 의 note 열에는 남긴다).
#   [저신뢰 p]  confidence < 임계값인 웨이퍼 비율. 임계값을 주지 않으면 baseline 구간의
#               하위 분위수(--conf-quantile, 기본 0.10)로 잡는다. 모델·클래스 수에 따라
#               확률 분포가 달라 고정 임계값은 의미가 없기 때문이다.
#   [Laney p']  로트 사이 변동이 이항 분산보다 크면(과산포) 보통 p 관리도는 계속 헛울린다.
#               baseline z 점수의 이동 범위로 sigma_z 를 재서 한계를 그만큼 넓힌다.
#               baseline 부분군이 20개 미만이면 추정이 불안정하므로 보정을 생략하고 표시한다.
#   [EWMA]      z 점수의 지수가중 이동평균(lambda 0.2, L 2.86). 0.5~1 sigma 의 작은 이동을
#               3 sigma 규칙보다 빨리 잡는다.
#   [fail_frac] 예측 CSV 에 불량 비율 열이 있으면 부분군 평균의 I-MR 관리도도 그린다.
#               세정 베이스라인 결함 밀도처럼 '패턴 없는 전체 수준'을 감시하는 용도.
#   [--group-col] chamber/tool/slot 같은 열로 층화해 'EDGE_RING@B' 식으로 따로 그리고,
#               그룹 간 발생률 차이의 카이제곱 p 값을 낸다. 한 챔버의 드리프트는 전체
#               관리도에서는 희석되므로 층화가 먼저다(현장 순서 6번 '공통성 분석').
#   [--event-col] 부품 교체·PM 같은 이벤트가 적힌 열을 그림에 세로 점선으로 표시하고,
#               상승 알람의 첫 탐지 시점과 가장 가까운 이전 이벤트의 거리(웨이퍼 수)를 낸다
#               (현장 순서 7번 '언제부터인가').
#   [--anonymize] 로트명·그룹 ID 를 키드 해시(blake2b 8바이트 = 16 hex)로 치환한다. 매핑 표는 저장하지
#               않는다. 키는 환경변수 WM811K_ANON_KEY(또는 --anon-key-env 로 지정한 변수)에서 읽고,
#               없으면 실행마다 새로 뽑는다. 초동·중간·종결 보고나 로트 리포트처럼 여러 실행의 산출물을
#               서로 대조하려면 같은 키를 써야 한다. 키는 저장소·보고서에 넣지 않는다.
#               고객 팹 데이터를 보고서에 담을 때 기밀 취급용.
#   [보고서]    spc_<stem>_report.md 에 데이터 범위, 관리도 종류, baseline 알람률, 패턴별
#               중심선->최근값, 첫 탐지 규칙·시점, 감시 알람 점 수(규칙·연속 여부), 이벤트 거리,
#               점검 항목, 대조할 장비 측 로그를 적는다. R1 1점뿐인 단발 알람에는 점검 목록 대신
#               '다음 부분군 확인 후 조치' 한 줄만 쓴다(1점 허위 알람과 추세를 구분하기 위해).
#               alarms.csv 에는 현장 기록용 빈 열(acknowledged_at, action, verified_at)을 둔다.
#
# 규칙 (Western Electric)
#   R1  3σ 밖 1점            R2  연속 3점 중 2점이 같은 쪽 2σ 밖
#   R3  연속 5점 중 4점이 같은 쪽 1σ 밖    R4  연속 8점이 중심선 같은 쪽
#
# 왜
#   Phase I / Phase II: 한계는 앞부분(기본 50%)의 안정 구간(baseline)에서만 잡고 나머지를
#   감시한다. 전체로 한계를 잡으면 이상이 한계 안으로 흡수된다. baseline 안에서 규칙이
#   울리면 그 구간이 안정이 아니었다는 뜻이므로 따로 보고한다.
#
# 한계
#   WM-811K 에는 시각·챔버·슬롯이 없다. 기본값은 CSV 의 행 순서를 시간의 대리로 쓰고,
#   실제 팹 데이터라면 --time-col 로 시각 열을 지정한다. WM-811K 의 행 순서는 제품·로트
#   블록 순서라 그대로 돌리면 baseline 알람률이 수십 % 가 되며 스크립트가 이를 경고한다.
#   --demo 는 합성이다. 탐지 로직이 도는지 보는 용도이며 탐지 성능의 근거가 아니다.
#   baseline 부분군이 3개 미만인 패턴(드문 패턴, 짧은 baseline)은 감시하지 않고 사유를 적는다.
#
# 입력
#   wm811k_evaluate.py 의 wm811k_predictions.csv (score 열: 규칙 분류기 휴리스틱 점수) 또는
#   wm811k_validate.py --export-predictions 의 test_predictions.csv (confidence 열: RF 확률 최댓값).
#   lot, y_pred 열이 필수. confidence(없으면 score 를 별칭으로 사용), fail_frac, 시각·그룹·이벤트 열은 선택.
#
# 사용법
#   python wm811k_spc.py --demo                                   # 합성 시퀀스 (발생률 관리도)
#   python wm811k_spc.py --demo --group-col chamber --event-col event
#   python wm811k_spc.py test_predictions.csv --time-col process_end_time --group-col chamber \
#                        --event-col pm_event --anonymize --lang en
#   WM811K_ANON_KEY=... python wm811k_spc.py test_predictions.csv --anonymize     # 여러 실행에서 같은 익명 ID
#
# 구조: 1 입력 정리 -> 2 관리도 계산 -> 3 보고(표·그림·md) -> 4 데모 -> 5 실행(main 은 단계 함수를 잇기만 한다)

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import matplotlib.transforms as mtransforms
import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency

from _fonts import setup_korean_font
from wafer_pattern_classifier import ACTION_DETAIL, ACTIONS   # 조치 플레이북의 단일 소스 (first_checks, tool_evidence ...)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
CLASSES = ["CENTER", "DONUT", "EDGE_LOC", "EDGE_RING",
           "LOC", "NEAR_FULL", "RANDOM", "SCRATCH"]
CLEAN_LABELS = {"CLEAN", "none", "NONE", "None"}

# 익명화: blake2b 키드 해시. 8바이트(16 hex)다. 4바이트(8 hex)면 생일 충돌 확률이 8,047로트 0.8%,
# WM-811K 전체 로트 수 46,293 에서 22% 라 서로 다른 로트가 한 ID 로 합쳐질 수 있다(8바이트면 1e-10 수준).
# 그래도 anonymize_ids 는 충돌을 검사해 멈춘다. 키는 환경변수 ANON_KEY_ENV 에서 읽는다(여러 실행의 산출물 대조용).
ANON_DIGEST_SIZE = 8
ANON_KEY_ENV = "WM811K_ANON_KEY"

EWMA_LAMBDA = 0.2
# lambda=0.2, L=2.86 -> 관리 상태 ARL0 ~ 370 (마르코프 체인 자체 계산 371; 3 sigma 규칙 R1 과 같은 수준).
# ARL0 ~ 500 짝은 (0.05, 2.615) (0.10, 2.814) (0.20, 2.962) (0.25, 2.998) (Lucas & Saccucci 1990 표 값을
# 같은 계산으로 재현). 이전 값 2.7 은 ARL0 ~ 240 으로 허위 알람이 잦았다. 값 변경 시 docs/spc.md 9절 재측정.
EWMA_L = 2.86
MIN_EXPECTED = 5.0        # 정규 근사 조건 n*p_bar >= 5 와 n*(1-p_bar) >= 5
LANEY_MIN_BASE = 20       # 이보다 baseline 부분군이 적으면 Laney 보정 생략 (이동 범위 추정이 불안정)
MIN_BASE_GROUPS = 3       # baseline 부분군이 이보다 적으면 그 관리도는 그리지 않는다
MIN_MONITOR_GROUPS = 2

# 색은 wafer_map_visualizer 와 맞춘다. 알람은 색만이 아니라 마커 모양으로도 구분한다.
INK, MUTED, LIMIT = "#455A64", "#78909C", "#B0BEC5"
BASELINE_BG, EVENT_COLOR = "#ECEFF1", "#00897B"
ALARM_STYLE = {                # rule -> (marker, color)
    "R1": ("o", "#F44336"), "R2": ("^", "#FB8C00"), "R3": ("v", "#FB8C00"),
    "R4": ("s", "#8E24AA"), "EWMA": ("D", "#1565C0"),
}

LABELS: dict[str, dict[str, str]] = {
    "ko": {
        "xlabel": "웨이퍼 순번 (시간 순서)", "baseline": "baseline (한계 산출 구간)",
        "R1": "R1 3σ 밖", "R2": "R2 2/3점 2σ 밖", "R3": "R3 4/5점 1σ 밖", "R4": "R4 8점 한쪽", "EWMA": "EWMA",
        "subgroup": "부분군", "wafers": "장", "alarms": "감시 구간 알람", "none": "없음",
        "event": "이벤트", "laney_skipped": "Laney 생략(n_base={k}<20)",
        "incidence": "발생률 관리도 (분모 = 전체 웨이퍼)",
        "share": "점유율 관리도 (분모 = 결함 웨이퍼; 한 패턴이 오르면 다른 패턴은 기계적으로 내려간다)",
        "demo_title": "SPC 데모 - 합성 시퀀스 (웨이퍼 {d}부터 EDGE_RING 드리프트, {l}부터 저신뢰 증가, "
                      "{s}부터 SCRATCH 계단; 모두 B 챔버에만)",
        "file_title": "SPC - {name} ({order})",
        "order_rows": "행 순서를 시간의 대리로 사용", "order_col": "{col} 열로 정렬",
        "h_first": "감시 구간 상승 알람 - 규칙별 첫 탐지 시점 (웨이퍼 순번)",
        "h_first_all": "감시 구간 알람(상승+하강) - 규칙별 첫 탐지 시점 (웨이퍼 순번)",
        "h_event": "상승 알람 첫 탐지 시점과 가장 가까운 이전 이벤트의 거리 (웨이퍼 수)",
        "h_group": "그룹 간 발생률 차이 - 감시 구간 비율과 카이제곱 p 값",
        "h_actions": "상승 알람이 있는 패턴과 점검 항목",
        "tool_evidence": "대조할 장비 측 로그",
        # 보고서
        "r_title": "SPC 알람 요약", "r_input": "입력", "r_range": "데이터 범위", "r_kind": "관리도 종류",
        "r_settings": "설정", "r_baseline": "baseline 알람률", "r_up": "상승 알람 패턴",
        "r_chart": "관리도", "r_center": "중심선 -> 최근 부분군", "r_first": "첫 탐지 (규칙, 웨이퍼 순번)",
        "r_evdist": "직전 이벤트와의 거리", "r_checks": "점검 항목", "r_lowconf": "저신뢰 경고",
        "r_dropped": "감시하지 않은 관리도", "r_figure": "그림", "r_none_up": "상승 알람 없음.",
        "r_synthetic": "이 보고서는 합성 데이터로 만든 것이다. 탐지 로직 확인용이며 공정·장비에 대한 정보나 성능 근거가 아니다.",
        "r_fields": "현장 기록: alarms.csv 의 acknowledged_at / action / verified_at 열에 확인 시각, 조치, 조치 후 복귀 확인 시각을 적는다.",
        "r_down_note": "하강 알람 {n}건은 점검 대상에서 제외했다 (alarms.csv note 열 참조).",
        "r_lowconf_text": "LOW_CONFIDENCE 상승: 분류기가 헷갈리는 웨이퍼가 늘었다. 새 패턴 출현 또는 분류기 노후 신호이므로 "
                          "저신뢰 웨이퍼를 직접 검토하고, 그 전까지 다른 패턴 관리도의 해석을 보류한다.",
        "r_group": "그룹 간 비교",
        "r_points": "감시 알람 점 수 (규칙; 연속)", "single": "단발", "run": "연속 {k}점",
        "r_single": "단발 알람(R1 1점) - 점검 목록 대신 다음 부분군을 확인한 뒤 조치. 재발하면 추세로 본다.",
        "r_no_events": "이벤트 없음 (--event-col 열이 전부 비어 있다)",
    },
    "en": {
        "xlabel": "wafer sequence (time order)", "baseline": "baseline (limit-setting window)",
        "R1": "R1 beyond 3σ", "R2": "R2 2 of 3 beyond 2σ", "R3": "R3 4 of 5 beyond 1σ", "R4": "R4 8 on one side", "EWMA": "EWMA",
        "subgroup": "subgroup", "wafers": " wafers", "alarms": "monitor alarms", "none": "none",
        "event": "event", "laney_skipped": "Laney skipped (n_base={k}<20)",
        "incidence": "incidence chart (denominator = all wafers)",
        "share": "share chart (denominator = defective wafers; one pattern rising pushes the others down)",
        "demo_title": "SPC demo - synthetic sequence (EDGE_RING drift from wafer {d}, low-confidence rise from {l}, "
                      "SCRATCH step from {s}; all in chamber B only)",
        "file_title": "SPC - {name} ({order})",
        "order_rows": "row order used as time proxy", "order_col": "sorted by {col}",
        "h_first": "Monitor-window upward alarms - first detection per rule (wafer index)",
        "h_first_all": "Monitor-window alarms (up+down) - first detection per rule (wafer index)",
        "h_event": "Distance from first upward detection to the nearest preceding event (wafers)",
        "h_group": "Between-group incidence - monitor-window rates and chi-square p",
        "h_actions": "Patterns with upward alarms and their checks",
        "tool_evidence": "tool-side logs to cross-check",
        "r_title": "SPC alarm summary", "r_input": "Input", "r_range": "Data range", "r_kind": "Chart type",
        "r_settings": "Settings", "r_baseline": "Baseline alarm rate", "r_up": "Patterns with upward alarms",
        "r_chart": "Chart", "r_center": "center -> latest subgroup", "r_first": "First detection (rule, wafer index)",
        "r_evdist": "Distance from last event", "r_checks": "Checks", "r_lowconf": "Low-confidence warning",
        "r_dropped": "Charts not monitored", "r_figure": "Figure", "r_none_up": "No upward alarms.",
        "r_synthetic": "This report was produced from synthetic data. It verifies the detection logic only and says nothing about any process, tool or detection performance.",
        "r_fields": "Field record: fill acknowledged_at / action / verified_at in alarms.csv with the time acknowledged, the action taken and the time the chart was confirmed back to baseline.",
        "r_down_note": "{n} downward alarm(s) were excluded from the checks (see the note column in alarms.csv).",
        "r_lowconf_text": "LOW_CONFIDENCE rising: the classifier is unsure about more wafers. This signals a new pattern or a stale model; "
                          "review the low-confidence wafers directly and hold interpretation of the other charts until then.",
        "r_group": "Between-group comparison",
        "r_points": "Monitor alarm points (rules; run)", "single": "single", "run": "run of {k}",
        "r_single": "Single-point alarm (one R1) - confirm with the next subgroup before acting; no checklist. Treat a repeat as a trend.",
        "r_no_events": "No events (the --event-col column is entirely empty)",
    },
}


# ──────────────────────────────────────────
# 1. 입력 정리
# ──────────────────────────────────────────
def load_predictions(path: Path, time_col: str | None = None, verbose: bool = True) -> pd.DataFrame:
    """예측 CSV 를 읽어 시간 순서로 정렬한다. confidence 가 없고 score 가 있으면 score 를 별칭으로 쓴다."""
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
    conf_source = "confidence" if "confidence" in df.columns else None
    if conf_source is None and "score" in df.columns:
        df["confidence"] = df["score"].astype(float)
        conf_source = "score"
        if verbose:
            print("[주의] confidence 열이 없어 score 열을 대신 쓴다: 규칙 분류기 휴리스틱 점수, 확률 아님. "
                  "LOW_CONFIDENCE 관리도는 '규칙이 덜 확신한 웨이퍼의 비율'로 읽어라.")
    df = df.reset_index(drop=True)
    df.attrs["confidence_source"] = conf_source
    return df


def chart_mode(df: pd.DataFrame) -> str:
    """예측에 CLEAN/none 이 있으면 'incidence'(분모 = 전체 웨이퍼), 없으면 'share'(분모 = 결함 웨이퍼)."""
    return "incidence" if df["y_pred"].isin(CLEAN_LABELS).any() else "share"


def anon_key_from_env(name: str = ANON_KEY_ENV) -> bytes | None:
    """환경변수 name 의 값을 해시 키(32바이트)로. 변수가 없거나 비어 있으면 None.
    값을 그대로 쓰지 않고 sha256 으로 접는 이유: blake2b 키는 64바이트 이하여야 하고, 길이에 상관없이 같은 취급을 하기 위해."""
    v = os.environ.get(name, "")
    return hashlib.sha256(v.encode("utf-8")).digest() if v else None


def resolve_anon_key(env_name: str | None) -> tuple[bytes | None, str]:
    """--anon-key-env 처리. (키 또는 None, 콘솔용 근거 문자열).
    env_name 을 명시했는데 변수가 비어 있으면 멈춘다(조용히 무작위 키로 떨어지면 산출물 대조가 깨진 줄 모른다).
    명시하지 않으면 기본 변수 ANON_KEY_ENV 가 있을 때만 쓰고, 없으면 실행마다 새 키."""
    name = env_name or ANON_KEY_ENV
    key = anon_key_from_env(name)
    if key is None and env_name:
        sys.exit(f"--anon-key-env {env_name}: 환경변수가 없거나 비어 있다. 같은 사안의 보고는 같은 키로 익명화해야 "
                 f"산출물 간 로트·그룹 ID 가 맞는다.")
    return key, (f"환경변수 {name}, 여러 실행에서 같은 ID" if key else f"실행마다 새 키 (환경변수 {name} 없음; 이 실행 안에서만 일관)")


def anonymize_ids(df: pd.DataFrame, cols: list[str], salt: bytes | None = None) -> pd.DataFrame:
    """지정 열의 값을 키드 해시(ANON_DIGEST_SIZE 바이트 = 16 hex)로 치환한다. 매핑 표는 저장하지 않는다.

    salt 가 없으면 실행마다 새로 뽑는다(실행 사이에 같은 ID 가 필요하면 resolve_anon_key 로 환경변수 키를 넘긴다).
    같은 열 안에서 서로 다른 값이 같은 해시가 되면(충돌) 두 로트가 한 로트로 집계되므로 ValueError 로 멈춘다.
    """
    salt = os.urandom(16) if salt is None else salt
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            continue
        vals = out[c].astype(str)
        table = {v: hashlib.blake2b(v.encode("utf-8"), key=salt, digest_size=ANON_DIGEST_SIZE).hexdigest()
                 for v in pd.unique(vals)}
        if len(set(table.values())) != len(table):
            raise ValueError(f"{c}: 익명화 해시 충돌 ({len(table)}개 값, {ANON_DIGEST_SIZE}바이트) - "
                             f"키(salt)를 바꾸거나 ANON_DIGEST_SIZE 를 늘려라")
        out[c] = vals.map(table)
    return out


def resolve_conf_threshold(df: pd.DataFrame, n_base_rows: int, threshold: float | None,
                           quantile: float) -> tuple[float | None, str]:
    """--conf-threshold 가 없으면 baseline 구간 confidence 의 하위 분위수를 쓴다. (값, 근거 문자열) 반환."""
    if "confidence" not in df.columns:
        return None, ""
    if threshold is not None:
        return float(threshold), "--conf-threshold"
    base = df["confidence"].to_numpy(float)[:n_base_rows]
    base = base[np.isfinite(base)]
    if len(base) == 0:
        return None, ""
    return float(np.quantile(base, quantile)), f"baseline q{quantile:.2f}"


def chunk_ids(df: pd.DataFrame, target: int, by_lot: bool) -> np.ndarray:
    """행을 시간 순서대로 크기 >= target 인 부분군에 묶는다. 부분군 번호 배열을 반환.

    by_lot=True 면 로트를 쪼개지 않고 연속 로트를 target 이 될 때까지 합친다
    (한 로트가 target 보다 크면 그 로트 하나가 부분군이 된다).
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


def _lot_label(s: pd.Series) -> str:
    u = pd.unique(s)
    return ",".join(map(str, u[:3])) + ("..." if len(u) > 3 else "")


def summarize(lot: np.ndarray, gid: np.ndarray, idx: np.ndarray, hit=None) -> pd.DataFrame:
    """부분군별 n, 조건 충족 수, 끝 웨이퍼 순번(전역), 로트 표기."""
    d = pd.DataFrame({"gid": gid, "lot": lot, "idx": idx,
                      "hit": hit if hit is not None else np.zeros(len(gid), dtype=int)})
    d = d[d["gid"] >= 0]
    g = d.groupby("gid", sort=True)
    out = pd.DataFrame({"n": g.size(), "count": g["hit"].sum().astype(int),
                        "end_idx": g["idx"].max(), "lots": g["lot"].agg(_lot_label)})
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
    alarms: dict[str, np.ndarray]     # rule -> bool 배열 (규칙이 완성되는 점에 표시)
    ucl: np.ndarray
    lcl: np.ndarray
    end_idx: np.ndarray        # 부분군 끝 웨이퍼 순번 (x축)
    n: np.ndarray              # 부분군 크기
    n_base: int                # baseline 부분군 수
    kind: str = "p"            # "p" | "mean"
    sigma_z: float = 1.0       # Laney 과산포 계수 (1이면 보정 없음)
    laney_skipped: bool = False   # baseline 부분군이 적어 보정을 생략했는가
    lots: tuple[str, ...] = ()    # 부분군별 로트 표기
    base: str = ""             # 그룹 접미사를 뺀 패턴 이름
    group: str | None = None   # --group-col 층 (없으면 None)


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


def _finish(name, value, center, sigma, S, n_base, kind, clip=None, sigma_z=1.0, laney_skipped=False):
    z = (value - center) / sigma
    e, lim = ewma_chart(z)
    alarms = western_electric(z)
    alarms["EWMA"] = np.abs(e) > lim
    ucl, lcl = center + 3 * sigma, center - 3 * sigma
    if clip is not None:
        ucl, lcl = np.clip(ucl, *clip), np.clip(lcl, *clip)
    lots = tuple(S["lots"].astype(str)) if "lots" in S.columns else ()
    return Chart(name, value, center, sigma, z, e, lim, alarms, ucl, lcl,
                 end_idx=S["end_idx"].to_numpy(), n=S["n"].to_numpy(), n_base=n_base,
                 kind=kind, sigma_z=sigma_z, laney_skipped=laney_skipped, lots=lots, base=name)


def laney_factor(z_base: np.ndarray) -> float:
    """Laney p': baseline z 점수의 이동 범위 평균 / d2(1.128).

    1 보다 작으면 1 로 고정한다 - 의도적 보수화(Laney 원안과 다름). 원안은 과소산포(sigma_z < 1)도
    반영해 한계를 좁히지만, 여기서는 이항 한계보다 좁히지 않아 거짓 알람 쪽으로 기울지 않게 한다.
    """
    if len(z_base) < 3:
        return 1.0
    return max(1.0, float(np.abs(np.diff(z_base)).mean() / 1.128))


def p_chart(name: str, S: pd.DataFrame, n_base: int, laney: bool = True) -> Chart | None:
    count, n = S["count"].to_numpy(), S["n"].to_numpy()
    p_bar = float(count[:n_base].sum() / n[:n_base].sum())
    if p_bar <= 0 or p_bar >= 1:
        return None                              # baseline에 없는(또는 전부인) 패턴은 감시 불가
    sigma = np.sqrt(p_bar * (1 - p_bar) / n)
    laney_on = laney and n_base >= LANEY_MIN_BASE
    sigma_z = laney_factor(((count / n - p_bar) / sigma)[:n_base]) if laney_on else 1.0
    return _finish(name, count / n, p_bar, sigma * sigma_z, S, n_base, "p",
                   clip=(0, 1), sigma_z=sigma_z, laney_skipped=laney and not laney_on)


def mean_chart(name: str, S: pd.DataFrame, x: np.ndarray, n_base: int) -> Chart | None:
    """부분군 평균의 I-MR 관리도. σ는 baseline 이동 범위 평균 / d2(=1.128)."""
    base = x[:n_base]
    if len(base) < MIN_BASE_GROUPS:
        return None
    center = float(base.mean())
    sigma_scalar = np.abs(np.diff(base)).mean() / 1.128
    if sigma_scalar <= 0:
        return None
    sigma = np.full(len(x), sigma_scalar)
    return _finish(name, x, center, sigma, S, n_base, "mean")


def baseline_groups(S: pd.DataFrame, n_base_rows: int) -> int:
    """끝 순번이 baseline 행 범위 안에 있는 부분군 수. 감시 구간을 끌어와 채우지 않는다."""
    return int((S["end_idx"] < n_base_rows).sum())


def build_charts(df: pd.DataFrame, classes: list[str], base_size: int, by_lot: bool,
                 n_base_rows: int, conf_threshold: float | None, laney: bool = True,
                 idx: np.ndarray | None = None, suffix: str = "",
                 ) -> tuple[list[Chart], dict[str, int], dict[str, str]]:
    """패턴마다 n*p >= 5, n*(1-p) >= 5 가 되도록 부분군 크기를 base_size 의 배수로 키워 관리도를 만든다.

    idx 는 각 행의 전역 웨이퍼 순번(층화 시 부분 집합에 대해 전달). baseline 은 idx < n_base_rows.
    반환: (관리도 목록, 부분군 크기, 감시하지 않은 관리도와 사유).
    """
    charts, sizes, dropped = [], {}, {}
    idx = np.arange(len(df)) if idx is None else np.asarray(idx)
    in_base = idx < n_base_rows
    y = df["y_pred"].to_numpy()
    lot = df["lot"].to_numpy()
    targets = {c: (y == c) for c in classes}
    if "confidence" in df.columns and conf_threshold is not None:
        targets["LOW_CONFIDENCE"] = df["confidence"].to_numpy(float) < conf_threshold
    for name, hit in targets.items():
        label = name + suffix
        if in_base.sum() == 0:
            dropped[label] = "baseline 행 없음"
            continue
        p0 = float(hit[in_base].mean())
        if p0 <= 0:
            dropped[label] = "baseline 에 없음"
            continue
        if p0 >= 1:
            dropped[label] = "baseline 전부가 이 패턴"
            continue
        k = int(np.ceil(MIN_EXPECTED / min(p0, 1 - p0) / base_size))
        size = k * base_size
        gid = chunk_ids(df, size, by_lot)
        S = summarize(lot, gid, idx, hit.astype(int))
        n_base = baseline_groups(S, n_base_rows)
        if n_base < MIN_BASE_GROUPS:
            dropped[label] = f"baseline 부분군 {n_base}개 < {MIN_BASE_GROUPS} (부분군 {size}장, p0={p0:.4f})"
            continue
        if len(S) - n_base < MIN_MONITOR_GROUPS:
            dropped[label] = f"감시 부분군 {len(S) - n_base}개 < {MIN_MONITOR_GROUPS} (부분군 {size}장)"
            continue
        ch = p_chart(label, S, n_base, laney)
        if ch is None:
            dropped[label] = "baseline p_bar 가 0 또는 1"
            continue
        ch.base, ch.group = name, (suffix[1:] if suffix else None)
        charts.append(ch)
        sizes[label] = size
    if "fail_frac" in df.columns:
        label = "FAIL_FRAC_MEAN" + suffix
        gid = chunk_ids(df, base_size, by_lot)
        S = summarize(lot, gid, idx)
        x = pd.Series(df["fail_frac"].to_numpy(float)[gid >= 0]).groupby(gid[gid >= 0]).mean().to_numpy()
        n_base = baseline_groups(S, n_base_rows)
        ch = mean_chart(label, S, x, n_base) if len(S) - n_base >= MIN_MONITOR_GROUPS else None
        if ch is None:
            dropped[label] = f"baseline 부분군 {n_base}개 또는 감시 부분군 부족"
        else:
            ch.base, ch.group = "FAIL_FRAC_MEAN", (suffix[1:] if suffix else None)
            charts.append(ch)
            sizes[label] = base_size
    return charts, sizes, dropped


def build_all(df: pd.DataFrame, classes: list[str], base_size: int, by_lot: bool, n_base_rows: int,
              conf_threshold: float | None, laney: bool = True, group_col: str | None = None,
              ) -> tuple[list[Chart], dict[str, int], dict[str, str]]:
    """group_col 이 있으면 값별로 층화해 'PATTERN@group' 관리도를 만든다. 없으면 build_charts 와 같다."""
    df = df.reset_index(drop=True)
    if not group_col:
        return build_charts(df, classes, base_size, by_lot, n_base_rows, conf_threshold, laney)
    if group_col not in df.columns:
        sys.exit(f"--group-col {group_col} 열이 없다.")
    charts, sizes, dropped = [], {}, {}
    idx_all = np.arange(len(df))
    for g, sub in df.groupby(df[group_col].astype(str), sort=True):
        c, s, d = build_charts(sub.reset_index(drop=True), classes, base_size, by_lot, n_base_rows,
                               conf_threshold, laney, idx=idx_all[sub.index.to_numpy()], suffix=f"@{g}")
        charts += c
        sizes.update(s)
        dropped.update(d)
    return charts, sizes, dropped


def group_rate_test(df: pd.DataFrame, group_col: str, classes: list[str], n_base_rows: int) -> pd.DataFrame:
    """그룹별 패턴 발생률(감시 구간)과 그룹 간 차이의 카이제곱 p 값(baseline / 감시 구간 각각)."""
    df = df.reset_index(drop=True)
    grp = df[group_col].astype(str)
    groups = sorted(grp.unique())
    mon = np.arange(len(df)) >= n_base_rows
    rows = []
    for c in classes:
        hit = (df["y_pred"] == c).to_numpy()
        row = {"pattern": c}
        for g in groups:
            m = mon & (grp == g).to_numpy()
            row[f"rate@{g}"] = float(hit[m].mean()) if m.any() else np.nan
        for phase, mask in (("baseline", ~mon), ("monitor", mon)):
            tab = pd.crosstab(grp[mask], hit[mask])
            if tab.shape[0] < 2 or tab.shape[1] < 2:
                row[f"p_{phase}"] = np.nan
            else:
                row[f"p_{phase}"] = float(chi2_contingency(tab.to_numpy())[1])
        rows.append(row)
    return pd.DataFrame(rows)


# ──────────────────────────────────────────
# 3. 보고
# ──────────────────────────────────────────
def alarm_table(charts: list[Chart], mode: str = "share") -> pd.DataFrame:
    """모든 알람을 한 표로. 하강 알람에는 note 를 달고, 현장 기록용 빈 열을 둔다."""
    rows = []
    for ch in charts:
        for rule, mask in ch.alarms.items():
            for i in np.nonzero(mask)[0]:
                up = ch.z[i] > 0
                if up:
                    note = ""
                elif mode == "share" and ch.base in CLASSES:
                    note = "down: 다른 패턴 상승의 반작용 가능"
                else:
                    note = "down: 감소 방향 (점검 대상 아님)"
                rows.append({"chart": ch.name, "subgroup": int(i), "wafer_end_idx": int(ch.end_idx[i]),
                             "phase": "baseline" if i < ch.n_base else "monitor",
                             "rule": rule, "value": float(ch.value[i]), "z": float(ch.z[i]),
                             "direction": "up" if up else "down", "note": note,
                             "lots": ch.lots[i] if i < len(ch.lots) else "",
                             "acknowledged_at": "", "action": "", "verified_at": ""})
    cols = ["chart", "subgroup", "wafer_end_idx", "phase", "rule", "value", "z", "direction", "note",
            "lots", "acknowledged_at", "action", "verified_at"]
    return pd.DataFrame(rows, columns=cols).sort_values(["chart", "wafer_end_idx"]).reset_index(drop=True)


def first_detection(alarms: pd.DataFrame, up_only: bool = True) -> pd.DataFrame:
    """감시 구간에서 규칙별로 처음 울린 시점(웨이퍼 순번). '얼마나 빨리 잡았나'를 본다."""
    mon = alarms[alarms["phase"] == "monitor"]
    if up_only:
        mon = mon[mon["direction"] == "up"]
    if mon.empty:
        return pd.DataFrame(columns=["chart", "rule", "first_wafer_idx"])
    return (mon.groupby(["chart", "rule"])["wafer_end_idx"].min()
            .rename("first_wafer_idx").reset_index())


def event_marks(df: pd.DataFrame, event_col: str, group_col: str | None = None) -> pd.DataFrame:
    """이벤트 열이 비어 있지 않은 행 -> (idx, label, group)."""
    if event_col not in df.columns:
        sys.exit(f"--event-col {event_col} 열이 없다.")
    s = df[event_col]
    mask = s.notna() & (s.astype(str).str.strip() != "")
    out = pd.DataFrame({"idx": np.nonzero(mask.to_numpy())[0],
                        "label": s[mask].astype(str).str.strip().to_numpy()})
    out["group"] = df.loc[mask, group_col].astype(str).to_numpy() if group_col else None
    return out.reset_index(drop=True)


def event_distance(charts: list[Chart], alarms: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    """상승 알람이 있는 관리도마다 첫 탐지 시점과 가장 가까운 이전 이벤트(같은 그룹 우선)의 거리."""
    fd = first_detection(alarms, up_only=True)
    rows = []
    for ch in charts:
        f = fd[fd["chart"] == ch.name]
        if f.empty:
            continue
        first = int(f["first_wafer_idx"].min())
        rules = ",".join(sorted(f.loc[f["first_wafer_idx"] == first, "rule"]))
        ev = events[events["idx"] <= first]
        if ch.group is not None and events["group"].notna().any():
            ev = ev[ev["group"] == ch.group]
        if ev.empty:
            rows.append({"chart": ch.name, "first_wafer_idx": first, "rules": rules,
                         "event": "", "event_idx": -1, "wafers_since_event": -1})
            continue
        last = ev.loc[ev["idx"].idxmax()]
        rows.append({"chart": ch.name, "first_wafer_idx": first, "rules": rules,
                     "event": str(last["label"]), "event_idx": int(last["idx"]),
                     "wafers_since_event": int(first - last["idx"])})
    return pd.DataFrame(rows, columns=["chart", "first_wafer_idx", "rules", "event", "event_idx", "wafers_since_event"])


def plot_charts(charts: list[Chart], n_base_rows: int, out_png: Path, title: str, lang: str = "ko",
                events: pd.DataFrame | None = None) -> None:
    L = LABELS[lang]
    rows = len(charts)
    fig, axes = plt.subplots(rows, 1, figsize=(12, 2.0 * rows + 1.2), sharex=True,
                             squeeze=False, layout="constrained")
    labeled: set[int] = set()          # 이벤트 라벨은 그 이벤트가 처음 그려지는 축에만 쓴다
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
                m, col = ALARM_STYLE[rule]
                ax.scatter(x[idx], ch.value[idx], marker=m, s=34, color=col,
                           edgecolor="white", linewidth=0.6, zorder=3)
        if events is not None and len(events):
            trans = mtransforms.blended_transform_factory(ax.transData, ax.transAxes)
            for j, ev in events.iterrows():
                if ch.group is not None and ev["group"] is not None and str(ev["group"]) != ch.group:
                    continue
                ax.axvline(ev["idx"], color=EVENT_COLOR, lw=0.9, ls=":", zorder=1)
                if j not in labeled:
                    labeled.add(j)
                    ax.text(ev["idx"], 0.98, f" {ev['label']}", transform=trans, fontsize=7,
                            color=EVENT_COLOR, ha="left", va="top")
        summary = "  ".join(f"{r} {k_}" for r, k_ in n_alarm.items() if k_)
        unit = "p̄" if ch.kind == "p" else "x̄"
        if ch.laney_skipped:
            laney = "   " + L["laney_skipped"].format(k=ch.n_base)
        else:
            laney = f"   σz={ch.sigma_z:.2f}" if ch.sigma_z > 1 else ""
        ax.set_title(f"{ch.name}   {unit}={ch.center:.3f}   {L['subgroup']} {int(np.median(ch.n))}{L['wafers']}{laney}   "
                     f"{L['alarms']}: {summary or L['none']}", loc="left", fontsize=9, color=INK)
        ax.tick_params(labelsize=8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.grid(False)
    axes[-1, 0].set_xlabel(L["xlabel"], fontsize=9)
    handles = [plt.Line2D([], [], marker=m, ls="", color=c, markeredgecolor="white", markersize=6, label=L[r])
               for r, (m, c) in ALARM_STYLE.items()]
    handles.append(matplotlib.patches.Patch(color=BASELINE_BG, label=L["baseline"]))
    if events is not None and len(events):
        handles.append(plt.Line2D([], [], color=EVENT_COLOR, ls=":", label=L["event"]))
    fig.legend(handles=handles, loc="outside lower center", ncol=7, fontsize=8, frameon=False)
    fig.suptitle(title, fontsize=10, color=INK, x=0.01, ha="left", wrap=True)
    fig.savefig(out_png, dpi=130)
    plt.close(fig)


def _detail_list(pattern: str, key: str) -> list[str]:
    """ACTION_DETAIL[pattern][key] 를 문자열 목록으로 (항목이 없으면 빈 목록; 한 줄 문자열 필드는 1원소 목록)."""
    v = ACTION_DETAIL.get(pattern, {}).get(key, [])
    return [v] if isinstance(v, str) else [str(x) for x in v]


def checks_for(pattern: str) -> list[str]:
    """점검 항목: ACTION_DETAIL 의 first_checks, 없으면 ACTIONS 한 줄 요약."""
    return _detail_list(pattern, "first_checks") or ([ACTIONS[pattern]] if pattern in ACTIONS else [])


def alarm_profile(name: str, alarms: pd.DataFrame) -> dict:
    """감시 구간 상승 알람의 모양: 알람 부분군 수, 울린 규칙, 마지막 알람에서 거슬러 센 연속 부분군 수.

    single = 알람 부분군이 하나뿐이고 규칙이 R1 뿐. 연속 규칙(R2-R4)·EWMA 는 정의상 여러 점이 쌓여야 울리므로
    한 부분군에만 표시돼도 단발이 아니다. 단발은 1점 허위 알람일 수 있어 점검 목록 대신 다음 부분군 확인을 권한다.
    """
    m = alarms[(alarms["chart"] == name) & (alarms["phase"] == "monitor") & (alarms["direction"] == "up")]
    subs = sorted(set(m["subgroup"].astype(int)))
    rules = sorted(set(m["rule"]))
    run, expect = 0, (subs[-1] if subs else None)
    for s in reversed(subs):
        if s != expect:
            break
        run, expect = run + 1, s - 1
    return {"points": len(subs), "rules": rules, "run": run, "single": len(subs) == 1 and rules == ["R1"]}


def profile_text(p: dict, lang: str) -> str:
    """alarm_profile -> '13 (EWMA,R1,R2,R3,R4); 연속 9' / '1 (R1); 단발'."""
    L = LABELS[lang]
    tag = L["single"] if p["single"] else (L["run"].format(k=p["run"]) if p["run"] >= 2 else "")
    return f"{p['points']} ({','.join(p['rules'])})" + (f"; {tag}" if tag else "")


@dataclass
class RunContext:
    """write_report 입력. main 의 단계 함수들이 채운다."""
    lang: str
    stem: str
    source: str
    synthetic: bool
    mode: str                              # "incidence" | "share"
    range_text: str
    settings_text: str
    base_rate_text: str
    charts: list[Chart]
    alarms: pd.DataFrame                   # up_only 면 감시 구간 하강 알람은 뺀 표
    n_down: int = 0                        # 점검에서 제외한 하강 알람 수 (up_only 일 때)
    event_dist: pd.DataFrame | None = None
    n_events: int | None = None            # --event-col 을 줬을 때 이벤트 수 (0 = 열이 전부 비어 있음), 안 줬으면 None
    group_table: pd.DataFrame | None = None
    dropped: dict[str, str] = field(default_factory=dict)
    png_name: str = ""


def write_report(path: Path, ctx: RunContext) -> None:
    """spc_<stem>_report.md - 사람이 읽는 알람 요약."""
    L = LABELS[ctx.lang]
    by_name = {ch.name: ch for ch in ctx.charts}
    fd = first_detection(ctx.alarms, up_only=True)
    ev = ctx.event_dist
    ev_by = {} if ev is None or ev.empty else ev.set_index("chart").to_dict("index")
    out = [f"# {L['r_title']} - {ctx.stem}", ""]
    if ctx.synthetic:
        out += [f"> {L['r_synthetic']}", ""]
    out += [f"- {L['r_input']}: {ctx.source}",
            f"- {L['r_range']}: {ctx.range_text}",
            f"- {L['r_kind']}: {L[ctx.mode]}",
            f"- {L['r_settings']}: {ctx.settings_text}",
            f"- {L['r_baseline']}: {ctx.base_rate_text}", ""]
    if ctx.n_events == 0:
        out += [L["r_no_events"], ""]
    up_charts = sorted(set(fd["chart"])) if not fd.empty else []
    profiles = {name: alarm_profile(name, ctx.alarms) for name in up_charts}
    out += [f"## {L['r_up']}", ""]
    if not up_charts:
        out.append(L["r_none_up"])
    else:
        out += [f"| {L['r_chart']} | {L['r_center']} | {L['r_first']} | {L['r_points']} | {L['r_evdist']} |",
                "|---|---|---|---|---|"]
        for name in up_charts:
            ch = by_name[name]
            f = fd[fd["chart"] == name]
            first = int(f["first_wafer_idx"].min())
            rules = ",".join(sorted(f.loc[f["first_wafer_idx"] == first, "rule"]))
            e = ev_by.get(name)
            if e is None:
                dist = "-"
            elif e["event_idx"] < 0:
                dist = "(no prior event)" if ctx.lang == "en" else "(이전 이벤트 없음)"
            else:
                dist = f"{e['event']} @ {e['event_idx']} -> +{e['wafers_since_event']}"
            out.append(f"| {name} | {ch.center:.4f} -> {ch.value[-1]:.4f} | {rules} @ {first} | "
                       f"{profile_text(profiles[name], ctx.lang)} | {dist} |")
        out.append("")
        for name in up_charts:
            ch = by_name[name]
            if ch.base not in CLASSES:
                continue
            out += [f"### {name}", ""]
            if profiles[name]["single"]:
                out += [f"- {L['r_single']}", ""]
                continue
            out += [f"- {L['r_checks']}:"] + [f"  - {c}" for c in checks_for(ch.base)]
            te = _detail_list(ch.base, "tool_evidence")
            if te:
                out += [f"- {L['tool_evidence']}:"] + [f"  - {t}" for t in te]
            out.append("")
    if ctx.n_down:
        out += [L["r_down_note"].format(n=ctx.n_down), ""]
    if any(by_name[n].base == "LOW_CONFIDENCE" for n in up_charts):
        out += [f"## {L['r_lowconf']}", "", L["r_lowconf_text"], ""]
    if ctx.group_table is not None:
        out += [f"## {L['r_group']}", "", "```", ctx.group_table.to_string(index=False, float_format=lambda v: f"{v:.4f}"), "```", ""]
    if ctx.dropped:
        out += [f"## {L['r_dropped']}", ""] + [f"- {k}: {v}" for k, v in ctx.dropped.items()] + [""]
    out += [f"## {L['r_figure']}", "", f"![spc]({ctx.png_name})", "", L["r_fields"], ""]
    path.write_text("\n".join(out), encoding="utf-8")


# ──────────────────────────────────────────
# 4. 데모 - 드리프트를 심은 합성 시퀀스
# ──────────────────────────────────────────
WM811K_COUNTS = [4294, 555, 5189, 9680, 3593, 149, 866, 1193]     # CLASSES 순서의 WM-811K 결함 8종 장수
DEMO = dict(
    # 240 로트 x 25장 = 6,000장, baseline 50% = 0-2999. 시드 3 은 8개 시드(0-7)를 훑어 고른 값이다:
    # 시드 0 은 baseline 의 SCRATCH 발생률 추정이 0.4% 로 낮아 부분군이 1,250장(baseline 2개)이 되어 감시 불가가 된다.
    # 시드별 허위 알람·탐지 지연은 README 의 데모 절에 적는다.
    n_groups=240, n=25, seed=3, clean_frac=0.85,
    drift_start=120, drift_ramp=40, drift_mag=0.12,   # 그룹 120(웨이퍼 3000)부터 40그룹에 걸쳐 B 챔버 CLEAN->EDGE_RING 전환 확률 0 -> 0.12
    lowconf_start=150, lowconf_frac=0.30,              # 그룹 150(웨이퍼 3750)부터 B 챔버 웨이퍼의 30% 가 confidence U(0.3, 0.7)
    step_start=165, step_mag=0.15,                     # 그룹 165(웨이퍼 4125)부터 B 챔버 CLEAN->SCRATCH 전환 확률 0.15
    events={1025: "pm_wet_clean", 2900: "focus_ring_replaced"},   # 웨이퍼 1025(A 챔버 로트), 2900(B 챔버 로트)
)


def demo_predictions(n_groups: int = DEMO["n_groups"], n: int = DEMO["n"], seed: int = DEMO["seed"]) -> pd.DataFrame:
    """발생률 시나리오: 약 85% 가 CLEAN, 나머지 15% 를 WM-811K 라벨 비율로 결함 8종에 나눈다.
    로트는 챔버 A/B 를 번갈아 타고, 드리프트·저신뢰·계단은 모두 B 챔버의 CLEAN 웨이퍼를 바꾸는 식으로
    심어 다른 패턴의 발생률은 건드리지 않는다. 합성이다. 탐지 로직 확인용이며 공정 정보는 없다."""
    rng = np.random.default_rng(seed)
    base = np.array(WM811K_COUNTS, float)
    base = base / base.sum() * (1 - DEMO["clean_frac"])
    probs = np.append(base, DEMO["clean_frac"])
    labels = CLASSES + ["CLEAN"]
    rows = []
    for g in range(n_groups):
        chamber = "B" if g % 2 == 0 else "A"
        y = np.array(rng.choice(labels, size=n, p=probs), dtype=object)
        conf = rng.beta(8, 1.2, size=n)
        if chamber == "B":
            if g >= DEMO["drift_start"]:
                q = DEMO["drift_mag"] * min(1.0, (g - DEMO["drift_start"] + 1) / DEMO["drift_ramp"])
                y[(y == "CLEAN") & (rng.random(n) < q)] = "EDGE_RING"
            if g >= DEMO["step_start"]:
                y[(y == "CLEAN") & (rng.random(n) < DEMO["step_mag"])] = "SCRATCH"
            if g >= DEMO["lowconf_start"]:
                conf = np.where(rng.random(n) < DEMO["lowconf_frac"], rng.uniform(0.3, 0.7, n), conf)
        for i in range(n):
            wid = g * n + i
            rows.append({"sample_id": wid, "lot": f"lot{g:04d}", "chamber": chamber,
                         "event": DEMO["events"].get(wid, ""), "y_pred": y[i], "confidence": float(conf[i])})
    return pd.DataFrame(rows)


def demo_scenario_lines() -> list[str]:
    """콘솔·README 용 시나리오 설명. 숫자는 DEMO 에서 가져오므로 코드와 어긋나지 않는다."""
    n = DEMO["n"]
    base = np.array(WM811K_COUNTS, float)
    base = base / base.sum() * (1 - DEMO["clean_frac"])
    er, sc = base[CLASSES.index("EDGE_RING")], base[CLASSES.index("SCRATCH")]
    er_b = er + DEMO["clean_frac"] * DEMO["drift_mag"]
    sc_b = sc + DEMO["clean_frac"] * (1 - DEMO["drift_mag"]) * DEMO["step_mag"]
    return [
        f"합성 시나리오 (로직 확인용, 성능 아님): 웨이퍼 {DEMO['n_groups'] * n:,}장, 로트 {DEMO['n_groups']}개(로트당 {n}장), "
        f"CLEAN 약 {DEMO['clean_frac']:.0%}, "
        f"결함 8종은 WM-811K 라벨 비율로 나머지 {1 - DEMO['clean_frac']:.0%} 분배, 로트가 챔버 A/B 를 번갈아 탐",
        f"  EDGE_RING 드리프트: 웨이퍼 {DEMO['drift_start'] * n}부터 {DEMO['drift_ramp']}로트({DEMO['drift_ramp'] * n}장)에 걸쳐 "
        f"B 챔버 CLEAN->EDGE_RING 전환 확률 0 -> {DEMO['drift_mag']:.2f} (B 발생률 {er:.3f} -> {er_b:.3f}, 전체 기준 {er:.3f} -> {(er + er_b) / 2:.3f})",
        f"  저신뢰 증가:        웨이퍼 {DEMO['lowconf_start'] * n}부터 B 챔버 웨이퍼의 {DEMO['lowconf_frac']:.0%} 가 confidence U(0.3, 0.7)",
        f"  SCRATCH 계단:       웨이퍼 {DEMO['step_start'] * n}부터 B 챔버 CLEAN->SCRATCH 전환 확률 {DEMO['step_mag']:.2f} "
        f"(B 발생률 {sc:.3f} -> {sc_b:.3f}, 전체 기준 {sc:.3f} -> {(sc + sc_b) / 2:.3f})",
        "  이벤트:             " + ", ".join(f"웨이퍼 {k} '{v}'" for k, v in DEMO["events"].items()),
        "  다른 패턴(CENTER/LOC/EDGE_LOC/DONUT/RANDOM/NEAR_FULL)의 발생률은 바꾸지 않았다.",
    ]


# ──────────────────────────────────────────
# 5. 실행 - parse_args -> load_input -> build -> save_tables -> plot -> print_summary -> write_report
# ──────────────────────────────────────────
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="분류 결과에 SPC 관리도를 붙인다.")
    ap.add_argument("predictions", nargs="?", type=Path, help="예측 CSV (lot, y_pred 필수)")
    ap.add_argument("--demo", action="store_true", help="합성 시퀀스로 탐지 확인 (성능 근거 아님)")
    ap.add_argument("--subgroup", default="25", help="'lot' 또는 기본 부분군 크기 (기본 25). 드문 패턴은 자동으로 배수만큼 키운다")
    ap.add_argument("--min-size", type=int, default=25, help="--subgroup lot 일 때 연속 로트를 이 크기가 될 때까지 합친다")
    ap.add_argument("--baseline-frac", type=float, default=0.5, help="한계를 잡는 앞부분 비율")
    ap.add_argument("--conf-threshold", type=float, default=None,
                    help="저신뢰 임계값. 없으면 baseline 구간 confidence 의 --conf-quantile 분위수")
    ap.add_argument("--conf-quantile", type=float, default=0.10)
    ap.add_argument("--time-col", help="시간 순서로 정렬할 열 (없으면 행 순서)")
    ap.add_argument("--event-col", help="부품 교체·PM 등 이벤트가 적힌 열 (비어 있지 않은 행을 표시)")
    ap.add_argument("--group-col", help="층화할 열 (chamber/tool/slot). 관리도 이름이 'PATTERN@값' 이 된다")
    ap.add_argument("--no-laney", action="store_true", help="Laney 과산포 보정을 끈다 (순수 이항 한계)")
    ap.add_argument("--up-only", action=argparse.BooleanOptionalAction, default=True,
                    help="하강 알람을 콘솔·점검 항목에서 제외 (alarms.csv 에는 note 와 함께 남긴다). 기본 켬")
    ap.add_argument("--anonymize", action="store_true",
                    help=f"로트명·그룹 ID 를 키드 해시({2 * ANON_DIGEST_SIZE}자리)로 치환 (매핑 표 저장 안 함)")
    ap.add_argument("--anon-key-env", metavar="VAR", default=None,
                    help=f"--anonymize 키를 읽을 환경변수 이름. 같은 사안의 초동·중간·종결 보고와 로트 리포트에 같은 키를 쓰면 "
                         f"산출물 간 ID 가 맞는다. 지정하지 않으면 {ANON_KEY_ENV} 가 있을 때 그것, 없으면 실행마다 새 키")
    ap.add_argument("--lang", choices=["ko", "en"], default="ko", help="그림·보고서 언어. 한글 폰트가 없으면 그림만 en 으로")
    ap.add_argument("--classes", nargs="+", default=CLASSES)
    ap.add_argument("--output", type=Path, default=HERE / "spc")
    args = ap.parse_args(argv)
    if not args.demo and not args.predictions:
        ap.error("예측 CSV 경로를 주거나 --demo 를 지정하라.")
    args.by_lot = args.subgroup == "lot"
    args.base_size = args.min_size if args.by_lot else (int(args.subgroup) if args.subgroup.isdigit() else 0)
    if args.base_size < 2:
        ap.error("--subgroup 은 'lot' 또는 2 이상의 정수여야 한다.")
    return args


def load_input(args: argparse.Namespace) -> tuple[pd.DataFrame, str, str]:
    """(시간 순 예측 표, 산출물 stem, 보고서의 입력 표기). --demo 면 시나리오를 찍고, --anonymize 면 여기서 치환한다."""
    if args.demo:
        df = demo_predictions()
        stem, source = "spc_demo", "--demo (synthetic)"
        for line in demo_scenario_lines():
            print(line)
    else:
        df = load_predictions(args.predictions, args.time_col)
        stem, source = "spc_" + args.predictions.stem, args.predictions.name
    if args.anonymize:
        key, key_text = resolve_anon_key(args.anon_key_env)
        cols = ["lot"] + ([args.group_col] if args.group_col else [])
        df = anonymize_ids(df, cols, key)
        print(f"익명화: {'·'.join(cols)} -> {2 * ANON_DIGEST_SIZE}자리 키드 해시 (키: {key_text}; 매핑 표는 저장하지 않음)")
    return df, stem, source


def build(args: argparse.Namespace, df: pd.DataFrame, n_base_rows: int,
          ) -> tuple[list[Chart], dict[str, int], dict[str, str], float | None, str]:
    """저신뢰 임계값을 정하고 관리도를 만든다. 부분군 크기·Laney 계수·감시 불가 사유를 찍는다."""
    conf_threshold, conf_how = resolve_conf_threshold(df, n_base_rows, args.conf_threshold, args.conf_quantile)
    if conf_threshold is not None:
        src = df.attrs.get("confidence_source") or "confidence"
        print(f"저신뢰 임계값: {conf_threshold:.3f} ({conf_how}, 열={src})")
    charts, sizes, dropped = build_all(df, args.classes, args.base_size, args.by_lot, n_base_rows,
                                       conf_threshold, laney=not args.no_laney, group_col=args.group_col)
    if not charts:
        for k, v in dropped.items():
            print(f"  감시 불가 {k}: {v}")
        sys.exit("그릴 관리도가 없다. 데이터가 너무 적거나 baseline에 패턴이 없다.")
    print("부분군 크기 (n*p >= 5, n*(1-p) >= 5 조건):  " + "  ".join(f"{k} {v}" for k, v in sizes.items()))
    over = {ch.name: ch.sigma_z for ch in charts if ch.sigma_z > 1.05}
    if over:
        print("Laney 과산포 계수 sigma_z (로트 간 변동이 이항 분산보다 큰 정도):  "
              + "  ".join(f"{k} {v:.2f}" for k, v in over.items()))
    skipped = [f"{ch.name}(n_base={ch.n_base})" for ch in charts if ch.laney_skipped]
    if skipped:
        print(f"Laney 보정 생략 (baseline 부분군 < {LANEY_MIN_BASE}): " + ", ".join(skipped))
    if dropped:
        print("감시 불가:")
        for k, v in dropped.items():
            print(f"  {k}: {v}")
    return charts, sizes, dropped, conf_threshold, conf_how


def save_tables(out_dir: Path, stem: str, charts: list[Chart], alarms: pd.DataFrame) -> None:
    """<stem>_alarms.csv (현장 기록 열 포함), <stem>_subgroups.csv (부분군별 값·z·EWMA·한계)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    alarms.to_csv(out_dir / f"{stem}_alarms.csv", index=False, encoding="utf-8-sig")
    pd.concat([pd.DataFrame({"chart": ch.name, "subgroup": np.arange(len(ch.value)), "n": ch.n,
                             "wafer_end_idx": ch.end_idx, "lots": list(ch.lots) if ch.lots else "",
                             "value": ch.value, "z": ch.z, "ewma": ch.ewma, "ewma_limit": ch.ewma_limit,
                             "ucl": ch.ucl, "lcl": ch.lcl, "phase": np.where(np.arange(len(ch.value)) < ch.n_base, "baseline", "monitor")})
               for ch in charts]).to_csv(out_dir / f"{stem}_subgroups.csv", index=False, encoding="utf-8-sig")


def figure_title(args: argparse.Namespace, mode: str, lang: str) -> str:
    FL = LABELS[lang]
    if args.demo:
        title = FL["demo_title"].format(d=DEMO["drift_start"] * DEMO["n"], l=DEMO["lowconf_start"] * DEMO["n"],
                                        s=DEMO["step_start"] * DEMO["n"])
    else:
        order = FL["order_col"].format(col=args.time_col) if args.time_col else FL["order_rows"]
        title = FL["file_title"].format(name=args.predictions.name, order=order)
    return title + "\n" + FL[mode]


def plot(args: argparse.Namespace, charts: list[Chart], n_base_rows: int, mode: str, out_png: Path,
         events: pd.DataFrame | None) -> None:
    """그림 저장. 한글 폰트가 없으면 그림 라벨만 en 으로 바꾼다(콘솔·보고서는 --lang 대로)."""
    fig_lang = args.lang
    if fig_lang == "ko" and setup_korean_font() is None:
        fig_lang = "en"
        print("[경고] 한글 폰트를 찾지 못해 그림 라벨을 영문(en)으로 전환한다. 콘솔·보고서는 --lang 대로.")
    plot_charts(charts, n_base_rows, out_png, figure_title(args, mode, fig_lang), lang=fig_lang, events=events)


def baseline_rate_text(charts: list[Chart], alarms: pd.DataFrame) -> str:
    """baseline 구간 알람률 '1.2% (3 / 250)'. 5% 를 넘으면 시간 순서·안정성 경고를 찍는다."""
    base_alarms = alarms[alarms["phase"] == "baseline"]
    n_base_points = sum(ch.n_base for ch in charts)
    base_rate = len(base_alarms) / max(n_base_points, 1)
    if base_rate > 0.05:
        print(f"\n[경고] baseline 구간 알람률 {base_rate:.0%} ({len(base_alarms)}건 / {n_base_points}점). "
              f"안정 공정이라면 규칙 5개를 다 켜도 1-2% 수준이다.\n"
              f"  이 시퀀스는 정상 상태가 아니거나 시간 순서가 아니다. WM-811K의 행 순서는 제품·로트 블록 순서라\n"
              f"  관리도가 공정 변화가 아니라 데이터셋 정렬을 잡는다. 실제 팹 데이터는 --time-col 로 시각을 지정하라.\n"
              f"  탐지 로직 자체를 확인하려면 --demo 를 써라.")
    elif not base_alarms.empty:
        print(f"\nbaseline 구간 알람 {len(base_alarms)}건 ({base_rate:.1%}) - 우연 범위 안이면 무시, "
              f"많으면 --baseline-frac 을 조정하거나 구간을 다시 골라라.")
    return f"{base_rate:.1%} ({len(base_alarms)} / {n_base_points})"


def print_summary(args: argparse.Namespace, charts: list[Chart], alarms: pd.DataFrame,
                  events: pd.DataFrame | None, ev_dist: pd.DataFrame | None, group_table: pd.DataFrame | None) -> str:
    """콘솔 요약: 첫 탐지 시점, 이벤트 거리, 그룹 비교, baseline 알람률, 알람 수, 패턴별 점검 항목. baseline 알람률 문자열 반환."""
    L = LABELS[args.lang]
    mon = alarms[alarms["phase"] == "monitor"]
    n_up, n_down = int((mon["direction"] == "up").sum()), int((mon["direction"] == "down").sum())

    print(f"\n{'=' * 70}\n{L['h_first'] if args.up_only else L['h_first_all']}\n{'=' * 70}")
    fd = first_detection(alarms, up_only=args.up_only)
    if fd.empty:
        print("  " + L["none"])
    else:
        print(fd.pivot(index="chart", columns="rule", values="first_wafer_idx")
              .reindex(columns=list(ALARM_STYLE)).fillna("-").to_string())
    if args.up_only and n_down:
        print(f"  하강 알람 {n_down}건은 제외 (alarms.csv 의 note 열 참조)")

    if events is not None:
        print(f"\n{'=' * 70}\n{L['h_event']}\n{'=' * 70}")
        if events.empty:
            print("  " + L["r_no_events"])
        else:
            print("  이벤트 " + ", ".join(f"{int(r['idx'])}:{r['label']}" + (f"@{r['group']}" if r["group"] is not None else "")
                                       for _, r in events.iterrows()))
            print(ev_dist.to_string(index=False) if ev_dist is not None and not ev_dist.empty else "  " + L["none"])

    if group_table is not None:
        print(f"\n{'=' * 70}\n{L['h_group']}\n{'=' * 70}")
        print(group_table.to_string(index=False, float_format=lambda v: f"{v:.4f}"))

    base_rate_text = baseline_rate_text(charts, alarms)
    print(f"감시 구간 상승 알람 {n_up}건, 하강 {n_down}건 "
          f"(관리도 {len(charts)}개, 감시 점 {sum(len(ch.value) - ch.n_base for ch in charts)}개)")

    # 패턴별 조치 - 상승 방향 알람이 있는 결함 패턴만. R1 1점뿐인 단발 알람은 점검 목록 대신 한 줄.
    up_names = set(mon.loc[mon["direction"] == "up", "chart"])
    up_charts = [ch for ch in charts if ch.name in up_names]
    up_patterns = [ch for ch in up_charts if ch.base in args.classes]
    if up_patterns:
        print(f"\n{'=' * 70}\n{L['h_actions']}\n{'=' * 70}")
        for ch in up_patterns:
            p = alarm_profile(ch.name, alarms)
            if p["single"]:
                print(f"  {ch.name:14s} [{profile_text(p, args.lang)}] {L['r_single']}")
                continue
            checks = checks_for(ch.base)
            print(f"  {ch.name:14s} [{profile_text(p, args.lang)}] " + "; ".join(checks))
            te = _detail_list(ch.base, "tool_evidence")
            if te:
                print(f"  {'':14s} {L['tool_evidence']}: " + "; ".join(te))
    if any(ch.base == "LOW_CONFIDENCE" for ch in up_charts):
        print("  LOW_CONFIDENCE 저신뢰 웨이퍼 증가 - 새 패턴 출현 또는 분류기 노후. 저신뢰 웨이퍼를 직접 검토하라.")
    return base_rate_text


def settings_text(args: argparse.Namespace, conf_threshold: float | None, conf_how: str) -> str:
    """보고서 '설정' 줄 (handoff: 관리도 설정은 보고서 머리에 남긴다)."""
    s = [f"subgroup={'lot>=' if args.by_lot else ''}{args.base_size}", f"baseline_frac={args.baseline_frac}",
         f"EWMA lambda={EWMA_LAMBDA} L={EWMA_L}", "Laney=" + ("off" if args.no_laney else f"on (n_base>={LANEY_MIN_BASE})"),
         f"up_only={args.up_only}"]
    if conf_threshold is not None:
        s.append(f"conf_threshold={conf_threshold:.3f} ({conf_how})")
    if args.group_col:
        s.append(f"group_col={args.group_col}")
    if args.event_col:
        s.append(f"event_col={args.event_col}")
    if args.anonymize:
        s.append("anonymized ids")
    return ", ".join(s)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    L = LABELS[args.lang]
    df, stem, source = load_input(args)

    mode = chart_mode(df)
    n_base_rows = int(len(df) * args.baseline_frac)
    print(f"웨이퍼 {len(df):,}장, 로트 {df['lot'].nunique():,}개, 기본 부분군 {'로트 병합 >=' if args.by_lot else ''}{args.base_size}장, "
          f"baseline 웨이퍼 0-{n_base_rows - 1}, 감시 {n_base_rows}-{len(df) - 1}")
    print(f"관리도 종류: {L[mode]}")
    if mode == "share":
        print("  (예측 CSV 에 CLEAN/none 판정이 없다. wm811k_evaluate.py --with-none 출력이면 발생률 관리도가 된다)")

    charts, sizes, dropped, conf_threshold, conf_how = build(args, df, n_base_rows)
    alarms = alarm_table(charts, mode)
    save_tables(args.output, stem, charts, alarms)

    events = event_marks(df, args.event_col, args.group_col) if args.event_col else None
    plot(args, charts, n_base_rows, mode, args.output / f"{stem}.png", events)
    ev_dist = event_distance(charts, alarms, events) if events is not None else None
    group_table = group_rate_test(df, args.group_col, args.classes, n_base_rows) if args.group_col else None
    base_rate_text = print_summary(args, charts, alarms, events, ev_dist, group_table)

    mon = alarms[alarms["phase"] == "monitor"]
    n_down = int((mon["direction"] == "down").sum())
    write_report(args.output / f"{stem}_report.md", RunContext(
        lang=args.lang, stem=stem, source=source, synthetic=args.demo, mode=mode,
        range_text=f"{len(df):,} wafers, {df['lot'].nunique():,} lots; baseline 0-{n_base_rows - 1}, monitor {n_base_rows}-{len(df) - 1}",
        settings_text=settings_text(args, conf_threshold, conf_how), base_rate_text=base_rate_text, charts=charts,
        alarms=alarms if not args.up_only else alarms[(alarms["direction"] == "up") | (alarms["phase"] == "baseline")],
        n_down=n_down if args.up_only else 0, event_dist=ev_dist,
        n_events=len(events) if events is not None else None, group_table=group_table, dropped=dropped,
        png_name=f"{stem}.png"))

    print(f"\n저장: {args.output / (stem + '.png')}\n      {args.output / (stem + '_subgroups.csv')}"
          f"\n      {args.output / (stem + '_alarms.csv')}\n      {args.output / (stem + '_report.md')}")


if __name__ == "__main__":
    main()
