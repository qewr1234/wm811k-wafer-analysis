# wafer_pattern_classifier.py
# 웨이퍼 불량 패턴 규칙 기반 분류기 + 패턴별 조치 플레이북(ACTION_DETAIL)
#
# 배경
#   WM-811K 같은 다이 단위 pass/fail 맵(사실상 웨이퍼 테스트 빈 맵)은 모든 공정
#   단계의 결과가 누적된 것이다. 장비사 기술지원 엔지니어는 고객이 에스컬레이션한
#   맵을 받아 "우리 장비 원인인가, 타사 장비 인계인가"를 장비 측 증거(알람 로그,
#   부품 카운터, 레시피·PM 이력)와 맞대어 좁힌다.
#
# 무엇을 하나
#   1) classify_wafer_pattern: 다이 DataFrame 에서 전역 통계(반경 비율, 방향·축
#      집중도)로 8종 결함 패턴 + CLEAN 을 규칙으로 판정한다.
#   2) ACTION_DETAIL: 패턴별 조치 플레이북의 **단일 소스**. 첫 점검 순서, 먼저
#      배제할 것, 고객 측/장비 측 증거, 해당 TEL 모듈, 타사 인계 항목, 판정 기준,
#      수집 데이터를 담는다. docs/defect_signatures.md 의 표와 tests/test_actions.py
#      로 일치를 검증한다. ACTIONS(한 줄 요약)는 여기서 생성되며 batch_wafer_report
#      와 wm811k_spc 의 알람 출력이 그대로 쓴다.
#
# 왜
#   분류 결과가 조치로 이어지지 않으면 현장에서는 쓸모가 없다. 조치 문구가 코드와
#   문서에 따로 있으면 서로 어긋난다(예: NEAR_FULL 을 '장비 긴급 점검'이라 쓰고
#   문서는 '재테스트 먼저'라 쓰는 모순). 그래서 한 곳에서만 정의한다.
#
# 한계
#   규칙 분류기의 임계값은 합성 데이터 기준의 미교정 값이다(실측 macro-F1 0.167,
#   교정·구조 특징·RF 로 0.907 - README 참조). ACTION_DETAIL 의 장비 서술은 공개
#   자료(특허·제품 페이지·교과서 수준의 공정 물리) 기준이며 TEL 내부 구현·매뉴얼
#   PM 주기는 모른다. '(추정)' 표시 항목은 확인되지 않은 것이다. 고객 데이터·실제
#   장비 식별자는 쓰지 않는다.
#
# 사용법
#   python wafer_pattern_classifier.py            # 합성 7모드 x noise 2종 자체 검증(7/7)
#   python wafer_pattern_classifier.py --actions  # ACTION_DETAIL 전체 출력
#   python wafer_pattern_classifier.py --actions NEAR_FULL
#
# 원본 대비 수정 사항
#   (여기서 '원본'은 이 저장소 최초 커밋 1df6309 'Add files via upload' 의 초기
#    스크립트다. 아래는 그 버전에서 잡은 것들이다.)
#   [버그] SCRATCH 미검출 — 중심을 지나는 선은 불량이 정반대 두 방향으로
#          퍼져 원형 평균이 상쇄된다. 각도를 2배로 접는 축(axial) 통계로 교체.
#   [버그] 오답에 최고 점수 — confidence = 1 - angle_concentration 이라
#          스크래치일 때 RANDOM 점수가 오히려 최대가 됐다.
#   [버그] fail_radius_std < 20 등 mm 절대값 임계 → 반경 비율로 전환.
#   [버그] wafer_radius 기본값 150 고정 → 미지정 시 데이터에서 추정.
#          WM-811K는 실제 mm 크기를 알 수 없어 자동 추정이 필수.
#   [제거] spatial_autocorr — 분류에 미사용이고, 10mm 격자에서는 값이
#          거의 항상 1-die/R 로 고정되어 판별력이 없었다. 또한 fail²
#          거리 행렬이라 다이 수가 늘면 메모리를 잡아먹는다.
#   [개명] confidence → score. 확률이 아니라 임의 공식의 휴리스틱 점수다.
#   [확장] EDGE_LOC, DONUT, LOC, NEAR_FULL 추가 (WM-811K 라벨 8종 대응).
#   [버그] CENTER 판정이 평균 반경 기반이라 외곽 이상치 몇 개로 뒤집혔다.
#          → 중앙값으로 교체 (CENTER, DONUT).
#   [버그] LOC이 전부 SCRATCH로 흡수됐다. 국소 클러스터도 축 집중도가
#          높기 때문. SCRATCH에 방향 집중도 상한을 추가해 구분.
#
# 주의: 아래 임계값은 합성 데이터 기준으로 정한 미교정(uncalibrated) 값이다.
#       실측에 적용할 때는 학습 분할에서만 교정하고 평가 분할은 건드리지 말 것.

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

Pattern = Literal[
    "CLEAN", "EDGE_RING", "EDGE_LOC", "CENTER",
    "DONUT", "SCRATCH", "LOC", "RANDOM", "NEAR_FULL",
]


def configure_console() -> None:
    """Windows 콘솔/파이프의 cp949 인코딩 오류를 막는다. __main__ 에서만 부른다.

    모듈 import 시에는 호출하지 않는다(다른 스크립트의 stdout 설정을 건드리지 않게).
    """
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")


# ──────────────────────────────────────────
# 패턴별 조치 플레이북 — 단일 소스
#
# 필드
#   summary            한 줄 요약(첫 점검 1~2개). ACTIONS 가 이 값으로 생성된다.
#   severity           'monitor' | 'lot_hold' | 'line_stop_review'
#                      웨이퍼 한 장 판정 기준의 기본값. 로트 안에서 반복되면 한 단계 올린다.
#   rule_out_first     조치 전에 먼저 배제할 것. 해당 없으면 ''.
#   first_checks       순서 있는 점검 목록(3~6개). 앞이 더 싸고 더 자주 맞는 것.
#   customer_evidence  고객 측 증거: 빈 맵, 로트 이력, 재테스트, 인라인 검사 추세.
#   tool_evidence      장비 측 증거: TEL 엔지니어가 꺼내는 알람/이벤트 로그, 부품 누적
#                      카운터(RF 시간·웨이퍼 매수), 레시피 변경 이력, PM·부품 교체 기록,
#                      로봇 티칭/센터링 로그, 챔버 시즈닝 이력, ESC He 압력·존 온도 로그.
#   tel_modules        해당 TEL 장비군(tel.com 현행 제품명)과 모듈. 내부 구현은 모른다.
#   non_tel            타사 장비 인계 항목(CMP, 노광 스캐너·레티클, 독립 검사 장비 등).
#   handoff            'TEL 원인 vs 타사 인계' 판정 기준 한 문장.
#   data_to_collect    에스컬레이션 시 요청·수집할 데이터.
#
# 물리 서술의 근거는 docs/defect_signatures.md 와 같다(공개 특허·제품 페이지·공정
# 물리). '(추정)' 표시는 확인되지 않은 것. 문자열은 cp949 로 인코딩 가능해야 한다
# (Windows 콘솔·파일 리다이렉트에서 깨지지 않게 - tests/test_actions.py 가 검사).
# ──────────────────────────────────────────
ACTION_DETAIL: dict[str, dict] = {
    "CLEAN": {
        "summary": "조치 불필요. 패턴 비율과 불량률 추세를 관리도(wm811k_spc.py)로 모니터링.",
        "severity": "monitor",
        "rule_out_first": "",
        "first_checks": [
            "불량률(fail_frac)이 CLEAN 임계(2%) 근처면 RANDOM 과의 경계 - FAIL_FRAC_MEAN 관리도 추세 확인",
            "같은 로트의 다른 웨이퍼 판정과 비교(한 장만 CLEAN 이고 나머지가 패턴이면 그 로트 이력 확인)",
            "저신뢰(score 낮음) 웨이퍼는 사람이 맵을 직접 본다",
        ],
        "customer_evidence": ["빈 맵·수율 집계", "로트 이력(공정 완료 여부)"],
        "tool_evidence": ["조치 대상 아님 - 장비 알람 로그는 정상 상태 기준선(baseline) 확보용으로만 수집"],
        "tel_modules": ["해당 없음"],
        "non_tel": ["해당 없음"],
        "handoff": "조치 대상 아님. 추세가 오르면 해당 패턴 항목으로 넘어간다.",
        "data_to_collect": ["웨이퍼별 판정 CSV(lot, y_pred, score)", "시각 열(실제 팹 데이터일 때)"],
    },
    "EDGE_RING": {
        "summary": "전둘레 엣지 불량. 엣지 링(포커스 링) 누적 RF 시간·엣지 보정값(사양 확인), ESC 엣지 존 온도·He 압력부터 점검.",
        "severity": "lot_hold",
        "rule_out_first": "",
        "first_checks": [
            "링 폭 추세: 로트 사이에 서서히 넓어지면 소모품 마모, 갑자기 생기면 부품 교체·레시피 변경·PM 시점과 대조",
            "Tactras / Episode UL 식각: 엣지 링(포커스 링) 누적 RF 시간·전력 카운터, 엣지 균일도 보정값(링 높이·엣지 DC 바이어스 등 - 장비에 그 기능이 있는 경우; 공개 특허 수준이며 TEL 제품 사양은 미확인)이 한계에 닿았는지(마모 -> 시스 왜곡 -> 엣지 식각률 변화·이온 틸트)",
            "ESC 엣지 존 온도·He 백사이드 압력 로그, 엣지 실 밴드 마모·폴리머 오염(He 누설은 엣지 실 밴드에서 난다)",
            "Triase+ / Episode / NT333 성막: 히터 엣지 존 온도, 센터/엣지 가스 분배비. TELINDY PLUS 퍼니스: 보트 슬롯 위치(상/중/하)별 패턴 비율(wm811k_slot.py), 보트 축 방향 히터 존 온도·가스 공급",
            "CLEAN TRACK LITHIUS Pro: EBR 폭 레이어별 설정 대조(한 레이어만 넓으면 전둘레 다이 손실)",
            "EXPEDIUS 배치 세정: 배스·건조 단계 엣지 집중 결함. CMP 리테이닝 링(타사)은 엣지 제거율 프로파일 이탈(과연마·저연마 모두)로 인계",
        ],
        "customer_evidence": [
            "빈 맵의 링 폭·반경 추세(로트별)",
            "로트 이력: 어느 식각/성막/코터/세정 챔버를 거쳤는가, CMP 직후인가",
            "인라인 두께·CD 맵(파라메트릭 맵)의 엣지 프로파일",
        ],
        "tool_evidence": [
            "엣지 링 누적 RF 시간·전력 카운터, 교체 이력",
            "엣지 균일도 보정값 이력(링 높이·엣지 DC 바이어스 등; 장비별 명칭·유무는 사양 확인)",
            "ESC 존별 온도·He 압력 로그, 실 밴드 교체 기록",
            "레시피 변경 이력, PM·챔버 시즈닝 이력",
            "히터 존 온도 로그(성막), EBR 폭 설정값(코터)",
        ],
        "tel_modules": [
            "Tactras / Episode UL 식각: 엣지 링(포커스 링) RF 카운터·엣지 균일도 보정값(사양 확인), ESC 엣지 존",
            "Triase+ / Episode / NT333 성막: 히터 엣지 존, 가스 분배비",
            "TELINDY PLUS 퍼니스: 보트 슬롯 위치별 패턴 비율, 석영 보트·튜브 상태",
            "CLEAN TRACK LITHIUS Pro 코터: EBR 폭 레이어별 설정",
            "EXPEDIUS 배치 세정: 배스·건조 엣지 집중",
        ],
        "non_tel": ["CMP 리테이닝 링 마모(타사): 엣지 제거율이 중심과 달라짐(과연마·저연마 모두 가능)"],
        "handoff": "링 폭 변화 시점이 TEL 챔버의 RF 카운터·보정값 한계·PM 시점과 겹치면 TEL 원인; 로트 이력에서 CMP 직후 로트에만 생기면 타사 인계.",
        "data_to_collect": [
            "로트별 링 폭(outer_rate, r_mean) 추세",
            "챔버 ID별 EDGE_RING 비율",
            "엣지 링 교체일·누적 RF 시간",
            "ESC 존 온도·He 압력 로그(해당 시각)",
            "EBR 폭 설정(레이어별)",
        ],
    },
    "EDGE_LOC": {
        "summary": "엣지 국소 불량. 불량 호의 방위각을 노치 기준으로 측정 - 로트 안 같은 각도면 챔버 비대칭, 제각각이면 로봇 센터링.",
        "severity": "lot_hold",
        "rule_out_first": "",
        "first_checks": [
            "불량 호의 방위각을 노치 기준으로 재서 같은 챔버를 거친 웨이퍼끼리 비교: 같은 각도면 챔버 고정 요소(배기구·가스 주입 위치), 제각각이면 핸들링",
            "반송 로봇 센터링 오프셋·티칭 로그, 얼라이너 노치 정렬 로그(노치 정렬 오류면 같은 패턴이 웨이퍼마다 다른 각도에 나타난다)",
            "CLEAN TRACK LITHIUS Pro: EBR 편심(노즐 위치·척 센터링) - 한쪽은 과도 제거, 반대쪽은 미제거 -> 박리. EBR 폭 4방향 측정",
            "식각/성막 챔버 비대칭: 배기 포트 방향, 가스 주입구 위치를 챔버 도면과 대조",
            "엣지 치핑: 한 점 깨짐이면 주변이 호 모양 - 웨이퍼 엣지 검사, 엔드이펙터·FOUP 슬롯 접촉 흔적",
        ],
        "customer_evidence": [
            "빈 맵에서 호의 방위각(노치 기준)과 폭, 로트 내 재현 여부",
            "로트 이력(챔버 ID·스테이션)",
            "웨이퍼 엣지 검사 결과(치핑)",
        ],
        "tool_evidence": [
            "반송 로봇 센터링 오프셋·티칭 로그",
            "얼라이너 노치 검출 로그",
            "챔버 배기·가스 주입 위치(도면)와 비교할 방위각",
            "EBR 노즐 위치·척 센터링 설정, EBR 폭 측정값(코터)",
            "레시피·PM 이력",
        ],
        "tel_modules": [
            "모든 TEL 장비 공통: EFEM 반송 로봇 센터링·티칭, 얼라이너",
            "Tactras / Episode UL 식각, Triase+ / Episode 성막: 배기·가스 주입 비대칭",
            "CLEAN TRACK LITHIUS Pro: EBR 편심(노즐 위치·척 센터링)",
        ],
        "non_tel": ["타사 장비의 반송계: TEL 챔버를 거치지 않은 로트에도 같은 각도면 그쪽 인계"],
        "handoff": "노치 기준 각도가 TEL 챔버 도면의 비대칭 요소나 로봇 오프셋 로그와 맞으면 TEL 원인; TEL 장비를 안 거친 로트에서도 같은 각도가 재현되면 타사 인계.",
        "data_to_collect": [
            "웨이퍼별 최대 성분 무게중심 방위각(노치 기준)",
            "로트 내 각도 분산",
            "챔버·스테이션 ID",
            "로봇 센터링 로그",
            "EBR 설정값",
        ],
    },
    "CENTER": {
        "summary": "중심부 불량. ESC/히터 중심 존 온도·존별 He 압력 설정(중심/엣지 비), 샤워헤드 중심, 코터 노즐 센터링부터 점검.",
        "severity": "lot_hold",
        "rule_out_first": "",
        "first_checks": [
            "중심 원의 반경이 ESC/히터 중심 존 반경과 일치하는지(일치하면 존 제어, 아니면 샤워헤드·노즐)",
            "Tactras / Episode UL: ESC 중심 존 온도·히터, 존별 He 압력 설정(중심/엣지 비). He 누설은 엣지 실 밴드·리프트 핀 홀에서 나므로 '중심 누설'은 보지 않는다(핀 홀 누설이면 같은 반경 3점)",
            "VHF CCP 식각이면 RF 정재파(center-high: 전극 지름이 유효 RF 파장의 절반 수준) 조건 - 정합기 설정·저주파 병용 조건 변경 이력",
            "Triase+ / Episode / NT333 성막: 샤워헤드 중심 홀 막힘, 세정 주기",
            "CLEAN TRACK LITHIUS Pro: 도포 노즐 센터링·분사 타이밍(중심 두께). CELLESTA 단일 세정: 노즐 스캔이 중심에 머무는 시간",
        ],
        "customer_evidence": [
            "빈 맵 중심 원 반경(prof0, r_med)과 로트 내 재현",
            "두께·CD 파라메트릭 맵의 중심 프로파일",
            "로트 이력(챔버 ID)",
        ],
        "tool_evidence": [
            "ESC/히터 존별 온도 로그, He 존별 압력 설정·실측",
            "RF 정합기 설정·반사파 로그, 레시피 변경 이력",
            "샤워헤드 교체·세정 이력",
            "코터 노즐 센터링 설정·분사 타이밍",
            "챔버 시즈닝·PM 이력",
        ],
        "tel_modules": [
            "Tactras / Episode UL 식각: ESC 중심 존, He 존 압력비, VHF 정재파(center-high)",
            "Triase+ / Episode / NT333 성막: 샤워헤드 중심, 히터 중심 존",
            "CLEAN TRACK LITHIUS Pro: 도포 노즐 센터링",
            "CELLESTA 단일 세정: 노즐 스캔 프로파일",
        ],
        "non_tel": ["CMP 헤드 중심 존 압력(타사)"],
        "handoff": "중심 반경이 TEL 챔버의 존 반경·노즐 설정과 맞고 그 챔버 로트에만 나오면 TEL 원인; CMP 직후 로트에만 나오면 타사 인계.",
        "data_to_collect": [
            "중심 원 반경(정규화)",
            "챔버별 CENTER 비율",
            "존 온도·He 압력 로그",
            "RF 설정 변경 이력",
            "노즐 설정",
        ],
    },
    "DONUT": {
        "summary": "환형 불량. 고리 반경을 다존 경계(히터/ESC, 타사 CMP 헤드)와 대조, 스핀 두께 링, 베이크 플레이트 존 경계(추정) 점검.",
        "severity": "lot_hold",
        "rule_out_first": "",
        "first_checks": [
            "고리 반경(r_med)이 장비 다존 경계(히터/ESC 존 반경)와 일치하는지 - 일치하면 존 간 설정 불일치",
            "Tactras / Episode UL: 정재파(center-high)와 스킨 효과(edge-high)가 겹치거나 압력이 높아 중간 반경 극값이 생기는 2차 효과 - 압력·주파수 조건 변경 이력",
            "CLEAN TRACK LITHIUS Pro: 스핀 코팅 두께 링(회전수·분사 타이밍), 베이크 플레이트 존 경계(추정)",
            "웨이퍼 휨(bow)과 척 접촉이 특정 반경에서 떨어지는지 - 휨 측정값과 상관",
            "타사 CMP 다존 헤드 존 경계(인계)",
        ],
        "customer_evidence": [
            "고리 반경·폭(prof2, r_std), 로트 내 재현",
            "웨이퍼 휨 측정값",
            "파라메트릭 맵의 반경 프로파일 극값",
        ],
        "tool_evidence": [
            "히터/ESC 존 경계 반경(사양), 존별 온도 설정·로그",
            "RF 압력·주파수 조건과 레시피 변경 이력",
            "코터 회전수·분사 타이밍 레시피, 베이크 플레이트 존 설정",
            "PM·부품 교체 이력",
        ],
        "tel_modules": [
            "Tactras / Episode UL 식각: ESC 존 경계, 압력 조건",
            "Triase+ / Episode 단일 웨이퍼 성막: 히터 존 경계 (TELINDY PLUS 퍼니스는 존이 보트 축 방향이라 슬롯 위치별 비율로 본다)",
            "CLEAN TRACK LITHIUS Pro: 스핀 두께 링, 베이크 플레이트 존(추정)",
        ],
        "non_tel": ["CMP 다존 헤드 존 경계(타사)"],
        "handoff": "고리 반경이 TEL 장비 존 경계와 일치하면 TEL 원인; CMP 헤드 존 반경과 일치하고 CMP 직후에만 나오면 타사 인계.",
        "data_to_collect": ["고리 반경·폭", "장비별 존 경계 반경", "존 설정값·로그", "휨 측정값"],
    },
    "SCRATCH": {
        "summary": "선형 불량. 호 모양이면 주로 CMP(타사), 직선이면 주로 핸들링(경험칙). 로트 안 노치 기준 방향·위치 재현 여부가 더 확실한 구분.",
        "severity": "lot_hold",
        "rule_out_first": "",
        "first_checks": [
            "선이 호인지 직선인지(경험칙: 호는 주로 CMP 패드 입자, 직선은 주로 반송 끌림) 그리고 로트 안에서 선의 방향·위치가 노치 기준으로 재현되는가(재현이면 핸들링 고정 접촉, 무작위면 CMP 입자)",
            "모든 TEL 장비 공통 반송계: EFEM 로봇 엔드이펙터 패드 상태, FOUP/카세트 슬롯 끌림, 웨이퍼 슬립 흔적, 로봇 티칭 로그",
            "CLEAN TRACK LITHIUS Pro: 중심 지향 방사형 선 군집이면 레지스트 도포량 부족, 양끝 소용돌이 대각선이면 디벨로퍼 노즐 오염, EBR 노즐 끝 용제 방울 낙하",
            "CELLESTA 단일 세정: 노즐 궤적을 따른 호/방사선",
            "호 모양이고 CMP 직후 로트에만 나오면 CMP 슬러리 응집체·패드 컨디셔너 잔해·리테이닝 링 안쪽 홈 잔류물(타사 인계)",
            "프로브 카드의 정상 터치다운은 선형 스크래치를 만들지 않는다 - 예외: 프로버 Z축·인덱스 이상이면 다이 격자 축(행/열)에 평행한 직선이 재테스트 후에도 남는다(프로버 Z·인덱스 로그; Precio / Prexa 면 TEL 프로버 지원). 격자 주기 반복 패턴이면 LOC/NEAR_FULL 항목의 프로버 점검으로",
        ],
        "customer_evidence": [
            "선의 모양(호/직선)·길이·방향, 로트 내 재현(노치 기준)",
            "로트 이력: CMP 직후인가, 어느 반송 경로인가",
            "웨이퍼 뒷면·엣지 검사",
        ],
        "tool_evidence": [
            "EFEM 로봇 티칭·센터링 로그, 엔드이펙터 패드 교체 이력",
            "FOUP/카세트 슬롯 상태, 웨이퍼 핸들링 알람 로그",
            "코터 도포량·디벨로퍼 노즐 세정 이력, EBR 노즐 상태",
            "세정기 노즐 스캔 레시피",
        ],
        "tel_modules": [
            "모든 TEL 장비 공통: EFEM 반송 로봇·엔드이펙터·FOUP 슬롯",
            "CLEAN TRACK LITHIUS Pro: 도포량(중심 지향 방사선), 디벨로퍼 노즐(소용돌이 대각선), EBR 노즐",
            "CELLESTA 단일 세정: 노즐 궤적 호/방사선",
        ],
        "non_tel": [
            "CMP 슬러리 필터·패드·컨디셔너·리테이닝 링 안쪽 홈(타사)",
            "CMP 후세정 브러시(타사)",
        ],
        "handoff": "로트 안에서 방향·위치가 노치 기준으로 재현되고 TEL 반송 경로와 맞으면 TEL 원인; 호 모양·무작위 위치·CMP 직후면 타사 인계.",
        "data_to_collect": [
            "최대 성분 세장비·길이·주축 각도(반경 방향 각도 특징은 다음 실험)",
            "로트 내 방향 분산",
            "반송 경로·챔버 ID",
            "CMP 통과 여부",
        ],
    },
    "LOC": {
        "summary": "국소 덩어리. 로트 안 같은 위치면 공정, 다른 위치면 이벤트. 같은 반경 3점(120도)이면 리프트 핀, 샷 피치 반복이면 레티클(타사).",
        "severity": "lot_hold",
        "rule_out_first": "격자 주기(샷 피치·터치다운 격자)로 반복되면 레티클 리피터 또는 프로브 카드 사이트 불량 - 재테스트와 리피터 분석으로 먼저 배제",
        "first_checks": [
            "덩어리 위치가 로트 안에서 같은가(공정·장비 고정 요소) 다른가(파티클 이벤트)",
            "같은 반경에 3점이 120도 간격이면 리프트 핀(핀 높이·오염) - 노치 기준 각도와 반경으로 어느 TEL 모듈인지 특정",
            "샷(노광 필드) 피치로 반복되면 레티클 리피터(타사 노광 인계), 다이 피치로 반복되면 공정 마진(다이 레벨 체계적 결함). WM-811K 에는 필드 정보가 없어 다이 피치 정수배 주기로만 추정",
            "파티클 샤워: 챔버 벽 박리 - 시즈닝 후 경과 웨이퍼 수, PM 직후 파티클 카운트(Tactras / Triase+ / TELINDY PLUS)",
            "직전 증착·코팅 단계의 뒷면 파티클 검사(뒷면 파티클 -> 노광 핫스팟)",
            "CLEAN TRACK LITHIUS Pro: 너무 좁은 EBR 설정이면 엣지 그리퍼 접촉 플레이크 -> 파티클",
        ],
        "customer_evidence": [
            "덩어리 위치(반경·노치 기준 각도)의 로트 내 재현",
            "격자 주기 반복 여부(리피터 분석)",
            "인라인 파티클 검사 추세(단계별)",
            "뒷면 검사 결과",
        ],
        "tool_evidence": [
            "리프트 핀 높이·교체 이력",
            "챔버 시즈닝 후 경과 웨이퍼 수, PM 이력, 파티클 알람 로그",
            "챔버 벽·라이너 교체 이력",
            "EBR 폭 설정, 엣지 그리퍼 상태(코터)",
            "프로버 프로브 카드 사이트별 불량률(격자 반복일 때)",
        ],
        "tel_modules": [
            "Tactras / Episode UL, Triase+ / Episode, TELINDY PLUS: 리프트 핀, 챔버 시즈닝·파티클",
            "CLEAN TRACK LITHIUS Pro: EBR 폭·엣지 그리퍼",
            "Precio / Prexa 프로버: 터치다운 격자 주기 반복이면 멀티사이트 카드 특정 사이트",
        ],
        "non_tel": [
            "레티클·노광기(타사): 샷 피치 리피터",
            "인라인 검사 장비(타사) 파티클 추세",
        ],
        "handoff": "위치가 TEL 챔버의 핀 반경·시즈닝 이력과 맞으면 TEL 원인; 샷 피치 반복이면 노광 인계, 터치다운 격자 반복이면 프로버 점검.",
        "data_to_collect": [
            "최대 성분 무게중심 반경·각도(노치 기준)",
            "로트 내 위치 분산",
            "격자 자기상관(다음 실험)",
            "시즈닝 후 경과 매수",
            "파티클 카운트 추세",
        ],
    },
    "RANDOM": {
        "summary": "산발 불량. 불량 비율을 관리도에 올려 라인 베이스라인 결함 밀도 추세를 보고, 단계별 인라인 파티클 추세로 어느 단계가 올랐는지 본다.",
        "severity": "monitor",
        "rule_out_first": "",
        "first_checks": [
            "불량 비율(fail_frac) 자체를 관리도(FAIL_FRAC_MEAN)에 올린다 - 서서히 오르면 라인 오염, 특정 로트만 높으면 그 로트 이력",
            "군집이 있으면 이미 LOC/EDGE_LOC 이다 - 포아송(균일 무작위) 전제 영역인지, 음이항(군집 계수)이 맞는지 isolated_frac 으로 확인",
            "단계별 인라인 파티클 검사(타사 검사 장비) 추세에서 어느 단계가 올랐는지",
            "TEL 챔버: PM 직후·시즈닝 경과 매수에 따른 파티클 카운트, 챔버 벽 박리",
            "CELLESTA 단일 세정 vs EXPEDIUS 배치 세정: 배치는 엣지 집중·세로 패턴, 단일은 무작위 밀도 - 세정 전환 전후 베이스라인 비교. Certas LEAGA 는 무액체라 워터마크 없음",
        ],
        "customer_evidence": [
            "웨이퍼별 불량 비율 추세(로트·시각)",
            "단계별 인라인 파티클 검사 추세",
            "로트 이력(어느 챔버·세정 경로)",
        ],
        "tool_evidence": [
            "챔버 파티클 알람 로그, 시즈닝 후 경과 매수",
            "PM·부품 교체 이력(챔버 라이너, 샤워헤드)",
            "세정기 레시피·약액 교체 이력",
            "EBR 폭 설정(너무 좁으면 플레이크 파티클)",
        ],
        "tel_modules": [
            "Tactras / Episode UL, Triase+ / Episode / NT333, TELINDY PLUS: 챔버 시즈닝·파티클",
            "CELLESTA / EXPEDIUS / NS300 세정: 베이스라인 결함 밀도",
            "CLEAN TRACK LITHIUS Pro: EBR 폭·플레이크",
        ],
        "non_tel": [
            "인라인 파티클 검사 장비(타사) 추세가 1차 자료",
            "라인 전체 청정도(고객 설비)",
        ],
        "handoff": "특정 TEL 챔버 통과 로트에서만 밀도가 오르고 그 챔버의 시즈닝·PM 시점과 겹치면 TEL 원인; 모든 경로에서 고르게 오르면 라인 청정도(고객·타사).",
        "data_to_collect": [
            "fail_frac 시계열",
            "isolated_frac(고립 다이 비율)",
            "챔버별 RANDOM 비율",
            "단계별 파티클 카운트",
            "시즈닝 경과 매수",
        ],
    },
    "NEAR_FULL": {
        "summary": "전면 불량. 재테스트로 프로브 카드·테스트 프로그램 원인을 먼저 배제한 뒤, 로트 이력에서 비정상 종료 공정을 찾는다.",
        "severity": "line_stop_review",
        "rule_out_first": "재테스트로 테스트 원인(프로브 카드 평탄도·오버드라이브·접촉 저항, 테스트 프로그램 리밋, 제품/웨이퍼 ID 혼동) 배제",
        "first_checks": [
            "재테스트: 프로브 카드 평탄도·오버드라이브·접촉 저항(CRES), 테스트 프로그램 리밋, 제품/웨이퍼 ID 혼동 배제(Precio / Prexa 프로버면 카드 클리닝·터치다운 카운터 확인)",
            "같은 로트의 다른 웨이퍼도 그런가(공정 사고) 한 장만 그런가(단일 웨이퍼 이벤트)",
            "로트 이력에서 비정상 종료 공정: 레시피 오류, 단계 누락, 공정 중 장비 다운 - 장비 알람·이벤트 로그와 대조",
            "실제 공정 원인으로 확인되면 라인 정지·로트 홀드 판단을 고객 수율팀과 함께(초동 보고)",
            "웨이퍼 파손은 보통 테스트까지 가지 않는다(추정) - 파손 의심이면 핸들링 알람 로그",
        ],
        "customer_evidence": [
            "재테스트 결과",
            "같은 로트 다른 웨이퍼의 빈 맵",
            "로트 이력(비정상 종료·홀드 기록)",
            "테스트 프로그램 버전·리밋",
        ],
        "tool_evidence": [
            "장비 알람·이벤트 로그(해당 로트 처리 시각)",
            "레시피 실행 로그(단계 누락·중단)",
            "프로버: 프로브 카드 CRES·클리닝 시트 주기·터치다운 카운터",
            "핸들링 알람 로그",
        ],
        "tel_modules": [
            "Precio / Prexa 프로버: 프로브 카드 접촉·클리닝·터치다운 카운터",
            "모든 TEL 공정 장비: 알람·이벤트 로그, 레시피 중단 기록",
        ],
        "non_tel": [
            "테스트 프로그램·테스터(타사)",
            "타사 공정 장비의 비정상 종료",
        ],
        "handoff": "재테스트 후에도 전면 불량이고 로트 이력의 비정상 종료가 TEL 장비 알람과 겹치면 TEL 원인; 재테스트로 사라지면 프로브 카드·테스트 프로그램 쪽(Precio / Prexa 면 TEL 프로버 지원).",
        "data_to_collect": [
            "재테스트 전후 빈 맵",
            "로트 이력·홀드 기록",
            "장비 알람 로그(시각)",
            "프로브 카드 ID·터치다운 수",
            "테스트 프로그램 버전",
        ],
    },
}

# 기존 import 호환 — 한 줄 요약. batch_wafer_report / wm811k_spc 가 그대로 쓴다.
ACTIONS: dict[str, str] = {k: v["summary"] for k, v in ACTION_DETAIL.items()}

SEVERITY_LABEL: dict[str, str] = {
    "monitor": "모니터링",
    "lot_hold": "로트 홀드 검토",
    "line_stop_review": "라인 정지 판단 필요",
}


def format_action_detail(pattern: str) -> str:
    """ACTION_DETAIL 한 항목을 사람이 읽는 여러 줄 텍스트로. 리포트·알람 출력용."""
    d = ACTION_DETAIL[pattern]
    lines = [f"[{pattern}] {d['summary']}",
             f"  심각도: {SEVERITY_LABEL[d['severity']]} ({d['severity']})"]
    if d["rule_out_first"]:
        lines.append(f"  먼저 배제: {d['rule_out_first']}")
    lines.append("  점검 순서:")
    lines += [f"    {i}. {c}" for i, c in enumerate(d["first_checks"], 1)]
    for key, label in (("customer_evidence", "고객 측 증거"), ("tool_evidence", "장비 측 증거"),
                       ("tel_modules", "TEL 모듈"), ("non_tel", "타사 인계"),
                       ("data_to_collect", "수집 데이터")):
        lines.append(f"  {label}:")
        lines += [f"    - {c}" for c in d[key]]
    lines.append(f"  판정 기준: {d['handoff']}")
    return "\n".join(lines)

# ── 임계값 (모두 유효 반경 R 또는 비율 기준) ──
CLEAN_FAIL_FRAC = 0.02      # 불량 비율 이하면 CLEAN
NEAR_FULL_FRAC = 0.60       # 불량 비율 이상이면 NEAR_FULL
CENTER_R_MAX = 0.30         # 중심 불량: 평균 반경 / R
EDGE_R_MIN = 0.70           # 엣지 계열: 평균 반경 / R
RING_STD_MAX = 0.15         # 전둘레 링: 반경 표준편차 / R
RING_DIR_MAX = 0.45         # 전둘레 링: 방향 집중도 상한 (넘으면 국소)
DONUT_R_RANGE = (0.35, 0.70)
DONUT_STD_MAX = 0.16
SCRATCH_AXIAL_MIN = 0.50
SCRATCH_DIR_MAX = 0.35      # 중심을 지나는 선은 양방향 → 방향 집중도가 낮다
LOC_DIR_MIN = 0.50


@dataclass
class WaferPatternResult:
    pattern: Pattern
    score: float                    # 휴리스틱 점수 (확률 아님)
    yield_pct: float
    fail_count: int
    fail_fraction: float
    wafer_radius: float             # 사용된 정규화 반경
    fail_radius_mean: float
    fail_radius_std: float
    fail_radius_median: float
    r_mean_norm: float              # fail_radius_mean / wafer_radius
    r_med_norm: float               # 이상치에 강건 — CENTER/DONUT 판정에 사용
    r_std_norm: float
    dir_concentration: float        # 방향 집중도 (한쪽 치우침)
    axial_concentration: float      # 축 집중도 (선형성)
    recommended_action: str = field(default="")


# 합성 생성기의 defect_mode → 분류기가 내야 할 클래스
EXPECTED_BY_MODE: dict[str, str] = {
    "ring": "EDGE_RING", "center": "CENTER", "scratch": "SCRATCH",
    "random": "RANDOM", "donut": "DONUT", "edge_loc": "EDGE_LOC",
    "clean": "CLEAN",
}


def expected_patterns(defect_mode: str, noise: float = 0.0) -> frozenset[str]:
    """합성 웨이퍼에서 정답으로 인정할 클래스 집합.

    clean 모드에 noise를 주면 다이의 약 noise 비율이 FAIL로 뒤집힌다.
    뒤집힌 비율은 웨이퍼마다 CLEAN_FAIL_FRAC(2%) 근처에서 흔들리므로,
    규칙상 CLEAN과 RANDOM(산발 불량) 둘 다 그 맵을 옳게 읽은 것이다.
    CLEAN만 기대하면 자체 검증이 코딩 오류가 아닌 MISS를 낸다.
    """
    if defect_mode == "clean" and noise > 0:
        return frozenset({"CLEAN", "RANDOM"})
    return frozenset({EXPECTED_BY_MODE[defect_mode]})


def _circular_stats(angles_deg: np.ndarray) -> tuple[float, float]:
    """방향 집중도와 축 집중도를 반환.

    방향 집중도는 평균 벡터 길이. 한쪽으로 치우친 국소 불량에서 커진다.
    축 집중도는 각도를 2배로 접어 계산한다. θ와 θ+180°가 같은 값이 되므로
    중심을 지나는 선형 패턴에서도 상쇄되지 않는다.
    """
    a = np.radians(angles_deg)
    dir_c = float(np.hypot(np.mean(np.sin(a)), np.mean(np.cos(a))))
    axial_c = float(np.hypot(np.mean(np.sin(2 * a)), np.mean(np.cos(2 * a))))
    return dir_c, axial_c


def _infer_radius(df: pd.DataFrame) -> float:
    """정규화용 반경을 데이터에서 추정한다.

    WM-811K는 맵 크기가 329종이고 실제 mm 크기를 알 수 없으므로,
    관측된 최대 반경을 웨이퍼 반경의 대리값으로 쓴다.
    """
    r_max = float(df["radius"].max())
    return r_max if r_max > 0 else 1.0


def classify_wafer_pattern(
    df: pd.DataFrame,
    wafer_radius: float | None = None,
) -> WaferPatternResult:
    """웨이퍼 다이 DataFrame(die_x, die_y, radius, angle_deg, status)을
    분석해 불량 패턴을 분류한다.

    wafer_radius를 주지 않으면 데이터의 최대 반경으로 추정한다.
    모든 판정은 반경 비율로 이루어지므로 맵 크기에 무관하다.
    """
    total = len(df)
    if total == 0:
        raise ValueError("빈 DataFrame")

    R = wafer_radius if wafer_radius else _infer_radius(df)

    is_fail = (df["status"] == "FAIL").to_numpy()
    fail_count = int(is_fail.sum())
    fail_frac = fail_count / total
    yield_pct = (1.0 - fail_frac) * 100.0

    def result(pattern: Pattern, score: float, **kw) -> WaferPatternResult:
        base = dict(
            yield_pct=yield_pct, fail_count=fail_count, fail_fraction=fail_frac,
            wafer_radius=R, fail_radius_mean=0.0, fail_radius_std=0.0,
            fail_radius_median=0.0,
            r_mean_norm=0.0, r_med_norm=0.0, r_std_norm=0.0,
            dir_concentration=0.0, axial_concentration=0.0,
        )
        base.update(kw)
        return WaferPatternResult(
            pattern=pattern, score=float(np.clip(score, 0.0, 1.0)),
            recommended_action=ACTIONS[pattern], **base,
        )

    # ── 불량이 거의 없음 ──
    if fail_frac <= CLEAN_FAIL_FRAC:
        return result("CLEAN", 1.0 - fail_frac / max(CLEAN_FAIL_FRAC, 1e-9))

    r = df.loc[is_fail, "radius"].to_numpy()
    ang = df.loc[is_fail, "angle_deg"].to_numpy()

    r_mean = float(r.mean())
    # 중앙값은 소수의 외곽 이상치에 강건하다. 평균만 쓰면 중심 불량 웨이퍼에
    # 산발적 외곽 불량 몇 개가 붙는 것만으로 판정이 뒤집힌다.
    r_med = float(np.median(r))
    # ddof=0 — 불량 1개일 때 NaN이 나오지 않게 한다
    r_std = float(r.std(ddof=0))
    r_mean_n = r_mean / R
    r_med_n = r_med / R
    r_std_n = r_std / R
    dir_c, axial_c = _circular_stats(ang)

    stats = dict(
        fail_radius_mean=r_mean, fail_radius_std=r_std,
        fail_radius_median=r_med,
        r_mean_norm=r_mean_n, r_med_norm=r_med_n, r_std_norm=r_std_n,
        dir_concentration=dir_c, axial_concentration=axial_c,
    )

    # ── 판정 순서: 특이한 것부터 좁혀 들어간다 ──

    # 거의 전면 불량
    if fail_frac >= NEAR_FULL_FRAC:
        return result("NEAR_FULL", fail_frac, **stats)

    # 중심부 (방향성이 없어야 함)
    if r_med_n <= CENTER_R_MAX and dir_c < LOC_DIR_MIN:
        return result("CENTER", 1.0 - r_med_n / CENTER_R_MAX, **stats)

    # 엣지 계열 — 전둘레인지 국소인지로 갈린다
    if r_mean_n >= EDGE_R_MIN:
        if r_std_n <= RING_STD_MAX and dir_c <= RING_DIR_MAX:
            score = r_mean_n * (1.0 - r_std_n / max(RING_STD_MAX, 1e-9) * 0.5)
            return result("EDGE_RING", score, **stats)
        return result("EDGE_LOC", max(dir_c, r_mean_n), **stats)

    # 환형 — 중간 반경에 좁은 띠, 방향성 없음
    if (DONUT_R_RANGE[0] <= r_med_n <= DONUT_R_RANGE[1]
            and r_std_n <= DONUT_STD_MAX and dir_c <= RING_DIR_MAX):
        return result("DONUT", 1.0 - r_std_n / max(DONUT_STD_MAX, 1e-9), **stats)

    # 선형 스크래치 — 축 집중도는 높고 방향 집중도는 낮아야 한다.
    # 국소 클러스터(LOC)도 축 집중도가 높으므로 dir_c 상한이 없으면
    # LOC 전부가 SCRATCH로 흡수된다.
    if axial_c >= SCRATCH_AXIAL_MIN and dir_c <= SCRATCH_DIR_MAX:
        return result("SCRATCH", axial_c * (1.0 - dir_c), **stats)

    # 국소 클러스터
    if dir_c >= LOC_DIR_MIN:
        return result("LOC", dir_c, **stats)

    # 나머지
    return result("RANDOM", 1.0 - max(dir_c, axial_c), **stats)


# ──────────────────────────────────────────
def _self_check() -> int:
    """합성 7모드 x noise 2종 자체 검증. MISS 수를 반환한다.

    생성기와 분류기가 같은 규칙을 공유하므로 전부 맞히는 것은 성능이 아니라
    코딩 오류가 없다는 확인까지다. 실제 정확도는 WM-811K로 재야 한다.
    """
    from wafer_map_visualizer import generate_sample_wafer_data

    modes = ["ring", "center", "scratch", "random", "donut", "edge_loc", "clean"]
    n_miss_total = 0
    for noise in (0.0, 0.03):
        print(f"\n{'=' * 62}")
        print(f"noise = {noise}")
        print(f"{'=' * 62}")
        n_ok = 0
        for mode in modes:
            df = generate_sample_wafer_data(defect_mode=mode, noise=noise)
            res = classify_wafer_pattern(df)
            exp = expected_patterns(mode, noise)
            ok = res.pattern in exp
            n_ok += ok
            print(f"\n[{mode.upper()}] -> {res.pattern}  {'OK' if ok else 'MISS'}")
            print(f"  score {res.score:.3f} | 수율 {res.yield_pct:.1f}% | "
                  f"불량 {res.fail_count}개 ({res.fail_fraction:.1%})")
            print(f"  r_mean/R {res.r_mean_norm:.3f} | r_med/R {res.r_med_norm:.3f} | "
                  f"r_std/R {res.r_std_norm:.3f} | "
                  f"dir {res.dir_concentration:.3f} | axial {res.axial_concentration:.3f}")
            print(f"  조치: {res.recommended_action}")
            if not ok:
                print(f"  기대: {'/'.join(sorted(exp))}")
        print(f"\n일치 {n_ok}/{len(modes)}")
        n_miss_total += len(modes) - n_ok
    return n_miss_total


if __name__ == "__main__":
    import argparse

    configure_console()
    ap = argparse.ArgumentParser(description="규칙 분류기 자체 검증 / 조치 플레이북 출력")
    ap.add_argument("--actions", nargs="?", const="ALL", metavar="PATTERN",
                    help="ACTION_DETAIL 출력. 패턴명을 주면 그 항목만 (예: NEAR_FULL)")
    args = ap.parse_args()

    if args.actions:
        keys = list(ACTION_DETAIL) if args.actions == "ALL" else [args.actions.upper()]
        unknown = [k for k in keys if k not in ACTION_DETAIL]
        if unknown:
            raise SystemExit(f"알 수 없는 패턴 {unknown}. 선택: {', '.join(ACTION_DETAIL)}")
        print("\n\n".join(format_action_detail(k) for k in keys))
        raise SystemExit(0)

    # 자체 검증이 깨지면 종료 코드로 알린다 (CI 등에서 잡을 수 있게)
    raise SystemExit(1 if _self_check() else 0)
