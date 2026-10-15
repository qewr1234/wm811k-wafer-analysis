# 참고문헌과 확인 수준

> 이 저장소의 문서(`defect_signatures.md`, `tel_equipment_map.md`, `process_context.md`, `handoff.md`, `glossary.md`, `case_study_8d.md`, `spc.md`, `roadmap.md`, `data/README.md`, README)가 인용하는 외부 주장을 한 곳에 모은다. 본문의 `[n]`은 아래 번호다(모든 문서가 같은 번호 체계를 쓴다). 각 항목에 **확인 수준**을 적고, '추정'·'커뮤니티'·'미확인' 등급은 **저장소 본문에 쓰지 않는다**(또는 '(추정)' 병기로만 쓴다). 장비를 만져본 적 없는 지원자가 엣지 링 RF 시간·ESC He 존·EBR 편심 같은 문장을 쓸 때, "어디서 알았나"에 대한 답이 이 파일이다.

확인일 표기: '2026-10'인 항목은 2026-10 조사 요약(웹 조사)에서 옮긴 것으로 **URL을 다시 열어 재확인하지 않았다**. '2026-10-15'인 항목은 그날 원문 URL을 직접 열어 인용 문장을 확인한 것이다. 소유자가 제출 전에 나머지 항목의 '확인일' 열을 직접 연 날짜로 갱신하는 것을 전제로 한다. 'URL 미확보'는 조사 요약에 주장만 있고 원문 링크가 없는 것이다.

확인 수준 등급:

| 등급 | 뜻 | 저장소 본문 사용 |
|---|---|---|
| 공식 | tel.com 제품 페이지, 공식 행사 자료, 공시 | 사실로 인용 |
| 특허 | 공개 특허(번호가 있으면 적음) | 사실로 인용, 예시값은 '예시'라고 적음 |
| 논문·교과서 | 학술 논문, 교과서 수준의 공정 물리·통계 | 사실로 인용 |
| 보도 | 언론 기사 | '보도 기준'으로 인용 |
| 채용 공고 | 채용 사이트에 게시된 공고 문구 | 직무명·문항은 인용, 담당업무는 소유자 원문 확인 후 |
| 2차 | 블로그, 중고장비 설명, 집계 사이트 | 보조 근거로만 |
| 커뮤니티 | 면접 후기, Q&A 답변 | **저장소 본문에 쓰지 않음** |
| 추정 | 확인되지 않았거나 일반론에서 유추한 것 | **본문에는 '(추정)' 병기로만**, 숫자는 쓰지 않음 |
| 자체 계산 | 이 저장소 코드가 데이터에서 계산한 값 | 사실로 인용하되 '저장소 계산'이라 적음 |

## A. TEL 제품·소프트웨어

| 번호 | 주장 | 출처 | 확인일 | 확인 수준 | 저장소 사용 |
|---|---|---|---|---|---|
| 1 | TEL 현행 제품명(상표 기호 생략): 코터/디벨로퍼 CLEAN TRACK LITHIUS Pro 계열(Pro Z, Pro V/V-i, Pro/Pro-i, DICE, AP), LITHIUS/LITHIUS i+, ACT 12/ACT 8Z/ACT M; 플라즈마 식각 Tactras, Episode UL, UNITY Me+; 가스 화학 식각 Certas LEAGA; 퍼니스 TELINDY PLUS(+IRad), EVAROS, TELFORMULA, ALPHA-8SE i; 단일 웨이퍼 성막 Triase+(Ti/TiN, EX-II TiN, W, SPAi), Episode 1, Episode 2 DMR, NT333, EXIM/LEXIA-EX; 세정 CELLESTA-i MD, CELLESTA MS2, EXPEDIUS-i, NS300; 프로버 Precio XL/Precio octo, Prexa MS; 본더 Synapse | https://www.tel.com/product/ | 2026-10 | 공식 | 사용. 'Trias', 'Telindy', 'Lithius' 단독 표기는 쓰지 않음 |
| 2 | TEL 제품 목록에 CMP, 노광 스캐너, 독립 검사·계측 장비가 없다 → 이 항목은 '타사 장비 인계' | https://www.tel.com/product/ (목록 부재에 근거한 해석) | 2026-10 | 공식(부재 근거) | 사용 |
| 3 | Certas LEAGA는 무액체·무플라즈마 등방성 가스 화학 식각으로 워터마크가 없다(듀얼웨이퍼 챔버 최대 6개) | https://www.tel.com/product/ | 2026-10 | 공식 | 사용 |
| 4 | LITHIUS Pro Z는 '자동 모니터링 기술', LITHIUS Pro DICE는 '강화된 데이터 수집·처리'를 공식 특징으로 적고, LITHIUS 비교표에 'Ingenio 데이터 분석'이 있다 | https://www.tel.com/product/ | 2026-10 | 공식 | 사용 |
| 5 | TELeMetrics(テレメトリックス): TEL의 원격 장비 모니터링 서비스. 2015년 시장 투입(「１５年に市場投入し」), 센서 데이터를 상시 수집해 가동 상황을 감시하고 데이터 분석으로 부품 교체·보수 시기를 예측(「部品交換や保守が必要な時期などを予測」). 기사 시점 세계 공장 도입률 약 10%를 2020년 50% 초과로 올리는 목표 | https://newswitch.jp/p/6411 (日刊工業新聞 newswitch, 2016-10-12 보도; 2015년은 출시 연도) | 2026-10-15 | 보도 | '2016년 보도 기준(2015년 출시)'으로 사용. 현재 사양·내부 구현은 모른다고 명시 |
| 6 | Ingenio: TEL의 미국 등록상표(INGENIO, 출원 2002-06-27 serial 76425095, 등록 2010-11-02 Reg. 3870729, Class 9 'electronic controller for semiconductor manufacturing machines'). 2002년 Ingenio TL ES가 TEL의 첫 APC 제품으로 Unity(200 mm)·Telius(300 mm) 식각기 대상: FDC, 툴 레벨 wafer-to-wafer 제어, 모듈 레벨 run-to-run 제어, 팹 레벨 R2R·e-Diagnostics 인터페이스. '2004년 Ingenio TL CT(CLEAN TRACK 연동)'는 조사 요약에만 있고 원문을 확인하지 못함 | https://www.eetimes.com/?p=1178969 (EE Times 'Heard on the Beat', 2002-11-02) ; 상표는 https://gleanmark.com/trademark/uspto-76425095 (USPTO 기록 집계 사이트, 2차) | 2026-10-15 | 보도 / 2차(상표 집계) | 'APC/FDC/R2R 상표'로만 사용. Ingenio TL CT(2004)는 '미확인'으로 분리. 내부 구현은 모른다고 명시 |
| 7 | TELCustomer(부품·매뉴얼·서비스 고객 포털), PN-300(프로버 데이터 관리 소프트웨어), Network-Based Prober Advanced Function(원격 운용·보수 지원) | https://www.tel.com/product/ | 2026-10 | 공식 | 사용 |
| 8 | TDX(Tool Data Extension): Ingenio와 함께 쓰는 장비 데이터 수집 모듈(오픈 API) | EDN 보도(연도 미상, URL 미확보) | 2026-10 | 보도(구형 가능) | 쓰지 않음 |
| 9 | Precio XL은 300 mm 고생산성 프로버, Prexa MS는 메모리용 전면 접촉 테스트 프로버 | https://www.tel.com/product/ | 2026-10 | 공식 | 사용 |
| 10 | CELLESTA-i(단일 웨이퍼 스핀 세정), CELLESTA MS2(양면·엣지 물리 세정), EXPEDIUS-i(배치 웻스테이션), NS300(스크러버) | https://www.tel.com/product/ | 2026-10 | 공식 | 사용 |
| 11 | Tactras: 2006년 출시, 직사각 클러스터, 최대 6챔버. 공식 페이지는 소모품·ESC를 언급하지 않는다. 'Tactras Vigus' 변종은 중고장비 시장에서만 확인 | https://www.tel.com/product/ ; 중고장비 설명(2차) | 2026-10 | 공식 / 2차 | 제품명만 사용. Vigus는 쓰지 않음 |
| 12 | TELINDY PLUS: 125매 로드, 드라이 가스 챔버 클리닝, 저O2 로딩 영역 제어, 유지보수 접근성 | 중고장비 설명(2차) | 2026-10 | 2차 | 제품명만 사용. 사양 수치는 쓰지 않음 |
| 13 | Triase+ Ti/TiN은 TiCl4 기반 CVD, Triase+ W는 WF6 기반, Episode 2 DMR은 Triase+ EX-II 후속으로 2매 동시 처리 | https://www.tel.com/product/ | 2026-10 | 공식 | 제품명만 사용 |
| 14 | 'Trias'(예: Trias SPA)는 구명칭으로 중고장비 마켓(moov.co)에만 보인다. 단종 모델명인지는 확인 안 됨 | 중고장비 마켓(2차) | 2026-10 | 2차 / 추정 | 쓰지 않음(구명칭 사용 금지의 근거로만) |

## B. 공정 물리·특허·통계

| 번호 | 주장 | 출처 | 확인일 | 확인 수준 | 저장소 사용 |
|---|---|---|---|---|---|
| 15 | 포커스 링(엣지 링)은 총 RF 시간·총 RF 전력·특정 스텝의 누적값이 임계값에 닿으면 교체 판정하는 소모품("the controller CU determines that the focus ring FR needs to be replaced when the total RF time reaches a threshold"). 임계값은 링 종류·재질별 실험 결과로 정한다("a result of an experiment performed for each type or material of the focus ring"). 교체는 반송 장치가 마모 링을 챔버 밖으로 내보내고 마운트 테이블을 세정한 뒤 새 링을 적재하며 **대기 개방 없이** 수행한다("without opening the process chamber to the atmosphere") — 즉 교체 방식·소요 시간은 장비 구성에 따라 다르며 '벤트·재인증 필수'로 단정할 수 없다 | TEL 명의 'Focus ring replacement method and plasma processing system' 특허군: US10490392 (2019-11-26) https://patents.google.com/patent/US10490392B2/en ; 연속 출원 US11990323 (2024-05-21), US12094696 (2024-09-17), US12567568 (2026-03-03) https://patents.google.com/patent/US11990323B2/en | 2026-10-15 | 특허 | 사용. 교체 소요 시간 숫자는 쓰지 않음(장비별) |
| 16 | 한 석영 부품 특허가 RF 방전 누적 약 300시간을 수명 예로 든다(장비·재질·레시피에 따라 다름, 일반 규격 아님) | 특허(번호 미확보) | 2026-10 | 특허(예시값) | '특허 예시값'으로만. PM 주기로 쓰지 않음 |
| 17 | 포커스 링 침식 → 엣지 시스 전계 왜곡 → 엣지 식각률 변화·피처 틸팅(이온 틸트). 시스 휨은 웨이퍼 표면과 링 사이 전압·기하 불일치에서 오고 침식·차징으로 드리프트. 대응은 링 높이 조절·엣지 DC 바이어스 | 논문·특허 수준(URL 미확보) | 2026-10 | 논문·특허 | 사용 |
| 18 | ESC는 중심/엣지 별도 He 공급(2~4존)과 다존 히터를 갖고, 챔버로 새는 **외부 누설**은 엣지 실 밴드(마모·폴리머 오염)와 리프트 핀 홀에서 난다. 엣지 He 냉각 약화 → 엣지 온도 상승 → 식각률 변화. 존이 분리되려면 존 사이에 내측 실 밴드가 있어야 하므로, 중심 존의 He 이상은 외부 누설이 아니라 **존 간 크로스토크**(내측 실 마모·오염으로 중심 존 He가 엣지 존으로 새어 설정 압력을 못 잡음)나 He 홀·홈의 폴리머 막힘(유량 이상)으로 나타난다 | 논문·특허 수준(URL 미확보); 존 간 크로스토크는 다존 구조에서 따르는 일반론 | 2026-10 | 논문·특허 / 일반론 | 사용. '중심 누설'(챔버로의 외부 누설)은 쓰지 않고, 중심 존 이상은 '존 간 크로스토크·홀 막힘'으로 서술 |
| 19 | VHF(약 30 MHz 이상) CCP에서 전극 지름이 유효 RF 파장의 절반 수준이 되면 정재파 효과(J0 베셀형 표면파)로 중심 전력이 높아진다(center-high). 고밀도에서는 스킨 효과가 edge-high. 둘이 겹치거나 압력이 오르면 중간 반경 극값이 생길 수 있으나 2차 효과. 정재파 프로파일은 주파수·전극 치수·플라즈마 밀도로 정해지며, **억제 수단은 전극 형상(가우시안·렌즈형 전극)·유전체 렌즈·세그먼트 전극과 주파수 구성(VHF/LF 병용)**이다. 정합기는 임피던스 정합(반사파·전달 전력)만 하지 전극 위 정재파 프로파일을 바꾸지 못한다 | Lieberman, M. A., Booth, J. P., Chabert, P., Rax, J. M., & Turner, M. M. (2002). Standing wave and skin effects in large-area, high-frequency capacitive discharges. Plasma Sources Sci. Technol., 11(3), 283-293 ; Chabert, P., Raimbault, J. L., Rax, J. M., & Lieberman, M. A. (2004). Phys. Plasmas, 11(5), 1775 ; 'Suppression of the standing wave effect in high frequency capacitive discharges using a shaped electrode and a dielectric lens: Self-consistent approach', Phys. Plasmas, 11(8), 4081-4087 (2004) https://researchportal.ip-paris.fr/en/publications/suppression-of-the-standing-wave-effect-in-high-frequency-capacit/ | 2026-10-15 (서지 확인; 본문은 초록 수준) | 논문 | 사용. 정재파는 CENTER 원인, DONUT에는 2차 효과로만. '정합기가 정재파 손잡이'라고 쓰지 않음 |
| 20 | 결함원 자동 분류(리소 공정 예시): 예시 맵 402 '웨이퍼 중심을 향한 여러 선형 결함 군집(multiple linear clusters of defects that are oriented toward the center of the wafer)' ↔ 레지스트 코팅 공급 부족(inadequate delivery of resist coating), 맵 403 '대각선 위의 조밀한 분포와 양끝 소용돌이(swirled)' ↔ 디벨로퍼 노즐 오염(contamination on the nozzle which dispensed the developing chemicals). 그 밖에 맵 401(중심 군집)·404(방사형 군집)은 접착층(adhesion layer) 공급 단계 귀속 | US6507933B1 'Automatic defect source classification', 출원인 Advanced Micro Devices(현 GlobalFoundries), 출원 1999-07-12, 등록 2003-01-14 https://patents.google.com/patent/US6507933B1/en | 2026-10-15 | 특허 | 사용. '도포량 부족'은 특허 표현대로 '레지스트 공급 부족(inadequate delivery)'으로 적음. 코터 전용 특허가 아니라 AMD의 일반 결함원 분류 특허에서 리소 예시 2개를 인용한 것 |
| 21 | EBR 노즐 끝에 남은 용제 방울의 낙하와 45° 이상 분사각의 튐이 결함을 만든다. 스핀 코팅은 원심력으로 가장자리 두께가 두껍고 불규칙 | EBR 노즐 특허(번호 미확보) | 2026-10 | 특허 | 사용 |
| 22 | EBR 폭(보통 0~6 mm, 레이어별 설정)에 걸린 엣지 다이는 전부 손실. 예시: 5.0 mm → 0.6 mm로 줄이면 손실 다이 80 → 16 | 기술 자료(URL 미확보) | 2026-10 | 2차(기술 자료) | 메커니즘만 사용, 예시 수치는 쓰지 않음 |
| 23 | EBR이 웨이퍼 중심에서 편심되면 한쪽만 과도 제거(다이 손실), 반대쪽은 미제거(막 팝핑·박리) → EDGE_LOC 모양. 너무 좁은 EBR은 경화 레지스트가 엣지 그리퍼에 닿아 플레이크 → 파티클 | 기술 자료(URL 미확보) | 2026-10 | 2차(기술 자료) | 사용 |
| 24 | 척-웨이퍼 사이 약 150 nm 이상 뒷면 파티클이 국소 디포커스(핫스팟)를 만든다. 뒷면 파티클은 CVD·스퍼터·레지스트 코팅 후 급증 | 논문·기술 자료(URL 미확보) | 2026-10 | 논문·기술 자료 | 사용 |
| 25 | 레티클(마스크) 결함은 모든 노광 샷(필드)의 같은 필드 내 좌표에 반복된다(리피터). 샷 안의 여러 다이에 같은 다이 좌표로 반복되는 것은 레티클이 아니라 공정 마진(다이 레벨 체계적 결함). 리피터 원인: 레티클 이물·크롬 결함·펠리클 손상 | 특허·기술 자료(URL 미확보) | 2026-10 | 특허·기술 자료 | 사용 |
| 26 | 프로브 카드의 **정상 터치다운**은 다이 패드에 수 µm 스크럽 마크를 남길 뿐 웨이퍼 스케일 선형 스크래치를 만들지 않는다(과도한 오버드라이브도 패드 스크래치·패시베이션 손상 수준 [76]). 프로브 원인의 빈 맵 서명은 멀티사이트 카드의 특정 사이트 불량이 터치다운 격자 주기로 반복되는 패턴, 또는 척 이동 오프셋에 따른 평행 이동. 프로브 팁 이물 → 접촉 저항(CRES) 상승 → 전체 불량; 약 2,500 터치다운에서 CRES 불안정 사례; 클리닝 시트·스크럽으로 회복. SWTW 2005 발표는 웨이퍼 테스트 수율 손실 분류에서 **프로버 측 기계 요인**으로 'Chuck overshoot', 'Index & theta error', 'Alignment & re-alignment', 'Co-plan. head plate/chuck'를 든다 — 정상 동작에서 선이 안 생긴다는 것과 Z·인덱스 고장 시 니들이 접촉 상태로 끌려 다이 격자 축에 평행한 직선이 생길 수 있다는 것은 다른 주장이며, 후자는 '예외'로 적는다(고장 모드 서술은 위 분류와 패드 손상 기록에서 유추한 일반론) | Pietzschmann, F. (IFX), 'The "probe card signature" – syndrome or who has the "old maid"', SWTW 2005, https://www.swtest.org/swtw_library/2005proc/PDF/S07_03_Pietzschmann.pdf (슬라이드 5 'Wafer Test Failure/Yield Loss Classifications', 슬라이드 10 'chuck movement (theta)') ; 2,500 터치다운 사례는 조사 요약(URL 미확보) | 2026-10-15 (SWTW 2005 PDF 열람) | 발표 자료·특허·일반론 | 메커니즘 사용. '프로브 카드는 선형 스크래치를 만들지 않는다'는 '정상 터치다운은'으로 한정하고 Z·인덱스 고장 예외(격자 축 평행 직선 → 프로버 Z·인덱스 로그 점검)를 병기. '2,500 터치다운'은 사례값이며 규격이 아님 |
| 27 | CMP 리테이닝 링 마모·두께 편차·평탄도 불량은 패드 눌림/반발을 바꿔 엣지 제거율을 올리기도(fast edge) 내리기도(slow edge) 한다. 링 안쪽 홈 마모 → 슬러리 잔류물 축적·탈락 → 스크래치 | 기술 자료(URL 미확보) | 2026-10 | 2차(기술 자료) | 사용. '과연마' 단정은 쓰지 않음 |
| 28 | CMP 스크래치 원인은 슬러리 응집체·패드 컨디셔닝 잔해·다이아몬드 그릿·금속 조각. '호 모양 = CMP'라는 기하 규칙은 인과를 적은 공개 자료를 찾지 못했고('웨이퍼 호 스크래치 검출' 특허가 있어 실무 용어인 것만 확인). 2차 자료는 scratch 클래스를 '방향·위치 무관한 직선 또는 곡선'으로만 정의 | 특허·2차(URL 미확보) | 2026-10 | 부분 검증 | '경험칙 - 절대 규칙 아님'으로만 사용 |
| 29 | 핸들링 스크래치는 로봇 블레이드 처짐(droop) 등으로 생기며 로트 안에서 방향·위치가 재현된다 | 기술 자료(URL 미확보) | 2026-10 | 2차(기술 자료) | 사용 |
| 30 | 포아송 수율 모델(Y = exp(-D0·A))은 결함이 균일·독립이라는 가정. 실측 결함은 군집하므로 Murphy·Seeds·음이항(군집 계수 α) 모델이 쓰인다 | 수율 모델 교과서 | 2026-10 | 교과서 | 사용 |
| 31 | 리프트 핀은 보통 같은 반경에 3개(120°)라 핀 서명은 '같은 반경 3점'이며 핀 1개 이상이면 그 핀 반경 위 한 점. 노치 정렬이 안 된 장비에서는 회전만 다르다 | 일반 장비 구조(교과서 수준) | 2026-10 | 교과서 | 사용 |
| 32 | 석영 보트 슬롯 하단 모서리에 파티클이 쌓여 돌기가 생기면 웨이퍼를 손상시키고, 웨이퍼-튜브 간격이 좁을수록 위치 오차가 균일도에 크게 작용하며, 석영은 열 사이클로 변형. 폴리실리콘 프리코트가 보트를 웻에치 유지보수에서 보호 | 퍼니스 특허 문헌(번호 미확보) | 2026-10 | 특허 | 사용 |
| 33 | 배치 웻벤치는 배스 오버플로 유동에 따른 세로 패턴과 가장자리 집중 결함, 단일 웨이퍼 스핀 세정은 고정 시그니처 없이 무작위 결함 밀도만 낮아짐. 스핀 세정에서는 노즐 스캔 속도·압력, 회전 중심 불일치, 이탈 액적이 국소 손상 | 특허·논문(URL 미확보) | 2026-10 | 특허·논문 | 사용 |
| 34 | 파손 웨이퍼는 보통 테스트까지 가지 않고 걸러지므로 NEAR_FULL의 현실적 원인은 테스트 쪽(프로브 카드 평탄도·오버드라이브·CRES, 테스트 프로그램 리밋, 제품/웨이퍼 ID 혼동)과 로트 이력의 비정상 종료 | 조사 요약의 추론 | 2026-10 | 추정 | '(추정)' 병기로만 |
| 35 | Laney p′: σz = 표준화 z의 이동범위 평균 / 1.128, 한계 p̄ ± 3·σ_i·σz. Western Electric 4규칙. 정규 근사 관례 n·p̄ ≥ 5 | SPC 교과서(Montgomery 등) | 2026-10 | 교과서 | 사용 |
| 36 | EWMA 관리 상태 ARL0: λ 0.2·L 2.86 → ≈ 370(이 저장소가 쓰는 값; 3σ 규칙과 같은 수준), λ 0.2·L 2.7 → ≈ 240. ARL0 ≈ 500 짝은 (λ 0.05, L 2.615), (0.10, 2.814), (0.20, 2.962), (0.25, 2.998) | Brook & Evans 마르코프 체인 근사로 자체 계산(301 상태); 표 출처는 Lucas & Saccucci (1990) Technometrics 32(1) | 2026-10-15 | 자체 계산 | docs/spc.md 5절·wm811k_spc.py 주석과 동일 값. L 을 바꾸면 데모 수치 재측정 |
| 37 | 같은 로트의 웨이퍼는 결함 패턴을 공유하므로 lotName 기준 group split이 필요하다(2026년 arXiv 논문이 같은 이유로 채택) | arXiv 논문(URL 미확보) | 2026-10 | 논문 | 설계 원칙의 보조 근거로만 |

## C. WM-811K 데이터

| 번호 | 주장 | 출처 | 확인일 | 확인 수준 | 저장소 사용 |
|---|---|---|---|---|---|
| 38 | WM-811K 원 논문. 원 논문이 적은 원인 귀속: center → 박막 증착, ring → 식각, scratch → 기계 핸들링. 전문가(domain experts) 수동 라벨 | Wu, M.-J., Jang, J.-S. R., & Chen, J.-L. (2015). Wafer map failure pattern recognition and similarity ranking for large-scale data sets. IEEE Trans. Semiconductor Manufacturing, 28(1), 1-12. MIR Lab, NTU | 2026-10 | 논문(본문은 2차 자료로 확인) | '원 논문 귀속'으로 인용 |
| 39 | 원본 811,457장, 라벨 172,950장(약 21%), 결함 8종 25,519장(Center 4,294 / Donut 555 / Edge-Loc 5,189 / Edge-Ring 9,680 / Loc 3,593 / Near-full 149 / Random 866 / Scratch 1,193), none 147,431장. 픽셀 0=다이 없음/1=정상/2=불량. TSMC 제공 | 2차 자료(데이터셋 설명·블로그) + 저장소 계산(클래스별 장수는 `prepare_wm811k.py` 출력과 일치) | 2026-10 | 2차 + 자체 계산 | 사용 |
| 40 | 로트 8,047개, 맵 크기 329종, 결함 부분집합 로트당 평균 약 3.2장(25,519 / 8,047 = 3.17) | 저장소 코드 계산 | 2026-10 | 자체 계산 | '저장소 계산'이라 적고 사용 |
| 41 | 전체 로트 수는 자료마다 다르다: 46,293(Kaggle) / 46,393 / 47,543 | 2차 자료 | 2026-10 | 2차 | 쓰지 않음(불일치 기록용) |
| 42 | Kaggle 'WM-811K wafer map' 데이터셋의 라이선스 필드는 페이지가 JS 렌더링이라 확인하지 못함. MIR Lab 배포 조건도 미확인 | Kaggle(로그인 후 소유자 확인 필요) | 2026-10 | 미확인 | 실측 썸네일 재배포는 소유자 확인 전까지 보류 |
| 43 | '웨이퍼 테스트(CP) 빈 맵'이라는 표현은 원 논문 본문으로 확인하지 못했다. 2차 자료는 'real-world fabrication, 픽셀 0/1/2'까지만 말한다. 다이 단위 pass/fail이므로 테스트 결과임은 사실상 확실하나 원 논문 인용처럼 쓰지 않는다 | 조사 요약 | 2026-10 | 추정(데이터 형식에서 유추) | '다이 단위 pass/fail 맵(사실상 웨이퍼 테스트 빈 맵)'으로만 서술 |
| 44 | WM-811K 로트는 25장 묶음(waferIndex 1~25). 단, 결함 라벨 부분집합에서는 로트당 평균 3.2장 | NYC Data Science 블로그(2차, URL 미확보) + 저장소 계산 | 2026-10 | 2차 + 자체 계산 | '원본 기준 25장, 결함 부분집합 3.2장'으로 사용 |
| 45 | MixedWM38: 혼합 패턴 공개 데이터(1 정상 + 8 단일 + 29 혼합, 52×52, 0/1/2 인코딩 동일). 일부 GAN 생성, 라이선스는 README 확인 필요 | 2차(URL 미확보) | 2026-10 | 2차 | 로드맵에서만 언급 |
| 46 | WM-811K 배열 방향과 물리 노치의 대응은 데이터셋 문서에 없다. waferIndex가 물리 보트/카세트 슬롯과 같다는 보장도 없다 | 데이터셋 문서 부재 | 2026-10 | 추정 | 방위각은 '로트 안 상대 각도', 슬롯은 '대리 변수'로만 서술 |

## D. TEL Korea 채용·조직

| 번호 | 주장 | 출처 | 확인일 | 확인 수준 | 저장소 사용 |
|---|---|---|---|---|---|
| 47 | 2026 하반기 공채 직무 목록: 인턴(채용연계형) 12개 직무에 'Software Engineer - Tech Support Engineer', 'Software Engineer - System & Solution Engineer', 'Engineer Operation Analyst', 'System Engineer' 포함. 경력 16개 직무(Field Engineer: Etching System_화성·평택·이천·청주·용인 / Single Wafer Deposition / Surface Preparation System; Process Engineer: Etching System_용인 / Module Process and Integration / Assemble & Test System / Thermal Processing / Single Wafer Deposition / Surface Preparation System - Wet Clean_평택·이천 등)에는 SW·Tech Support 직무가 없다. 접수 마감 10/18 14:59(자소설) | https://jasoseol.com/recruit/106551 | 2026-10-15 | 채용 사이트(집계) | 직무명만 인용. 담당업무는 소유자가 공고 원문(tel.recruiter.co.kr)에서 확인 후 적음 |
| 48 | 2026 하반기 공채: 접수 10/5~10/18, 온라인 설명회 'TEL-人 Session' 10/13, 서류 → (신입) AI 역량검사 → 1·2차 면접(11월) → 2027년 1월 입사. 자소서 문항은 '직무가 요구하는 경험·역량' 중심으로 개편 | https://m.inews24.com/v/2011896 (2026-10-06) | 2026-10 | 보도 | 일정만 인용 |
| 49 | 2026 상반기 공채 기사: 신입 AI 역량검사 후 1·2차 면접, 경력은 실무 역량 중심 면접. 입사 후 2주 집체교육 'TEL-SHIP', 4주 일본어 연수 'JapanEase', 6개월 현업 멘토링, 경력직 'TEL Culture Program'. 일반 자격: 해외근무 결격사유 없는 자, 남자는 군필 또는 그에 준하는 자 | https://www.heraldk.com/article/2026041222515547967 | 2026-10 | 보도 | 교육 프로그램명만 인용 |
| 50 | 자소서 문항 전 직무 공통 2개: "직무를 선택한 이유와 직무 수행에 활용할 수 있는 경험·역량을 구체적 사례 중심으로", "협업 과정의 문제를 해결하기 위한 판단·행동과 결과". 접수 마감 10/18 23:59(하이잡) - 자소설(14:59)과 다름 | https://www.haijob.co.kr/posting/13943 | 2026-10 | 채용 사이트 | 문항 인용. 마감 시각은 소유자가 원문 확인 |
| 51 | 2026 하반기 공채 기사. 'Technical Support Engineer'라는 독립 직무명은 없고 가장 가까운 경력 직무는 Field Engineer | https://mbiz.heraldcorp.com/article/10893919 | 2026-10 | 보도 | [47]과 함께 읽음: 인턴 트랙에는 'Software Engineer - Tech Support Engineer'가 있음 |
| 52 | TEL Korea 내부에 'Etching System, Technical support team'이 존재하며 RF 기술지원을 맡는다 | https://www.semiconkorea.org/en/node/7236 | 2026-10 | 공식(행사 자료) | 팀 존재 사실만 인용 |
| 53 | TEL Korea FE 경력 공고 담당업무: 설비 HW/SW 트러블슈팅, 긴급 부품 수배, 작업지시서·보고서 작성, 본사 및 해외 각국 법인과 협업·소통하며 설비 HW/SW 개선. 우대: JLPT N3(경력 Etching FE는 N2)·TOEIC 700, '장비 구조 및 진공·RF·플라즈마·가스·반송계 이해'. 근무지 주소: 화성(삼성1로1길 56), 평택(고덕중앙로 304), 이천(경충대로 2056), 청주(풍산로 15) | https://lab.incruit.com/jobs/2606130000077 | 2026-10 | 채용 공고 | 요건 문구 인용 |
| 54 | 2025 상반기 FE/PE 공고: FE '설치·시동 후 고객 창구로서 사후 지원(수리·점검·개조), 장애 대응 방안 수립', PE '고객 니즈 파악 → 실험·평가·분석, 공정 셋업과 트러블 대응', '작업지시서 작성, CIP(지속 개선) 개발 대응' | https://linkareer.com/activity/240092 | 2026-10 | 채용 공고 | 업무 문구 인용 |
| 55 | 2024년 10월 경력 Software Engineer 공고(동탄): 담당업무 '설비·고객 데이터 분석 결과의 웹 애플리케이션 시각화(TTTM 분석, 근본원인, 생산성 KPI), 빅데이터 전처리, DX'. 자격: 영어 가능. 우대: JLPT N3/JPT 500, Hadoop/Kafka/Python/C#/Java/Spring/ELK/AWS/K8s/Docker | 채용 공고(URL 미확보) | 2026-10 | 채용 공고 | 직무 대응표에 인용 가능하나 소유자가 원문 확인 |
| 56 | Tokyo Electron Korea Ltd.: 1993년 9월 설립(구 Tokyo Electron FE Korea Ltd. 인수), 2012년 4월 Tokyo Electron Korea Solution Ltd.(2006년 2월 설립)와 합병. 자소설닷컴의 '설립 2006년'은 합병 전 Solution 법인 기준으로 추정 | 일본 EDINET 유가증권보고서(URL 미확보) | 2026-10 | 공식(공시) / 2차 | 설립연도는 공시 기준으로만 |
| 57 | 본사 경기 화성시 삼성1로1길 56(동탄). 근무지 화성·평택·이천·청주·발안. 2027년 1월 용인 R&D센터(원삼 일반산단 2만 7,032㎡) 가동 예정 | 2026 공고·보도 | 2026-10 | 채용 공고·보도 | 법인명·사업장은 확인 범위만 |
| 58 | TEL Technology Center Korea-2(TTCK-2): "2024년 10월 준공된 도쿄일렉트론코리아의 국내 세 번째 R&D 거점", 삼성전자를 위한 전용 연구 팹, "고객사의 평가용 웨이퍼가 들어온 뒤 빠르면 24시간 안에 공정 평가", 증착(TFF)·식각(ES)·계측·검사(MI, CD-SEM) 장비 보유 | https://inews24.com/view/1999255 (아이뉴스24 르포 '[르포]"웨이퍼 오면 24시간 안에 평가"…', 2026-08-28; '2024년 10월 준공'은 기사 본문의 사실 서술) | 2026-10-15 | 보도 | '2026-08 보도 기준(준공 2024-10)'으로만. '24시간 내 평가'는 운영 세부를 모른다고 명시 |
| 59 | 사원수 2,287명, 매출 1조 5,288억 원(기준 연도 미표기) | 자소설닷컴(2차) | 2026-10 | 2차 | 쓰지 않음 |
| 60 | TEL 해외(독일/미국/일본) FE 공고: '설치·유지보수·트러블슈팅·고객 보고', '화학물질·고전압·가동 기계·방사선 안전 절차 준수', '큰 불량 시 스스로 장치 분석·해석 수행' | 해외 채용 공고(URL 미확보) | 2026-10 | 채용 공고 | 안전·업무 문구의 보조 근거 |
| 61 | 면접 후기: 'Alarm/트러블 → 접근 → 원인 분석 → 조치 → 결과' 순서의 사례 설명, '왜 FE인가', '장비가 멈추면 무엇부터 확인하겠는가', '도구 중심 설명은 약하다' | https://comento.kr/job-questions/도쿄일렉트론코리아/필드엔지니어/도쿄일렉트론_코리아 fe 경력직 면접 질문 드립니다-626872 ; …/tel_2차 면접질문 드립니다-629058 ; …/tel_필드엔지니어 서류 작성 중인데 현직자분들 조언 부탁드립니다-633125 (URL은 조사 요약 표기 그대로) | 2026-10 | 커뮤니티 | **저장소 본문에 쓰지 않음** |
| 62 | 타사(Lam Research, Applied Materials) 면접·공고는 8D·5Why·Ishikawa를 명시적으로 묻는다 | https://static.glassdoor.at/Interview/Lam-Research-Interview-E1582-RVW15018103.htm ; https://jobs.appliedmaterials.com/job/hsinchu/operations-and-customer-quality-engineer/95/91045577072 | 2026-10 | 커뮤니티 / 타사 공고 | 저장소 본문에 쓰지 않음(8D 양식 채택의 배경으로만) |
| 63 | 'FE 상시채용 장비군 목록 안에 Technical Support가 있다' | 검색 요약(1차 자료 미확인) | 2026-10 | 추정 | **쓰지 않음** |
| 64 | 'LITHIUS Pro Z+' 제품명 | 미확인 | 2026-10 | 미확인 | **쓰지 않음** |
| 65 | 교대근무·팹 상주 조건, 고객사 배정(화성·평택=삼성, 이천·청주=SK하이닉스), 천안·파주 사업장 | 커뮤니티 답변 | 2026-10 | 커뮤니티 | **쓰지 않음** |
| 66 | 담당 HR 메일(tekrecruit@tel.com) | 검색 요약(미검증) | 2026-10 | 미검증 | **쓰지 않음** |
| 67 | TEL Values 문구 | 2차 자료 | 2026-10 | 2차 | 쓰지 않음 |

## E. 추정 등급 모음(본문에 숫자로 쓰지 않는 것)

| 번호 | 주장 | 근거 | 확인 수준 | 저장소 사용 |
|---|---|---|---|---|
| 68 | TEL 매뉴얼 기준 PM 주기, 부품 교체 기준(노즐·컵 세정 주기, EBR 폭 점검 주기, 샤워헤드·챔버 라이너 교체, 시즈닝 레시피), 엣지 링 교체 소요 시간(장비 구성에 따라 벤트·재인증이 따르거나 대기 개방 없이 자동 교체 [15]) | 공개 자료 없음 | 추정 | '(추정)' 병기로만, 숫자 없음('수 시간~수 일' 같은 범위도 쓰지 않음) |
| 69 | SEMI E10(장비 RAM 6상태·MTBF/MTTR), E125/E134(장비 데이터 수집·DCP), E142(기판 맵 XML), S2/S8(장비 EHS·인간공학), ISO 14644-1(클린룸) | 표준 명칭 수준만 인용, 본문 미열람 | 표준(명칭만) | 명칭만 인용 |
| 70 | 코터 베이크 플레이트 존 경계가 DONUT을 만든다 | 다존 히터 일반론에서 유추 | 추정 | '(추정)' 병기로만 |
| 71 | WM-811K 실측에 0 패딩·비대칭 맵이 얼마나 있는지, 전부 skipped인 로트가 있는지 | 이 환경(LSWMD.pkl 없음)에서 확인 불가 | 추정 | 한계로만 기록 |

## F. 2026-10-15 추가 확인

| 번호 | 주장 | 출처 | 확인일 | 확인 수준 | 저장소 사용 |
|---|---|---|---|---|---|
| 72 | 포커스 링 교체 시점을 식각 패턴의 형상·CD 측정으로 판정하는 TEL 특허: 분광 엘립소미터로 웨이퍼 여러 위치의 CD·측벽각을 재고 그 산포가 임계값을 넘으면 교체 판정("determining the replacement time of the focus ring based on the measured shape or the measured critical dimension of the pattern"); 링 온도 피드백 제어 변형도 기술 | US9396911B2 'Determination method, control method, determination apparatus, pattern forming system and program', Tokyo Electron Ltd, 2016-07-19 https://patents.google.com/patent/US9396911B2/en | 2026-10-15 | 특허 | '보정 손잡이 한계 = 교체 시점' 옆에 'CD·프로파일 측정 기반 판정 특허도 있다'로 사용 |
| 73 | 브러시 스크러버는 CMP 후세정의 대표 장비이며, TEL 현행 세정 제품군에 스크러버 NS300 계열(NS300, NS300Z, NS300+ HT, NS300+ 200mm Conversion)이 있다. 따라서 CMP 일체형 후세정 모듈의 브러시는 CMP(타사) 항목이지만, 독립 스크러버 NS300으로 후세정하는 라인이면 브러시 자국(압력·PVA 브러시 마모)은 TEL 범위 | https://www.tel.com/product/ (Cleaning > Scrubber System, 2026-10-15 확인) ; 브러시 후세정 일반: US5639311 'Method of cleaning brushes used in post CMP semiconductor wafer cleaning operations'(번호는 조사 요약, 본문 미열람) | 2026-10-15 (제품 목록) / 2026-10 (특허) | 공식 / 특허(명칭만) | 'CMP 후세정 브러시 = 전부 타사'로 쓰지 않고 일체형/독립 스크러버를 구분 |
| 74 | I-MR 관리도의 일본 표준 표기: JIS Z 9020-2:2023 6.2 'X 管理図（個々の測定値の管理図）及び Rm 管理図（移動範囲管理図）' | https://webdesk.jsa.or.jp/preview/pre_jis_z_09020_002_000_2023_j_ed10_ch.pdf (목차 미리보기, p.3) | 2026-10-15 | 표준(목차) | glossary #78 일본어 열 |
| 75 | 'シーズニング（チャンバーシーズニング）', 'リピータ欠陥（繰返し欠陥）', '径方向プロファイル'는 반도체 장비·검사 분야의 통용 일본어 기술 용어(JIS 용어 아님) | 업계 통용 표기(1차 표준 자료 없음) | 2026-10-15 | 2차(통용 표기) | glossary #10·#39·#85에 '통용 기술 용어(JIS 아님)' 비고로 사용 |
| 76 | 프로브 오버드라이브 스크럽은 본드 패드에 "significant scrub line … or significant scratch damage to the bond pad"를 남기고 과도하면 패시베이션층도 손상시킨다 — 즉 정상·과도 접촉의 손상은 패드 스케일이다 | US5773987A 'Method for probing a semiconductor wafer using a motor controlled scrub process', Motorola https://patents.google.com/patent/US5773987A/en | 2026-10-15 | 특허 | [26]의 '정상 터치다운은 웨이퍼 스케일 선을 만들지 않는다'의 보조 근거 |

## 통합 메모

- 2026-10-15에 `tel_equipment_map.md`, `process_context.md`, `handoff.md`의 자체 출처 번호를 이 파일 번호로 치환했다(통합 완료). 이제 저장소 안의 모든 `[n]`은 이 파일 번호이며, 각 문서 끝에는 "출처: `references.md` [n, …]" 한 줄만 둔다. `glossary.md`는 번호 없이 이 파일을 가리킨다.
- 이 파일에 없는 외부 주장을 저장소 본문에 새로 쓸 때는 여기에 행을 추가한다. 확인 수준을 못 적는 주장은 본문에 넣지 않는다.
