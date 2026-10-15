# results/ — 실측 수치의 재현 근거

> **현재 상태: 산출물 미첨부.** 이 폴더에 커밋된 것은 이 README 와 `environment.txt`(값이 전부 '(미기록)'인 틀)뿐이다.
> 아래 표의 파일은 소유자가 LSWMD.pkl 이 있는 PC 에서 실행해 채운다. 그 전까지 README 의 실측 수치는
> 저장소 안에서 검증되지 않는다(합성 데이터·CI 로는 재측정할 수 없다).

README 의 실측 수치(규칙 미교정 0.167 → 교정 0.558 → 구조 특징 RF 0.878 ± 0.008 → 위치 특징 RF **0.907 ± 0.008**)는
WM-811K 원본(LSWMD.pkl, 약 2GB)으로 낸 것이라 CI 에서는 재측정하지 않는다. 이 폴더는 그 숫자를 낸
**실행의 산출물 원본**을 두는 곳이다. 저장소의 `.gitignore` 는 `*.csv` 를 제외하지만 `results/*.csv`,
`results/*.txt`, `results/*.md` 만 예외로 커밋된다.

## 소유자가 실데이터 실행 후 넣어야 할 파일

| 파일 | 만드는 명령 | 내용 |
|---|---|---|
| `wm811k_validate_results.csv` | `python wm811k_validate.py` | 시드 5개(42, 0, 1, 2, 3)의 RF-17 / RF-20 test macro-F1. README 의 0.878 / 0.907 ± 0.008 의 원본 |
| `wm811k_improve_results.csv` | `python wm811k_improve.py` | 같은 5분할의 RF-20 / RF-28 / HGB-20 / HGB-28 (README '다음 실험' 절을 측정값으로 바꿀 때) |
| `calibrated_thresholds.txt` | `python wm811k_calibrate.py > results/calibrate.log` 의 '교정된 임계값' 블록을 그대로 복사 | 13개 임계값의 교정 전/후 (README 2번 항목 `center_r` 0.30 → 0.74 등의 원본) |
| `confusion_rf20.txt` | `wm811k_validate.py` 콘솔 출력의 'RF-20개 confusion matrix (5회 합산)' 블록 | README 의 EDGE_LOC↔LOC 오분류 장수의 원본 |
| `evaluate.log`, `calibrate.log`, `structural.log`, `validate.log`, `improve.log` | 각 스크립트를 `> results/<이름>.log` 로 리다이렉트 (Windows 도 동작, cp949 회귀는 CI 가 검사) | 콘솔 로그 전체. 각 단계의 train/test 숫자·AUC 표·클래스별 F1. 특징 테이블 저장 줄의 `라벨 N장 중 제외 n장` 이 실제 학습에 쓰인 장수의 근거다 |
| `environment.txt` | 아래 '환경 기록' | 숫자를 낸 PC 의 Python·패키지 버전 |

로그 파일은 `.txt` 로 저장해야 커밋된다(`.log` 는 제외 패턴에 걸리지 않지만 예외 목록에도 없다). 예: `> results/validate.txt`.

**넣지 않는 것**

- `test_predictions.csv` (`wm811k_validate.py --export-predictions`): 웨이퍼별 예측에 로트명이 들어간다.
  WM-811K 는 공개 데이터라 비밀은 아니지만 수천 행이라 용량 때문에 제외한다(`.gitignore` 가 `results/` 안에서도 막는다).
  SPC 데모는 `python wm811k_spc.py --demo` 로 재현된다.
- 특징 캐시 `wm811k_features*.csv`: 수 MB. 재추출로 복원된다(LSWMD.pkl 필요).
- `*.lot_history.csv`: SPC 의 로트 이력 산출물.

## 환경 기록

`results/environment.txt` 는 **수치를 낸 PC 에서** 다음으로 채운다 (현재 파일의 '참고' 블록은 이 저장소를 정비한
세션의 환경이지, 숫자를 낸 환경이 아니다):

```bash
python -c "import sys, platform, numpy, pandas, scipy, sklearn, matplotlib; print('python', sys.version.split()[0], platform.platform()); print('numpy', numpy.__version__); print('pandas', pandas.__version__); print('scipy', scipy.__version__); print('scikit-learn', sklearn.__version__); print('matplotlib', matplotlib.__version__)" > results/environment.txt
pip freeze >> results/environment.txt
```

## 수치 불변 규칙

특징값·분할·모델에 영향을 주는 코드(`wafer_map_visualizer.wafermap_to_df`, `wafer_pattern_classifier.classify_wafer_pattern` 의
규칙·임계값, `wm811k_structural.structural_features`, `wm811k_validate.largest_component_features / lot_split / make_rf`,
`wm811k_improve.robust_features / make_hgb`, `wm811k_calibrate` 의 규칙·격자, `CLASSES` 순서)를 바꾸는 변경은
이 폴더를 실데이터로 다시 만들어 README 수치와 **같은 커밋**에서 갱신할 때만 허용한다.
`tests/test_features_snapshot.py` 가 합성 고정 맵 3장의 특징값 28개를 소수 6자리로 고정해 두어, 리팩터가 값을 바꾸면 CI 가 알린다.

합성 데이터(`tests/`, `--demo`)로 나온 F1·알람은 로직 확인이지 성능이 아니다. 이 폴더에는 실데이터 산출물만 둔다.
