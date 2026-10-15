# 로드맵 — 구현된 것의 검증 범위와 남은 것

> 한 줄 요약: 이 저장소의 기능을 "실측으로 검증 / 합성으로 로직만 확인 / 미측정"으로 나눠 적고, 남은 항목마다 "어느 현장 질문에 답하는가"를 한 줄로 단다. 합성 결과는 로직 확인이지 성능이 아니다 — 이 원칙은 새 기능에도 똑같이 적용된다. 실측 수치는 [`validation_log.md`](validation_log.md), SPC 수치는 [`spc.md`](spc.md).

## 1. 구현된 것 — 검증 범위

| 기능 | 파일 | 실측(WM-811K) | 합성(tests / --demo) | 비고 |
|---|---|---|---|---|
| 합성 웨이퍼 맵 생성·렌더, WM-811K 2D 배열 변환 | `wafer_map_visualizer.py` | — | 로직 확인 | 노치는 그림상 −90°에 그림(가정) |
| 규칙 분류기 8종 (전역 특징 6) | `wafer_pattern_classifier.py` | 미교정 0.167 / 교정 0.558 | 7/7 | 임계값·규칙은 수치 불변 대상 |
| 점검 사전 `ACTION_DETAIL` (severity, rule_out_first, first_checks, 고객/장비 측 증거, handoff) | `wafer_pattern_classifier.py` | 해당 없음(문서 데이터) | `tests/test_actions.py` | docs 표와 일치 검증 |
| 구조 특징 11 + RF | `wm811k_structural.py` | 0.878 (단일 0.890) | 파이프라인 스모크 | |
| 위치 특징 3 + 5회 반복 검증 + RF 규제 + `--export-predictions` | `wm811k_validate.py` | **0.907 ± 0.008** | `tests/test_exports.py` | confidence = predict_proba 최댓값(보정 안 함) |
| 강건 특징 8 + HGB 비교 | `wm811k_improve.py` | **미측정** (예상 특징 추출 ~2분, RF/HGB 10회 ~5분, 4코어 기준 추정) | 끝까지 도는 것만 확인 | 채택 기준: 5회 모두 개선, Δ > 분할 간 σ |
| 특징값 스냅샷 (수치 불변 감시) | `tests/test_features_snapshot.py` | — | 고정 맵 3장 × 28특징 | CI |
| SPC: 발생률/점유율 자동 판정, 자동 부분군, Laney(n_base ≥ 20), WE 4규칙, EWMA(λ 0.2, L 2.86; ARL0 ≈ 370 자체 계산), Phase I/II, 저신뢰 분위수, `--group-col`, `--event-col`, `--anonymize`, `--lang`, `--up-only`, 보고서 md | `wm811k_spc.py` | **못 씀**(행 순서가 시간이 아님; 스크립트가 경고) | `--demo` 탐지 시점·허위 알람·층화·이벤트 거리 ([`spc.md`](spc.md) 9절), `tests/test_spc.py` | 실제 팹 데이터는 `--time-col` |
| 방위각 군집 판정 (Rayleigh, 노치 기준) | `wm811k_azimuth.py` | 대부분 로트 insufficient(로트당 3.2장) | `--demo` 4로트 판정 일치, `tests/test_azimuth.py` | 노치 방향은 가정(`--notch-deg`) |
| 스크래치 직선/호 판별 + 로트 내 각도 재현성 | `wm811k_scratch_shape.py` | 동상 | `--demo` 직선 ratio 0.08 / 호 3.27 / 덩어리 too_short, 로트 판정 4/4 일치, `tests/test_scratch_shape.py` | 호 = CMP는 경험칙 |
| 슬롯(waferIndex) 의존성 검정 (끝 슬롯 2×2, 로트 층화 순열, Spearman) | `wm811k_slot.py` | 실행 가능하나 미측정; waferIndex = 물리 슬롯 보장 없음 | `--demo` 3시나리오, `tests/test_slot.py` | |
| 장비 공통성 분석 (단계 내 Fisher, BH, 중복률) | `wm811k_commonality.py` + `docs/lot_history_schema.md` | 입력 없음(WM-811K에 장비 이력 없음) | `--demo` 합성 이력, `tests/test_commonality.py` | |
| 로트 트러블슈팅 리포트 (믹스·반복·방위각·모양·슬롯·공통성·의심 모듈·OCAP 레벨·8D D2 초안, PDF + JSON) | `wm811k_lot_report.py` | 실행 가능하나 미측정 — 로트당 3.2장이라 반복·방위각·모양 판정은 대부분 insufficient, 공통성 입력(장비 이력)은 WM-811K에 없음 | `--demo` 합성 로트 3개 판정 일치, `tests/test_lot_report.py` | OCAP 레벨·의심 모듈 순위 규칙은 설계값 |
| 배치 PDF 리포트, 플롯리 파라메트릭 맵, 한글 폰트 동봉 | `batch_wafer_report.py`, `plotly_wafer_heatmap.py`, `_fonts.py`, `docs/fonts/` | — | `tests/test_report.py` | |
| 문서 그림·샘플 PDF 재생성 (`docs/img`, `docs/samples`) | `make_figures.py` | — | `tests/test_make_figures.py` | 합성 데이터만 쓴다 |
| 문서: 결함 시그니처, TEL 장비 매핑, 공정 맥락, 인계·보고, 용어 대조, 8D 케이스, SPC 상세, 검증 기록 | `docs/*.md` | 공개 자료 수준; 추정은 '(추정)' 표기 | — | TEL 내부 구조·PM 주기는 모른다 |

**실측으로 답할 수 있는 것**은 분류기 품질(0.907 ± 0.008)뿐이다. 나머지는 WM-811K에 시각·챔버·슬롯·사이트·장비 이력이 없어 "실제 팹 데이터가 들어왔을 때의 판정 절차를 코드로 고정한 것"이며, 효과 수치는 전부 미측정이다.

## 2. 남은 것

각 항목에 '왜 필요한가(어느 현장 질문에 답하나)'를 적는다. 우선순위는 현장 질문의 빈도와 구현 비용으로 매겼고, 모두 WM-811K 컬럼(waferMap, lotName, waferIndex)과 합성 데이터만으로 구현·테스트 가능한 범위로 설계한다. 효과는 전부 추정이다.

| # | 항목 | 왜 필요한가 — 어느 현장 질문에 답하나 | 설계 요지 | 검증 가능 범위 |
|---|---|---|---|---|
| 1 | **none 게이트 모델** (`wm811k_evaluate.py --with-none` 결과 → 이진 분류기) | "정상 웨이퍼를 결함으로 잘못 알리는 비율이 얼마인가" — 고객이 시스템을 믿을지 정하는 첫 숫자이고, 이것 없이는 SPC 알람이 "매일 몇 건 헛울리나"에 답할 수 없다 | 같은 20~28특징으로 이진 RF(class_weight balanced), 로트 분할 5회, PR-AUC와 '결함 재현율 0.95에서의 none 오탐률', 임계값은 train 내부. 저신뢰는 LOW_CONFIDENCE 관리도로 | **실측 가능** (none 147,431장 있음) — 몇 안 되는 실측 추가 실험 |
| 2 | **레티클·사이트 격자 자기상관 (repeater)** | "같은 위치가 반복되는가 — 레티클(샷 피치)인가, 공정 마진(다이 피치)인가, 프로브 카드 사이트(터치다운 격자)인가" — LOC·NEAR_FULL의 타사 인계 vs TEL 프로버(Precio / Prexa) 지원을 가르는 질문 | 불량 지시 함수의 2D 자기상관(겹침 ≥ 30다이 정규화), 0-lag 제외 상위 피크, 격자 벡터 2개로 설명되면 반복 주기 보고, 무작위 맵 시뮬레이션 95% 분위를 임계로 | 합성만(WM-811K에 샷·사이트 정보 없음, 다이 피치 정수배 주기로만 추정) |
| 3 | **로트 스택 맵 + 로트 간 유사도** | "이 로트의 서명이 어느 로트와 닮았나 — 같은 장비를 지났나" — 팹 원인 추적의 기본 화면 | 단위원 32×32 재샘플, 다이별 불량 빈도 / 로트 불량률 = 초과 비율 맵, 코사인·Jaccard 유사도, 공통성 분석의 양성 로트 정의로 연결 | 합성만(결함 부분집합 로트당 3.2장) |
| 4 | **수율 손실 분해** (패턴별 체계적 손실 다이) | "어느 패턴을 먼저 잡아야 수율이 가장 오르나" — 알람의 경제적 가중치, 8D D2의 정량 문제 정의('로트당 평균 N다이 손실') | 최대 성분 밖 배경 불량률 λ, 패턴 영역 불량 − λ×면적 = 체계적 손실, 패턴별 파레토. 다이 수 단위로만(실제 크기·가격 모름) | 합성만(링 합성에서 손실 ≈ 링 다이 수) |
| 5 | **FDC 트레이스 결합 데모** (SEMI E125 / E134) | "그 챔버의 어떤 센서가 언제부터 달라졌나" — 패턴이 챔버까지 좁혀진 다음의 질문. TELeMetrics(원격 모니터링, 2016년 보도 기준, 2015년 출시)·Ingenio(APC/FDC)가 다루는 센서 데이터와 이 저장소의 결과 데이터를 같은 시간축에 놓는 지점 | 조인 키(tool, chamber, lot, slot, start_time; WM-811K는 로트·슬롯 키만), 스텝별 센서 요약(평균·최대·기울기), 패턴 양성/음성 Mann-Whitney + Cliff's delta 랭킹, 센서 요약에 같은 EWMA를 걸어 패턴 알람 시점과 교차 확인. TEL 내부 구현은 모른다 | 합성 트레이스만 |
| 6 | **혼합 패턴 성분 인벤토리** (MixedWM38) | "센터 불량 위에 스크래치가 겹친 웨이퍼를 어떻게 적나" — 웨이퍼당 라벨 1개의 한계 | 크기 ≥ 3 연결 성분마다 성분 특징 재계산 → scratch_segment / ring / edge_blob / center_blob / local_blob, 반경 프로파일로 배경 제거 후 잔차 분석, 라벨 'CENTER+SCRATCH'. MixedWM38(1 정상 + 8 단일 + 29 혼합, 52×52, 같은 0/1/2 인코딩; 일부 GAN 생성, 라이선스 확인 필요)로 외부 검증 | 합성 + 외부 데이터(저장소에 포함하지 않음) |
| 7 | **통합 CLI · JSON Lines 스키마 · SEMI E142 리더** | "이 로트 봐줘"를 한 명령으로, 결과를 MES·대시보드가 읽게 — 2024년 TEL Korea 경력 SW 공고의 담당업무 '설비·고객 데이터 분석 결과의 웹 애플리케이션 시각화, 빅데이터 전처리'에 닿는 항목([`references.md`](references.md) [55], 원문 미확인) | `wm811k` 서브커맨드(classify / spc / lot / commonality / slot / azimuth / repeater), 웨이퍼 단위 JSONL(wafer_id, lot, wafer_index, y_pred, confidence, fail_frac, systematic_die, components[], azimuth, scratch_shape, repeater, flags[]), 다이 격자 CSV 입력. E142(기판 맵 XML)는 스키마 세부 미확인이라 리더는 보류 항목 | 합성 스모크(서브커맨드 종료 코드 0) |
| 8 | **Dockerfile** (+ `python -m` 진입점) | "지금 노트북에서 보여줄 수 있나 / 팹 PC에서 같은 환경으로 돌릴 수 있나" — 재현성, 우대 스택(Docker/K8s)과의 접점 | `requirements.lock` 기반 이미지, `--demo` 전부와 pytest를 빌드 단계에서 실행, CI에서 빌드 검증 | CI |
| 9 | **반경 방향 각도 특징** (`radial_angle`: 최대 성분 주축과 반경 방향의 각) | "이 선이 중심을 향하나(코터 도포 방사선, CLEAN TRACK LITHIUS Pro), 접선 방향인가(핸들링 끌림), 호인가(CMP·타사)" — SCRATCH 절의 트랙 노즐 계열 분기 | `wm811k_improve.ROBUST_FEATURES` 뒤 선택 특징으로 두고 SCRATCH↔LOC 혼동(270장)에 효과가 있는지 같은 5분할에서 짝지어 비교; 수치 불변 규칙에 따라 results/ 재생성과 같은 커밋에서만 | **실측 가능** (특징 추가 → 재측정 필요) |
| 10 | SPC 소소한 것 | 케이스 스터디에서 드러난 것 | (a) 조치 이벤트에서 EWMA를 재시작하는 `--reset-at-event`(큰 이탈 뒤 λ 0.2에서 4~5 부분군 걸리는 기억 제거); (b) R3/R4 방향을 완성점의 z 부호가 아니라 창 안 다수 점의 부호로; (c) 같은 x 근처의 이벤트 라벨이 겹치지 않게 그리기; (d) 조치 후 복귀 검증용으로 '이벤트 이후 N장'의 원시 비율 이항 검정을 보고서에 추가 | 합성 |

## 3. 하지 않는 것

- 커뮤니티 출처 정보(교대 근무, 고객사 배정 등)와 확인되지 않은 TEL 내부 정보는 저장소에 넣지 않는다.
- 고객 데이터·실제 장비 식별자는 커밋하지 않는다([`handoff.md`](handoff.md) 4절). 샘플·케이스는 전부 합성.
- 특징값·분할에 영향을 주는 코드 변경은 `results/` 재생성과 같은 커밋에서만([`validation_log.md`](validation_log.md) 수치 불변 규칙). 위 표의 1·9번이 여기에 해당한다.
- WM-811K 실측 썸네일 커밋은 데이터 라이선스를 소유자가 확인하기 전까지 보류.
