# PORTFOLIO — 이 저장소가 증명하는 것, 증명하지 못하는 것

> 한 줄 요약: 소프트웨어 엔지니어 경력으로 Tokyo Electron Korea 2026 하반기 공채 **Software Engineer - Tech Support Engineer**(경력 Field / Process Engineer 트랙에도 통용)에 내는 포트폴리오의 1페이지 설명이다. 기술 근거만 적는다. **인성·동기 답변('왜 이 회사인가', '왜 이 직무인가', '10년 후' 등)은 이 저장소에 넣지 않는다** — 그런 내용이 기술 문서 사이에 섞이면 문서의 신뢰도가 떨어진다. 사실과 추정, 실측과 합성은 줄 단위로 구분한다.

## 소프트웨어 경력에서 가져오는 것 3가지

1. **테스트·CI·재현성.** `tests/` 13개 파일(합성 데이터만, 테스트 하나 30초 이내)과 CI 매트릭스(ubuntu/windows × Python 3.11/3.12). 자체 검증이 깨지면 종료 코드로 알리고(`wafer_pattern_classifier.py`), Windows 파일 리다이렉트의 cp949 회귀를 CI가 잡는다. README의 실측 수치(macro-F1 0.907 ± 0.008)는 이 환경에서 재측정할 수 없으므로 `tests/test_features_snapshot.py`가 특징값 28개를 고정해 리팩터가 수치를 바꾸면 CI가 알리고, 특징·분할·모델에 닿는 변경은 `results/` 재생성과 같은 커밋에서만 한다는 규칙을 [`docs/validation_log.md`](docs/validation_log.md)에 적어 두었다.
2. **데이터 파이프라인·시각화.** LSWMD.pkl → 추출 → 특징 → 교정 → 반복 검증 → 예측 CSV → SPC로 이어지는 파이프라인에서 누수(로트 단위 분할, 임계값은 train에서만, test는 1회)를 설계 단계에서 막았고, 특징 20개가 각각 어느 물리 현상을 재는지(AUC) 기록했다. 산출물은 사람이 읽는 형태다: 파라메트릭 맵(오프라인 HTML), 관리도 PNG, 서비스 리포트·로트 리포트 PDF, 알람 요약 md. 한글 폰트를 동봉해 환경에 따라 리포트가 깨지지 않게 했고, 고객 ID는 `--anonymize`로 가린다.
3. **자동화.** 조치 문구의 단일 소스(`wafer_pattern_classifier.ACTION_DETAIL`)에서 문서 표·PDF·SPC 알람 출력이 모두 생성되고 `tests/test_actions.py`가 코드와 문서의 일치를 검사한다. 알람 → 점검 항목 → 대조할 장비 측 로그 → 보고서 초안이 한 실행에서 나오고, 문서용 그림·샘플 PDF 전부가 `make_figures.py` 한 명령으로 재생성된다. 반복 작업을 스크립트와 테스트로 고정하는 습관이 현장의 작업지시서·CIP 대응에서 쓰이는 지점이다.

## 현장에서 배워야 하는 것 3가지 (솔직하게)

1. **장비 하드웨어.** 진공·RF/플라즈마·가스 분배·온도/ESC·반송계를 실물로 다뤄 본 적이 없다. 이 저장소의 장비 서술은 공개 자료(제품 페이지·특허·논문·교과서 수준의 공정 물리) 기준이며, TEL 내부 구조·매뉴얼의 PM 주기·소모품 교체 기준은 모른다. 확인되지 않은 것은 '(추정)'으로 표시했고 출처는 [`docs/references.md`](docs/references.md)에 등급과 함께 있다. [`docs/process_context.md`](docs/process_context.md)는 학습 메모이지 경험이 아니다.
2. **고객 대응·보고.** 실제 고객 에스컬레이션을 받아 초동 보고를 쓰고 부품을 수배하고 작업지시서를 낸 적이 없다. [`docs/handoff.md`](docs/handoff.md)의 보고 3단계와 8D 팀 역할, [`docs/case_study_8d.md`](docs/case_study_8d.md)의 케이스 2건은 공개 자료 기준의 설계와 합성 시나리오다. 1인 프로젝트라 협업 실적도 없다.
3. **안전·클린룸.** LOTO, RF·고전압, 가스 캐비닛, 클린룸 규정은 체크리스트로 적었을 뿐 교육·자격·현장 경험이 없다. 장비 앞에 서기 전에 배워야 하는 것의 첫 번째다.

## 증명하는 범위 / 증명하지 못하는 범위

| 증명하는 것 (실측 또는 코드로 고정) | 증명하지 못하는 것 |
|---|---|
| WM-811K 실측 분류 품질 macro-F1 **0.907 ± 0.008** (누수 없는 로트 분할 5회, 해석 가능한 특징 20개) | SPC·방위각·슬롯·공통성·로트 리포트의 **실측 효과** — WM-811K에 시각·챔버·슬롯·장비 이력이 없어 합성 로직 확인뿐 |
| 합성 7/7 → 실측 0.167 붕괴의 원인을 특정하고(임계값, 특징 아님) 누수 없이 교정·확장한 과정([`docs/validation_log.md`](docs/validation_log.md)) | 정상 웨이퍼(`none` 147,431장)를 거르는 단계의 오경보율 — 미측정([`docs/roadmap.md`](docs/roadmap.md) 1번) |
| 패턴 → TEL 모듈 / 타사 인계 → 고객 측·장비 측 증거 → 점검 순서 → 판정의 논리를 코드와 문서 한 소스로([`docs/defect_signatures.md`](docs/defect_signatures.md), `ACTION_DETAIL`) | `wm811k_improve.py`의 강건 특징 8개·HGB 효과 — 실측 미측정 |
| SPC 로직: Laney p′·WE 4규칙·EWMA(λ 0.2, L 2.86)·Phase I/II·층화·이벤트 거리, 상승 알람 → 점검 항목([`docs/spc.md`](docs/spc.md)) | 장비 실물 경험, 고객 대응 실적, TEL 내부 지식 — 위 '배워야 하는 것' |
| 테스트·CI·재현성 습관과 고객 데이터 기밀 설계(`--anonymize`, 합성만 커밋) | 실측 수치를 낸 환경 기록(`results/environment.txt`)은 소유자가 채우기 전까지 미기록 |

## 이 저장소로 답하는 기술 질문

| 질문 | 근거 파일 | 한 줄 답 |
|---|---|---|
| 이 맵이 나오면 무엇부터 보나 | [`docs/defect_signatures.md`](docs/defect_signatures.md) 현장 순서, `python wafer_pattern_classifier.py --actions <PATTERN>` | 재테스트로 테스트 원인부터 배제 → 로트 안에서 반복되는가 → 노치 기준 방위각·스크래치 모양·슬롯 → 장비 측 로그(알람·부품 카운터·PM·티칭)를 로트 처리 시각에 맞춰 대조 → 공통성 → 관리도의 시작점 → TEL 원인/타사 인계 판정 → 초동·중간·종결 보고 |
| 합성에서 7/7인데 실측은 0.167인 이유 | [`docs/validation_log.md`](docs/validation_log.md) 실험 0~2 | 생성기와 분류기가 규칙을 공유해 7/7은 코딩 오류 확인일 뿐이다. 실측은 패턴 위에 산발 불량이 깔려 반경 통계가 바깥으로 밀리고, 합성 기준 임계값이 틀렸다(`center_r` 0.30 → 0.74). 특징별 AUC는 이미 높았으므로 특징 부재가 아니라 임계값 문제였다 |
| 알람이 헛울리면 (Laney σz) | [`docs/spc.md`](docs/spc.md) 4·6절, `wm811k_spc.py` | 같은 로트는 패턴을 공유해 로트 간 변동이 이항 분산보다 크다(과산포). baseline z의 이동범위 평균/1.128로 σz를 재서 한계를 σz배 넓힌다. baseline 부분군이 20개 미만이면 추정이 불안정해 생략하고, σz < 1은 1로 둔다(원안과 다른 의도적 보수화). baseline 알람률이 5%를 넘으면 시간 순서·안정성 자체를 의심한다 |
| NEAR_FULL이 뜨면 라인 세우나 | `ACTION_DETAIL["NEAR_FULL"]`, [`docs/defect_signatures.md`](docs/defect_signatures.md) NEAR_FULL 행, `wm811k_lot_report.py` OCAP 규칙 | 아니다, 재테스트 먼저. 프로브 카드 접촉(CRES)·테스트 프로그램 리밋·웨이퍼 ID 혼동도 전면 불량으로 찍힌다. 재테스트 후에도 남고 같은 로트의 다른 웨이퍼도 그러면 로트 이력의 비정상 종료를 장비 알람 로그와 대조해 고객 수율팀과 라인 정지를 판단한다(로트 리포트는 NEAR_FULL 2장 이상을 L3). 운영에서는 재현율 우선 — 오탐 비용은 재테스트 1회다 |
| 고객이 우리 장비 아니라고 하면 | [`docs/handoff.md`](docs/handoff.md) 1절, `wm811k_spc.py --group-col/--event-col`, `wm811k_azimuth.py`, `wm811k_commonality.py` | 증거로 답한다: TEL 챔버 통과/비통과 로트의 발생률 차이(층화 관리도의 카이제곱), 알람 시작점과 PM·부품 교체 이벤트의 거리, 노치 기준 각도가 챔버 도면·로봇 오프셋 로그와 맞는지, 공통성 분석에서 TEL 장비가 지목됐는지. 맞지 않으면 근거(CMP 직후 로트에만 생김, 샷 피치 반복 등)와 함께 타사 인계한다. "우리 장비가 아니다"를 증거 없이 말하지 않는다 |
| 오분류 9%가 현장에서 무엇을 잘못하게 하나 | [`docs/defect_signatures.md`](docs/defect_signatures.md) '오분류의 현장 비용' 표 | LOC → EDGE_LOC(5회 합산 542장)이면 파티클·리프트 핀 대신 로봇 센터링을 건드리고, SCRATCH → LOC(270장)이면 반송계 점검을 건너뛴다. 가장 비싼 오류는 NEAR_FULL 미검출(라인 정지 판단 지연)이라 분류기 앞에 `fail_frac` 하드 룰을 두고 재현율을 우선한다. 저신뢰 웨이퍼는 자동 조치에 태우지 않고 사람이 맵을 본다(LOW_CONFIDENCE 관리도) |

위 답의 수치는 전부 README·docs에 있는 것이며, 합성 데이터에서 나온 수치(탐지 시점·판정 일치)는 로직 확인이지 성능이 아니다.
