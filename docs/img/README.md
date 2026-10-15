# docs/img - 문서용 그림 (전부 합성 데이터)

이 폴더의 그림은 **전부 합성 데이터**로 `python make_figures.py` 가 만든다. 그림 속 일치율·탐지 시점·판정은 로직 확인이지 성능이 아니다. 실측 수치는 README 의 WM-811K 결과뿐이다. 실제 장비·고객 데이터는 없고, Tool/Chamber 같은 식별자는 빈 양식이다.

| 파일 | 생성 (`python make_figures.py --only <name>`) | 대체 텍스트 | 내용 |
|---|---|---|---|
| `wafer_patterns_synthetic.png` | `patterns` | 합성 웨이퍼 맵 8종을 2x4 로 늘어놓은 격자: 엣지 링, 센터, 도넛, 엣지 국소, 스크래치, 국소, 무작위, 전면 불량. 초록 PASS, 빨강 FAIL, 아래 삼각형 노치 | 합성 웨이퍼 맵 8종 2x4 격자 (`tests/synthetic_wm811k.make_wafermap`). 노치는 아래(가정 notch_deg=-90). LOC 패널은 덩어리 1개가 보이는 시드를 따로 골랐다(`PANEL_SEED`). |
| `spc_demo.png` | `spc` | 패턴별 p 관리도 8개를 세로로 쌓은 그림. EDGE_RING 은 웨이퍼 3000부터 드리프트, SCRATCH 는 4125부터 계단, 저신뢰 비율은 3750부터 증가하며 알람 점이 표시된다 | `python wm811k_spc.py --demo` 의 관리도. 웨이퍼 3000부터 EDGE_RING 드리프트, 3750부터 저신뢰 증가, 4125부터 SCRATCH 계단을 심은 합성 시퀀스. |
| `spc_demo_chamber.png` | `spc_chamber` | 챔버 A/B 로 층화한 관리도 11개. B 챔버 관리도에만 드리프트·계단이 있고 이벤트(pm_wet_clean, focus_ring_replaced)가 세로 점선으로 표시된다. 세로로 길어 docs/img 에서 원본 크기로 볼 것 | 같은 데모를 `--group-col chamber --event-col event` 로 층화한 것. 심은 이상은 B 챔버에만 있고 이벤트(pm_wet_clean, focus_ring_replaced)가 세로 점선. 1560x3016 으로 세로로 길다. |
| `pipeline.svg` | `pipeline` | 8단계 흐름도: 웨이퍼 맵 -> 분류 -> 패턴 8종 -> 로트 안 판정 -> 장비 측 증거 대조 -> TEL 원인 / 타사 인계 -> SPC 추세·이벤트 -> 보고, 8 에서 7 로 되돌아가는 점선 | 흐름도. 글자를 경로로 저장해 폰트 없는 환경에서도 한글이 보인다. 같은 대체 텍스트가 SVG `<title>`/`<desc>` 에 들어 있다. |
| `service_report_page.png` | `service_report` | A4 세로 서비스 리포트 양식 1장: 머리 표(장비·챔버·로트·일자·심각도·영향 범위·봉쇄 조치 제안·보고 단계·다음 보고 예정), 현상, 분류 결과, 의심 원인 순위, 권고 조치, 후속 확인(SPC 알람 해제 기준), 증거 체크박스, 비고 빈 줄, 서명란 | `batch_wafer_report.build_service_report_page` 의 서비스 리포트 양식 1페이지 (합성 링 로트 3장). Tool/Chamber 는 빈 양식. 머리 표는 `docs/handoff.md` 2절 초동 보고 항목과 1:1. |
| `lot_report_page.png` | `lot_report` | 로트 트러블슈팅 리포트 1페이지: 로트 헤더(웨이퍼 수·평균 불량률·지배 패턴·저신뢰 장수·OCAP 레벨), 패턴 믹스 막대, 웨이퍼 썸네일 8장(슬롯 순), 방위각 로즈와 fixed_angle 판정 | `python wm811k_lot_report.py --demo` 가 만드는 PDF(demo_edge_loc_fixed)의 1페이지. |
| `*_en.png`, `pipeline_en.svg` | 위 이름 + `--lang en` | 같은 그림의 영문판(제목·캡션만 영문, 조치 문구는 한국어 단일 소스) | 저장소에는 커밋하지 않는다. 필요할 때 `python make_figures.py --lang en` 으로 만든다. |

샘플 PDF 는 `docs/samples/` 에 있다 (`--only sample_pdf`): `batch_wafer_report_sample.pdf` (합성 로트 3개 x 웨이퍼 2장, 서비스 리포트 전부 첨부, 8쪽), `lot_report_sample.pdf` (합성 로트 1개의 로트 트러블슈팅 리포트, 2쪽).

규칙: PNG 는 dpi 120~130, 파일당 500KB 이하(넘으면 256색 팔레트로 축소). `--lang en` 은 `_en` 접미사로 영문판을 만든다(이 README 는 한국어 한 벌만 있다). 한글은 동봉 폰트(`docs/fonts/NanumGothic-Regular.ttf`, `_fonts.py`)로 그린다. 생성 시각은 2026-01-01 00:00 UTC 로 고정해(`SOURCE_DATE_EPOCH`) 같은 코드면 바이트까지 같다 - `tests/test_make_figures.py` 가 두 번 생성해 비교한다.
