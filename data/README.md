# data/ — 원본 데이터 입수·배치 안내

> 한 줄 요약: WM-811K 원본(LSWMD.pkl, 약 2 GB)은 여기(`data/`)에 두고 커밋하지 않는다. 이 폴더에는 추출본(`wm811k_labeled.pkl`, `wm811k_defects.pkl`)이 생기며 역시 커밋하지 않는다. 고객 데이터는 어디에도 두지 않는다.

## 입수 경로

| 항목 | 내용 |
|---|---|
| 데이터셋 | WM-811K (LSWMD) — 다이 단위 pass/fail 웨이퍼 맵(사실상 웨이퍼 테스트 빈 맵) |
| 원 출처 | MIR Lab, National Taiwan University (Wu, Jang & Chen 2015). 배포 페이지 URL은 소유자가 확인 후 기입: ______ |
| 2차 배포 | Kaggle 'WM-811K wafer map' — https://www.kaggle.com/qingyi/wm811k-wafer-map (로그인 필요, 2026-10 조사 요약 기준) |
| 파일 | `LSWMD.pkl` (pandas pickle), 약 2 GB |
| 행 수 | 811,457장 (원본 전체) |
| 라벨 있는 것 | 172,950장 (`none` 포함) |
| 결함 8종 | 25,519장 — Center 4,294 / Donut 555 / Edge-Loc 5,189 / Edge-Ring 9,680 / Loc 3,593 / Near-full 149 / Random 866 / Scratch 1,193 |
| `none`(정상) | 147,431장 |
| 열 | `waferMap`(2D 배열: 0 = 다이 없음, 1 = 정상, 2 = 불량), `dieSize`, `lotName`, `waferIndex`, `trianTestLabel`, `failureType` |
| 저장소 자체 계산 | 결함 8종 25,519장의 로트 수 8,047개, 맵 크기 329종 (원 논문 수치가 아니라 `wm811k_evaluate.py` 실행 결과) |
| 라이선스 | **소유자가 Kaggle 페이지의 License 필드를 직접 확인한 뒤 기입**: ______ (확인일: ______). 확인 전까지 실측 맵 썸네일은 저장소에 커밋하지 않는다 |
| SHA256 | 소유자가 내려받은 파일로 기입: ______ |

인용 조건: 이 데이터를 쓴 산출물은 원 논문을 인용한다.

> Wu, M.-J., Jang, J.-S. R., & Chen, J.-L. (2015). Wafer map failure pattern recognition and similarity ranking for large-scale data sets. *IEEE Transactions on Semiconductor Manufacturing*, 28(1), 1-12.

'웨이퍼 테스트 빈 맵'이라는 표현은 원 논문 인용이 아니라 다이 단위 pass/fail이라는 데이터 형식에서 온 서술이다. 일부 2차 자료의 '172,950장만 실제 맵이고 나머지는 시뮬레이션'이라는 주장은 검증되지 않았으므로 이 저장소는 라벨 있는 172,950장(그중 결함 8종 25,519장)만 쓴다.

## 배치와 경로

```
data/
  LSWMD.pkl              <- 내려받아 여기에 둔다 (커밋 안 함: .gitignore 의 data/*.pkl)
  wm811k_labeled.pkl     <- prepare_wm811k.py 가 만든다 (라벨 있는 172,950장, none 포함)
  wm811k_defects.pkl     <- prepare_wm811k.py 가 만든다 (결함 8종 25,519장) - 평가 스크립트의 입력
```

다른 위치에 두려면 환경변수 `WM811K_DIR`로 폴더를 지정한다(`wm811k_evaluate.py` 등이 `WM811K_DIR` 또는 스크립트 옆 `data/`에서 `wm811k_defects.pkl`을 찾는다).

```bash
# Linux / macOS
export WM811K_DIR=/path/to/wm811k
# Windows (PowerShell)
$env:WM811K_DIR = "D:\wm811k"

python prepare_wm811k.py                       # data/LSWMD.pkl -> data/wm811k_labeled.pkl, wm811k_defects.pkl
python prepare_wm811k.py path/to/LSWMD.pkl out_dir
python prepare_wm811k.py --sample 300 --seed 0 # 300 로트만 (소규모 재현·디버깅용; 수치는 README 와 다르다)
```

## 예상 소요 (추정)

| 단계 | 추정 시간 | 비고 |
|---|---|---|
| `prepare_wm811k.py` (2 GB pickle 읽기 → 추출) | 수 분 | 메모리 8 GB 이상 권장(추정). 한 번만 하면 된다 |
| 특징 추출 25,519장 (`wm811k_evaluate.py` 등) | 약 1~2분 | 한 장당 분류기 1.3~2.1 ms, 특징 함수 합계 2.5~4.0 ms (다른 환경에서 잰 값, 조사 요약 기준) |
| `wm811k_calibrate.py` | 수 분 | 좌표 하강 + 트리 비교 |
| `wm811k_validate.py` (RF 5시드 + 리프 선택) | 약 10분 (4코어 기준) | README 의 0.907 ± 0.008 |
| `wm811k_improve.py` | 약 5분 | RF/HGB 짝지어 비교 |

이 환경(이 저장소의 CI 포함)에는 LSWMD.pkl이 없어 실측 스크립트는 `tests/synthetic_wm811k.py`가 만든 합성 LSWMD 형식 데이터로만 끝까지 도는지 확인한다. 합성 결과는 로직 확인이지 성능이 아니다.

## 커밋하지 않는 것

- 원본 `LSWMD.pkl`, 추출본 `*.pkl` (`.gitignore`: `data/*.pkl`), 특징 캐시 `wm811k_features*.csv`, 웨이퍼별 예측 `test_predictions.csv`.
- **고객 데이터**: 고객 팹의 빈 맵·로트명·레시피·장비/챔버 ID는 이 저장소 어디에도 두지 않는다. 실제 팹 데이터로 돌릴 때는 저장소 밖 경로를 `WM811K_DIR`로 지정하고, 보고서에는 `wm811k_spc.py --anonymize`를 쓴다([`../docs/handoff.md`](../docs/handoff.md) 기밀 원칙).
- 실측 수치의 재현 근거(5시드 결과 CSV·로그·환경 버전)는 `results/`에 두며 그 폴더의 README를 따른다.
