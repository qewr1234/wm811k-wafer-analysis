# docs/img - 문서용 그림 (전부 합성 데이터)

이 폴더의 그림은 **전부 합성 데이터**로 `python make_figures.py` 가 만든다. 그림 속 일치율·탐지 시점·판정은 로직 확인이지 성능이 아니다. 실측 수치는 README 의 WM-811K 결과뿐이다. 실제 장비·고객 데이터는 없고, Tool/Chamber 같은 식별자는 빈 양식이다.

| 파일 | 생성 (`python make_figures.py --only <name>`) | 내용 |
|---|---|---|
| `wafer_patterns_synthetic.png` | `patterns` | 합성 웨이퍼 맵 8종 2x4 격자 (`tests/synthetic_wm811k.make_wafermap`). 노치는 아래(가정 notch_deg=-90). |
| `spc_demo.png` | `spc` | `python wm811k_spc.py --demo` 의 관리도. 웨이퍼 3000부터 EDGE_RING 드리프트, 3750부터 저신뢰 증가, 4125부터 SCRATCH 계단을 심은 합성 시퀀스. |
| `spc_demo_chamber.png` | `spc_chamber` | 같은 데모를 `--group-col chamber --event-col event` 로 층화한 것. 심은 이상은 B 챔버에만 있고 이벤트(pm_wet_clean, focus_ring_replaced)가 세로 점선. |
| `pipeline.svg` | `pipeline` | 흐름도. 글자를 경로로 저장해 폰트 없는 환경에서도 한글이 보인다. |
| `service_report_page.png` | `service_report` | `batch_wafer_report.build_service_report_page` 의 서비스 리포트 양식 1페이지 (합성 링 로트 3장). Tool/Chamber 는 빈 양식. |
| `lot_report_page.png` | `lot_report` | `python wm811k_lot_report.py --demo` 가 만드는 PDF(demo_edge_loc_fixed)의 1페이지. |

샘플 PDF 는 `docs/samples/` 에 있다 (`--only sample_pdf`): `batch_wafer_report_sample.pdf` (합성 로트 3개 x 웨이퍼 2장, 서비스 리포트 전부 첨부), `lot_report_sample.pdf` (합성 로트 1개의 로트 트러블슈팅 리포트).

규칙: PNG 는 dpi 120~130, 파일당 500KB 이하(넘으면 256색 팔레트로 축소). `--lang en` 은 `_en` 접미사로 영문판을 만든다. 한글은 동봉 폰트(`docs/fonts/NanumGothic-Regular.ttf`, `_fonts.py`)로 그린다.
