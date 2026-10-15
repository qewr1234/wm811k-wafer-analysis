# 로트 이력 CSV 스키마 — `wm811k_commonality.py` 입력

수율 이상이 나면 가장 먼저 하는 일이 "패턴이 나온 로트들이 어느 장비를 같이 지났는가"를 찾는 장비 공통성 분석(tool commonality analysis)이다. WM-811K에는 장비 이력이 없으므로 이 저장소는 입력 형식만 정하고 합성 이력으로 로직을 검증한다. 실제 팹에서는 MES의 로트 라우팅(track-in/track-out) 추출이 이 형식의 입력이 된다.

**고객 데이터는 커밋하지 않는다.** 이 저장소에는 공개 데이터(WM-811K)와 합성 데이터만 들어간다. 실제 이력 파일은 `*.lot_history.csv`로 이름 붙이면 `.gitignore`가 제외한다. 아래 예시의 로트·장비·챔버 ID는 전부 가상이다.

## 열

| 열 | 필수 | 형식 | 뜻 |
|---|---|---|---|
| `lot` | 필수 | 문자열 | 로트 ID. 예측 CSV(`wm811k_evaluate.py`, `wm811k_validate.py --export-predictions`)의 `lot`과 **문자 그대로** 같아야 조인된다(공백·대소문자 포함) |
| `step` | 필수 | 문자열 | 공정 단계 ID. 예 `ETCH_M1`, `CVD_ILD1`. 같은 단계의 장비끼리만 비교한다 |
| `tool` | 필수 | 문자열 | 장비 ID. 예 `ETCH-02` |
| `chamber` | 선택 | 문자열 | 챔버/스테이션 ID. 예 `A`. 없으면 장비 단위로만 본다(`--by step tool`과 같다) |
| `start_time` | 선택 | ISO 8601 날짜·시각 | 그 단계 처리 시작 시각. 예 `2026-01-07T06:00:00`. 시간축 분석(`wm811k_spc.py --time-col`)과 PM 경과일 계산에 쓴다 |
| `pm_date` | 선택 | ISO 8601 날짜 | 그 로트 처리 직전에 그 장비·챔버가 받은 마지막 PM 날짜. `start_time`과 함께 있으면 상위 장비의 "PM 후 경과일"을 양성/음성 로트로 나눠 요약한다 |
| `part_change` | 선택 | 문자열 | 직전 부품 교체 내용(예 `focus_ring`). 현재는 보존만 하고 계산에 쓰지 않는다. `wm811k_spc.py --event-col`의 이벤트 열로 재사용할 수 있다 |

행 하나 = 로트 하나가 단계 하나를 한 번 지난 기록. 같은 로트가 같은 단계를 두 번 지나면(재작업) 두 행이 되고, 스크립트는 경고만 하고 둘 다 센다. 웨이퍼 단위 행은 필요 없다(공통성 분석의 단위는 로트다).

## 예시 (가상 ID)

```csv
lot,step,tool,chamber,start_time,pm_date,part_change
demoLot0001,ETCH_M1,ETCH-02,B,2026-01-06T00:00:00,2025-12-20,focus_ring
demoLot0001,CVD_ILD1,CVD-01,A,2026-01-06T06:00:00,2025-11-28,
demoLot0001,TRACK_M1,TRK-03,A,2026-01-06T12:00:00,2026-01-02,
demoLot0001,CLEAN_PRE,CLN-01,B,2026-01-06T18:00:00,2025-12-30,
demoLot0002,ETCH_M1,ETCH-01,A,2026-01-07T00:00:00,2025-12-15,
demoLot0002,CVD_ILD1,CVD-02,B,2026-01-07T06:00:00,2025-12-01,showerhead
```

`python wm811k_commonality.py --demo`가 이 형식의 합성 이력(200로트)을 만들어 `commonality_demo/`에 결과를 쓴다.

## 예측 CSV와의 결합

- 예측 CSV에는 `lot`, `y_pred`가 필요하다(`wafer_index`는 공통성 분석에 쓰지 않는다).
- 로트 양성 정의: 로트 안 `y_pred == 패턴` 비율이 `--min-frac`(기본 0.3) 이상이고 로트 장수가 `--min-n`(기본 1) 이상. 결함 부분집합(WM-811K 라벨 8종)은 로트당 평균 3.2장이라 기본 `min_n=1`로 두었다. 1~2장짜리 로트의 "양성"은 웨이퍼 한 장의 판정이므로 로트 수가 충분할 때만 믿고, 로트당 25장인 실제 팹 데이터에서는 `--min-n 5` 이상을 권한다.
- 예측에는 있는데 이력에 없는 로트는 경고 후 제외된다. 이력에만 있는 로트(예측 없음)도 세지 않는다.

## 출력 읽는 법 (`commonality_<PATTERN>.csv`)

| 열 | 뜻 |
|---|---|
| `n_lots`, `n_bad`, `rate` | 그 단위(단계·장비·챔버)를 지난 로트 수, 그중 양성, 비율 |
| `n_other`, `bad_other`, `rate_other` | 같은 단계의 나머지 로트 |
| `rate_ratio`, `ci_lo`, `ci_hi` | `rate / rate_other`와 95% 구간(로그 정규 근사, 0 칸은 0.5 보정) |
| `p_fisher` | Fisher 정확검정 단측(greater): "이 단위가 같은 단계의 나머지보다 나쁜가" |
| `q_bh` | 단계 안 Benjamini–Hochberg 보정 |
| `overlap_with_top` | 이 단위의 로트 중 상위 1 단위의 장비(모든 챔버)도 지난 비율 |
| `evidence` | `n_lots < 5`면 `insufficient`(근거 부족). 표 뒤쪽으로 보낸다 |
| `note` | `top candidate`, 라우팅 혼입 경고(`routing overlap 0.94 with top ... - cannot separate`), `insufficient` |

**혼입 경고.** 라우팅이 묶여 있으면(ETCH-02를 지난 로트가 거의 항상 CVD-02도 지나면) 두 장비가 같이 뜬다. 다른 단계의 단위가 `overlap_with_top ≥ 0.8`이고 `q < 0.05`면 "구분 불가"로 표시한다. 그때는 한쪽만 지난 로트로 다시 나누거나, 두 장비의 PM·부품 이력을 각각 맞대야 한다.

**한계.** 공통성은 상관이지 인과가 아니다. 지목된 장비의 장비 측 증거(알람 로그, 부품 누적 카운터, 레시피·PM 이력)와 첫 양성 로트의 시점(`wm811k_spc.py --event-col`)을 맞대야 끝난다. 로트 수가 적으면 Fisher는 보수적이다. 합성 데모의 결과는 로직 확인이지 탐지 성능이 아니다.
