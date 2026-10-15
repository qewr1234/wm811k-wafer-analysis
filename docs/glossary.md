# 용어 대조표 — 한국어 / English / 日本語

> 한 줄 요약: 이 저장소의 문서·코드·보고서에 나오는 장비·공정·품질·통계 용어 87개를 한/영/일로 대조한다(행을 더하거나 뺄 때 이 숫자를 함께 고친다). 일본어는 표준 기술 용어만 적었고, 확신이 없는 것은 비워 두고 '미확인'으로 표시했다(기계 번역을 넣지 않는다).

사용 목적: (1) 한국 고객 현장 ↔ 일본 본사 ↔ 영문 보고서 사이에서 같은 부품·현상을 같은 말로 부르기 위해, (2) `docs/` 문서와 `wafer_pattern_classifier.ACTION_DETAIL`의 용어를 고정하기 위해. 일본어 열의 '미확인'은 해당 용어를 모른다는 뜻이 아니라 **표준 표기를 확인하지 못했다**는 뜻이며, 소유자가 일본어 자료(매뉴얼·JIS·사내 용어집)로 확인한 뒤 채운다.

## 1. 장비·부품

| # | 한국어 | English | 日本語 | 비고 (이 저장소에서의 쓰임) |
|---|---|---|---|---|
| 1 | 엣지 링 (포커스 링) | edge ring (focus ring) | フォーカスリング (エッジリング) | 플라즈마 식각 소모품. 마모 → 시스 왜곡 → EDGE_RING. 누적 RF 시간으로 교체 시점 판단 |
| 2 | 정전척 | electrostatic chuck (ESC) | 静電チャック | 중심/엣지 존 온도·He 압력. CENTER / EDGE_RING 점검 항목 |
| 3 | He 백사이드 냉각 | helium backside cooling | 미확인 | 챔버로의 외부 누설은 엣지 실 밴드·리프트 핀 홀에서 난다('중심 누설'은 쓰지 않는다). 중심 존 이상은 존 간 크로스토크·He 홀 막힘으로 서술 |
| 4 | 엣지 실 밴드 | edge seal band | 미확인 | ESC 바깥 둘레의 He 밀봉부. 마모·폴리머 오염 → He 누설 → 엣지 온도 상승. 존 사이의 내측 실 밴드가 새면 존 간 크로스토크 |
| 5 | 샤워헤드 | showerhead | シャワーヘッド | 가스 분배 상부 전극. 중심 홀 막힘 → CENTER |
| 6 | 리프트 핀 | lift pin | リフトピン | 보통 같은 반경 3개(120°). 핀 서명은 LOC 행의 '같은 반경 3점' |
| 7 | 플라즈마 시스 | plasma sheath | プラズマシース | 웨이퍼 끝에서 휘어 이온 입사각·식각률이 달라진다 |
| 8 | 정재파 효과 | standing wave effect | 定在波効果 | VHF CCP에서 center-high. CENTER 원인(DONUT 아님) |
| 9 | 스킨 효과 | skin effect | 表皮効果 | 고밀도에서 edge-high. 정재파와 겹치면 DONUT(2차 효과) |
| 10 | 챔버 시즈닝 | chamber seasoning | シーズニング（チャンバーシーズニング） | PM 직후 챔버 벽 안정화. '시즈닝 후 경과 매수'가 파티클 관리의 축. 일본어는 통용 기술 용어(JIS 아님) |
| 11 | 챔버 라이너 | chamber liner | チャンバーライナー | 벽 박리 파티클 샤워 → LOC / RANDOM |
| 12 | 상부 전극 | upper electrode | 上部電極 | CCP 식각기의 상부. 중심 전력 분포 |
| 13 | 정합기 | RF matching network (matcher) | 整合器 | 정합기 설정·반사파 로그는 전력 전달 이상을 보는 장비 측 증거. 정재파(center-high) 프로파일의 손잡이는 아니다 |
| 14 | 코터/디벨로퍼 (트랙) | coater/developer (track) | コータ・デベロッパ | CLEAN TRACK LITHIUS Pro 계열 |
| 15 | EBR (엣지 비드 제거) | edge bead removal (EBR) | エッジビード除去 (EBR) | 폭 설정 불일치 → EDGE_RING, 편심 → EDGE_LOC, 너무 좁음 → 플레이크 파티클 |
| 16 | 베이크 플레이트 | bake plate (hot plate) | ベークプレート (ホットプレート) | 존 경계 → DONUT (추정) |
| 17 | 배치 퍼니스 (종형로) | vertical batch furnace | 縦型炉 | TELINDY PLUS. 보트 슬롯 위치별 패턴 비율 변화가 서명 |
| 18 | 보트 슬롯 | boat slot | ボートスロット | 석영 보트의 웨이퍼 자리. 슬롯 파티클 → LOC |
| 19 | 석영 튜브 | quartz tube | 石英チューブ | 열 사이클 변형 |
| 20 | 단일 웨이퍼 (매엽식) | single-wafer | 枚葉式 | 배치(バッチ式)와 대비. 세정기 CELLESTA(매엽) vs EXPEDIUS(배치) |
| 21 | 웨이퍼 프로버 | wafer prober | ウェーハプローバ | Precio / Prexa. NEAR_FULL·격자 주기 반복과 연결. 정상 동작에서는 SCRATCH 원인이 아니고, Z축·인덱스 이상 시 격자 축 평행 직선이 예외 |
| 22 | 프로브 카드 | probe card | プローブカード | 접촉 저항·평탄도·오버드라이브. 재테스트로 먼저 배제. 카드 자체는 카드 벤더 소모품, 접촉 조건은 프로버(TEL) 범위 |
| 23 | 터치다운 | touchdown | タッチダウン | 프로브 카드가 웨이퍼에 한 번 닿는 단위. 터치다운 격자 주기 = 프로버 서명 |
| 24 | 접촉 저항 | contact resistance (CRES) | 接触抵抗 | 프로브 팁 이물 → 상승 → 전면 불량 |
| 25 | 반송 로봇 | wafer transfer robot | 搬送ロボット | 센터링·티칭 로그. 제각각 각도의 EDGE_LOC, 직선 SCRATCH |
| 26 | 엔드이펙터 | end effector | エンドエフェクタ | 로봇 손끝. 패드 상태·끌림 |
| 27 | 얼라이너 | aligner (notch aligner) | アライナ | 노치 정렬 오류 → 같은 패턴이 웨이퍼마다 다른 각도 |
| 28 | EFEM | equipment front end module | EFEM | 로드포트·로봇·얼라이너를 묶은 대기압 반송부. 모든 TEL 장비 공통 |
| 29 | FOUP | front opening unified pod | FOUP | 슬롯 끌림 → 직선 SCRATCH, 엣지 치핑 |
| 30 | 노치 | notch | ノッチ | 방위각 기준점. WM-811K 배열과 물리 노치의 대응은 미확인 |
| 31 | 인터락 | interlock | インターロック | 안전·공정 조건 위반 시 동작 차단 |
| 32 | 알람·이벤트 로그 | alarm / event log | アラームログ | 장비 측 증거의 첫 항목. 시각 대조의 기준 |
| 33 | 레시피 | recipe | レシピ | 변경 이력은 장비 측 증거 |
| 34 | 클린룸 클래스 | cleanroom class (ISO 14644-1) | クリーンルームの清浄度クラス | 체크리스트 항목(`process_context.md`) |

## 2. 결함·공정 현상

| # | 한국어 | English | 日本語 | 비고 |
|---|---|---|---|---|
| 35 | 웨이퍼 맵 | wafer map | ウェーハマップ | 이 저장소의 입력 |
| 36 | 빈 맵 | bin map | ビンマップ | 다이 단위 pass/fail(bin) 지도. WM-811K는 사실상 웨이퍼 테스트 빈 맵 |
| 37 | 파라메트릭 맵 | parametric map | 미확인 | 두께·CD 같은 연속값 분포. `plotly_wafer_heatmap.py` |
| 38 | 파티클 | particle | パーティクル | RANDOM / LOC |
| 39 | 리피터 (반복 결함) | repeater defect | リピータ欠陥（繰返し欠陥） | 모든 샷의 같은 필드 내 좌표에 반복 → 레티클. 일본어는 통용 기술 용어(JIS 아님) |
| 40 | 레티클 (마스크) | reticle (photomask) | レチクル | 타사(노광) 인계 |
| 41 | 샷 (노광 필드) | shot (exposure field) | ショット | 샷 피치 반복 = 레티클, 다이 피치 반복 = 공정 마진 |
| 42 | 뒷면 파티클 | backside particle | 裏面パーティクル | 노광 핫스팟(국소 디포커스) → LOC |
| 43 | 스크래치 | scratch | スクラッチ | 호(주로 CMP, 타사) vs 직선(주로 핸들링) - 경험칙 |
| 44 | 워터마크 | watermark | ウォーターマーク | 세정·건조 결함. Certas LEAGA는 무액체라 없음 |
| 45 | 균일도 | uniformity | 均一性 | 웨이퍼 내(WIW) 두께·CD·식각률 분포 |
| 46 | 수율 | yield | 歩留まり | 다이 수 기준. WM-811K는 다이 실제 크기를 모른다 |
| 47 | 로트 홀드 | lot hold | ロットホールド | ACTION_DETAIL severity 'lot_hold' |
| 48 | 공통성 분석 | (tool) commonality analysis | 미확인 | 불량 로트들이 공유한 장비·챔버 찾기. `--group-col` |

## 3. 품질·보전·관리 용어

| # | 한국어 | English | 日本語 | 비고 |
|---|---|---|---|---|
| 49 | 예방보전 | preventive maintenance (PM) | 予防保全 | 주기·항목은 TEL 매뉴얼 기준이며 이 저장소는 모른다(추정 표시) |
| 50 | 사후보전 | corrective (breakdown) maintenance | 事後保全 | 비예정 정지에 해당 |
| 51 | 소모품 | consumable part | 消耗品 | 엣지 링, 실 밴드, 프로브 카드 클리닝 시트 등 |
| 52 | 누적 RF 시간 | accumulated RF hours | 積算RF時間 | 엣지 링 교체 기준(특허군). 표기는 일반 용어 조합 |
| 53 | SEMI E10 6상태 | SEMI E10 equipment states | 미확인 | 아래 소표 |
| 54 | MTBF | mean time between failures | 平均故障間隔 | |
| 55 | MTTR | mean time to repair | 平均修復時間 | |
| 56 | OEE | overall equipment effectiveness | 設備総合効率 | |
| 57 | OCAP | out-of-control action plan | 미확인 | 관리도 알람 → 누가 무엇을 언제까지 |
| 58 | 8D | eight disciplines (8D report) | 8D | D1 팀 ~ D8 종결. `handoff.md`에 D1 역할 |
| 59 | 5-why | 5 whys | なぜなぜ分析 | 근본원인 추적 |
| 60 | 특성요인도 (이시카와) | Ishikawa (fishbone) diagram | 特性要因図 | 6M 분류 |
| 61 | 근본원인 분석 | root cause analysis (RCA) | 根本原因分析 | |
| 62 | 시정 조치 / 재발 방지 | corrective action / recurrence prevention | 是正処置 / 再発防止 | 8D D5 / D7 |
| 63 | 봉쇄 조치 | containment | 미확인 | 8D D3. 로트 홀드·재테스트·장비 격리 |
| 64 | 에스컬레이션 | escalation | エスカレーション | 고객 → FE → PE → 본사 |
| 65 | 기밀 유지 계약 | non-disclosure agreement (NDA) | 秘密保持契約 | 고객 데이터 취급 원칙(`handoff.md`) |
| 66 | FDC | fault detection and classification | FDC | 장비 센서 기반 이상 탐지. Ingenio가 TEL의 APC/FDC 상표 |
| 67 | APC | advanced process control | APC | |
| 68 | R2R | run-to-run control | R2R (ランツーラン制御) | EWMA가 결과 쪽에서 보는 느린 이동 |

SEMI E10 6상태 (한/영; 일본어 표준 표기 미확인):

| 상태 | English |
|---|---|
| 생산 | productive |
| 대기 | standby |
| 엔지니어링 | engineering |
| 예정 정지 | scheduled downtime |
| 비예정 정지 | unscheduled downtime |
| 비가동 (계획 외) | non-scheduled time |

## 4. 이 저장소의 통계·지표 용어

| # | 한국어 | English | 日本語 | 비고 |
|---|---|---|---|---|
| 69 | 관리도 | control chart | 管理図 | `wm811k_spc.py` |
| 70 | 부분군 | subgroup | 群 (サブグループ) | 부분군 크기 n_i가 달라도 한계를 매번 다시 계산 |
| 71 | 관리 한계 | control limits (UCL/LCL) | 管理限界 | |
| 72 | 중심선 | center line | 中心線 | p-bar |
| 73 | 과산포 | overdispersion | 過分散 | 로트 간 변동 > 이항 분산. Laney 보정의 이유 |
| 74 | Laney p' 관리도 | Laney p' chart | 미확인 | sigma_z = 이동범위 평균 / 1.128 |
| 75 | EWMA | exponentially weighted moving average | 指数加重移動平均 | lambda 0.2, L 2.86 |
| 76 | Western Electric 규칙 | Western Electric rules | 미확인 | R1~R4 |
| 77 | Phase I / Phase II | Phase I (limit setting) / Phase II (monitoring) | 미확인 | baseline 50 %에서만 한계 설정 |
| 78 | I-MR 관리도 | individuals and moving range chart | X管理図及びRm管理図（個々の測定値の管理図及び移動範囲管理図） | FAIL_FRAC_MEAN. 일본어는 JIS Z 9020-2:2023 6.2 표제 |
| 79 | 구성비 효과 | compositional effect | 미확인 | 점유율 합이 1이라 한 패턴 상승이 다른 패턴 하강으로 보임 |
| 80 | macro-F1 | macro-averaged F1 | マクロF1 | 결함 8종 고정. 65배 불균형이라 accuracy 무의미 |
| 81 | 로트 분할 | lot-level (group) split | ロット単位分割 | 같은 로트의 웨이퍼가 train/test에 섞이면 누수. 일반 번역이며 고정 용어 아님 |
| 82 | 혼동 행렬 | confusion matrix | 混同行列 | |
| 83 | AUC | area under the ROC curve | AUC | 특징별 단일 AUC로 '어떤 특징이 어떤 물리를 재는가' 검증 |
| 84 | 연결 성분 | connected component | 連結成分 | 8-이웃. 최대 성분의 세장비·무게중심 반경 |
| 85 | 반경 프로파일 | radial profile | 径方向プロファイル | prof0~prof4 (반경 구간별 불량률 비). 일본어는 통용 기술 용어(JIS 아님) |
| 86 | 방위각 | azimuth angle | 方位角 | 노치 기준. 로트 안 같은 각도 = 챔버 고정 요소 |
| 87 | 포아송 / 음이항 수율 모델 | Poisson / negative binomial yield model | ポアソン分布 / 負の二項分布 | RANDOM은 포아송 전제 영역, 실제 팹은 군집 때문에 음이항(군집 계수)이 더 맞음 |

## 출처

- 제품명·장비군: https://www.tel.com/product/ (2026-10 확인).
- 공정 물리 용어의 쓰임: [`defect_signatures.md`](defect_signatures.md), [`tel_equipment_map.md`](tel_equipment_map.md), `wafer_pattern_classifier.ACTION_DETAIL`.
- SPC 용어: `wm811k_spc.py` 머리 주석(Laney p', Western Electric, EWMA, Phase I/II).
- SEMI E10(장비 RAM 6상태), SEMI E125/E134(장비 데이터 수집)는 표준 명칭 수준만 인용. 본문은 열람하지 않았다.
- 일본어 표기: 일반 기술 용어(JIS·교과서 수준)만 적었고 '미확인'은 소유자가 일본어 1차 자료로 확인 후 채운다. 기계 번역은 넣지 않았다. #78은 JIS Z 9020-2:2023 목차(6.2) 표제, #10·#39·#85는 업계 통용 표기(JIS 용어 아님)로 비고에 그렇게 적었다 — [`references.md`](references.md) [74][75].
- 외부 주장의 확인 수준·URL은 [`references.md`](references.md)(번호 체계는 저장소 공통).
