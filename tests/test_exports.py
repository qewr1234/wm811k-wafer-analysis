# tests/test_exports.py
# 예측 CSV 내보내기·평가 출력·prepare --sample·규칙 동치·교정/구조 스크립트 스모크.
# 합성 WM-811K 형식 데이터(30로트)만 쓴다. 여기서 나오는 F1 은 성능이 아니라 로직 확인이다.
#
# 검사 항목
#   - wm811k_validate.main(--export-predictions, 시드 2개) 이 test_predictions.csv 를
#     지정한 열(lot, wafer_index, y_true, y_pred, confidence, fail_frac)로 만들고,
#     행이 시드 42 test 로트와 일치한다. wafer_index 없는 캐시면 NaN 열.
#   - wm811k_evaluate 출력 CSV 에 wafer_index·confidence(=score) 가 있고, --with-none 경로에서
#     y_true/y_pred 에 CLEAN 이 들어가며 지표는 결함 8종으로 계산된다.
#   - evaluate 와 calibrate 의 시드 42 로트 분할이 같다.
#   - prepare_wm811k.py --sample N 이 로트 단위로 N 로트만 남긴다.
#   - calibrate.apply_rules(Thresholds()) 가 classify_wafer_pattern 판정(y_rule_default)과 동치.
#   - calibrate.main / structural.main 이 tmp_path 에서 끝까지 돈다.
#   - 합성 none 로트(make_lswmd n_none_lots) -> prepare -> evaluate --with-none -> wm811k_spc 가
#     발생률(incidence) 관리도를 만드는 데까지 끝까지 돈다 (README ② 의 실측 경로 그대로).
#   - 실측 스크립트 6개가 argparse 라 --help 로 종료 코드 0.
#   - 루트 스크립트의 print / sys.exit 문자열 상수가 cp949 로 인코딩된다 (Windows 리다이렉트 회귀).
# 캐시·결과 파일은 전부 tmp_path 에 쓴다 (HERE/CACHE monkeypatch).

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import prepare_wm811k as prep  # noqa: E402
import wm811k_calibrate as cal  # noqa: E402
import wm811k_evaluate as ev  # noqa: E402
import wm811k_spc as spc  # noqa: E402
import wm811k_structural as st  # noqa: E402
import wm811k_validate as vd  # noqa: E402
from synthetic_wm811k import NONE_LABEL, make_lswmd  # noqa: E402

N_LOTS = 30
PIPELINE_SCRIPTS = ["prepare_wm811k.py", "wm811k_evaluate.py", "wm811k_calibrate.py",
                    "wm811k_structural.py", "wm811k_validate.py", "wm811k_improve.py"]


def _labels(df: pd.DataFrame) -> pd.Series:
    return df["failureType"].apply(lambda a: a.reshape(-1)[0] if a.size else None)


@pytest.fixture(scope="module")
def data(tmp_path_factory):
    """합성 LSWMD(결함 30로트 + none 3로트) -> prepare -> labeled/defects pkl. 모듈 안에서 한 번만."""
    d = tmp_path_factory.mktemp("c3data")
    src = d / "LSWMD.pkl"
    make_lswmd(n_lots=N_LOTS, n_unlabeled=3, seed=2, n_none_lots=3).to_pickle(src)
    out = prep.prepare(src, d)
    assert out["n_defects"] > 0 and out["n_labeled"] > out["n_defects"]
    return {"src": src, "dir": d, "labeled": out["labeled"], "defects": out["defects"]}


@pytest.fixture(scope="module")
def validate_run(data, tmp_path_factory):
    """validate.main(seeds 2개, export) 을 한 번 돌리고 산출물 폴더를 돌려준다."""
    d = tmp_path_factory.mktemp("c3validate")
    mp = pytest.MonkeyPatch()
    mp.setattr(vd, "CACHE2", d / "ext2.csv")
    mp.setattr(vd, "HERE", d)
    mp.setattr(vd, "LEAF_GRID", [2])          # Q3 규제 격자는 여기서 보지 않는다 (RF 400그루 x 25회 절약)
    try:
        vd.main(data["defects"], seeds=[42, 0], export=True)
    finally:
        mp.undo()
    return d


# ──────────────────────────────────────────
# 1. validate --export-predictions
# ──────────────────────────────────────────
def test_validate_export_predictions_columns(validate_run):
    p = validate_run / "test_predictions.csv"
    assert p.exists()
    out = pd.read_csv(p)
    assert list(out.columns) == vd.PRED_COLS
    assert len(out) > 0
    assert out["wafer_index"].notna().all()                     # 합성 데이터에는 waferIndex 가 있다
    assert set(out["y_pred"]) <= set(vd.CLASSES) and set(out["y_true"]) <= set(vd.CLASSES)
    assert ((out["confidence"] >= 0) & (out["confidence"] <= 1)).all()
    assert ((out["fail_frac"] >= 0) & (out["fail_frac"] <= 1)).all()

    # 행 = 시드 42 로트 분할의 test 쪽, 캐시(특징 테이블) 기준
    F = pd.read_csv(validate_run / "ext2.csv")
    assert "wafer_index" in F.columns
    _, te = vd.lot_split(F, vd.EXPORT_SEED)
    assert len(out) == len(te)
    assert set(out["lot"].astype(str)) == set(F["lot"].astype(str).to_numpy()[te])
    assert not (set(out["lot"].astype(str)) & set(F["lot"].astype(str).to_numpy()[np.setdiff1d(np.arange(len(F)), te)]))

    res = pd.read_csv(validate_run / "wm811k_validate_results.csv")
    assert list(res["seed"]) == [42, 0] and {"rf17", "rf20"} <= set(res.columns)


def test_validate_export_without_wafer_index(validate_run, tmp_path):
    """구버전 캐시(wafer_index 열 없음)여도 NaN 열로 내보낸다."""
    F = pd.read_csv(validate_run / "ext2.csv").drop(columns=["wafer_index"])
    out = vd.export_predictions(F, tmp_path / "p.csv", seed=0)
    assert list(out.columns) == vd.PRED_COLS
    assert out["wafer_index"].isna().all()
    assert (tmp_path / "p.csv").exists()


# ──────────────────────────────────────────
# 2. evaluate 출력
# ──────────────────────────────────────────
def test_evaluate_csv_has_wafer_index_and_confidence(data, tmp_path, monkeypatch):
    monkeypatch.setattr(ev, "HERE", tmp_path)
    ev.main(data["defects"])
    res = pd.read_csv(tmp_path / "wm811k_predictions.csv")
    for c in ("lot", "wafer_index", "y_true", "y_pred", "score", "confidence", "fail_frac", "skipped"):
        assert c in res.columns, c
    ok = res[~res["skipped"].astype(bool)]
    assert len(ok) > 0 and ok["wafer_index"].notna().all()
    assert np.allclose(ok["confidence"], ok["score"])           # 휴리스틱 점수의 복제
    assert set(ok["y_pred"]) <= set(ev.CLASSES) | {"CLEAN"}
    assert "CLEAN" not in set(ok["y_true"])                       # defects.pkl 에는 none 이 없다


def test_evaluate_with_none_keeps_clean(data, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ev, "HERE", tmp_path)
    df = ev.load_data(data["labeled"], include_none=True)
    assert "CLEAN" in set(df["y_true"])
    res = ev.classify_all(df)
    ok = res[~res["skipped"]]
    assert "CLEAN" in set(ok["y_true"]) and "CLEAN" in set(ok["y_pred"])
    m = ev.report(res, "with-none")
    assert 0.0 <= m["macro_f1"] <= 1.0 and 0.0 <= m["balanced_acc"] <= 1.0
    # balanced accuracy 는 결함 8종 recall 평균 (CLEAN 제외) 과 같아야 한다
    bal = np.mean([(ok.loc[ok["y_true"] == c, "y_pred"] == c).mean()
                   for c in ev.CLASSES if (ok["y_true"] == c).any()])
    assert m["balanced_acc"] == pytest.approx(bal)
    out = capsys.readouterr().out
    assert "→CLEAN" in out                                        # 표에는 CLEAN 열이 보인다


def test_evaluate_tables(data):
    df = ev.load_data(data["defects"])
    lt = ev.lot_size_table(df)
    assert list(lt.index) == ["1장", "2~4장", "5장 이상"]
    assert int(lt["로트 수"].sum()) == df["lot"].nunique()
    assert int(lt["웨이퍼 수"].sum()) == len(df)
    wt = ev.wafer_index_table(df, ev.CLASSES)
    assert wt is not None and int(wt["합계"].sum()) == len(df)
    assert ev.wafer_index_table(df.assign(wafer_index=np.nan)) is None


def test_synthetic_none_lots_are_off_by_default():
    """n_none_lots 기본 0: 기존 호출의 행 수·라벨·맵이 그대로다. 켜면 'none' 로트가 뒤에 붙는다."""
    base = make_lswmd(n_lots=5, n_unlabeled=2, seed=7)
    with_none = make_lswmd(n_lots=5, n_unlabeled=2, seed=7, n_none_lots=2)
    assert NONE_LABEL not in set(_labels(base).dropna())
    head = with_none.iloc[:len(base)]
    assert _labels(head).equals(_labels(base))
    assert all(np.array_equal(a, b) for a, b in zip(head["waferMap"], base["waferMap"]))
    tail = with_none.iloc[len(base):]
    assert (_labels(tail) == NONE_LABEL).all() and tail["lotName"].nunique() == 2
    frac = tail["waferMap"].apply(lambda m: (m == 2).sum() / (m > 0).sum())
    assert (frac <= 0.011).all()                                  # 산발 불량 0~1%: 규칙 분류기의 CLEAN 영역


def test_with_none_feeds_spc_incidence_charts(tmp_path, monkeypatch):
    """README ② 의 실측 경로를 합성으로 끝까지: none 로트 -> prepare -> evaluate --with-none ->
    wm811k_spc 가 share 가 아니라 incidence(분모 = 전체 웨이퍼) 관리도를 만든다."""
    src = tmp_path / "LSWMD.pkl"
    raw = make_lswmd(n_lots=30, n_unlabeled=0, seed=5, n_none_lots=15)
    n_none = int((_labels(raw) == NONE_LABEL).sum())
    assert n_none > 0
    raw.to_pickle(src)
    out = prep.prepare(src, tmp_path)
    assert out["n_labeled"] - out["n_defects"] == n_none        # none 은 labeled 에만 남는다

    assert ev._cli(["--with-none"]).with_none and not ev._cli([]).with_none
    monkeypatch.setattr(ev, "HERE", tmp_path)
    ev.main(out["labeled"], include_none=True)                 # == python wm811k_evaluate.py <labeled> --with-none
    pred_csv = tmp_path / "wm811k_predictions.csv"
    res = pd.read_csv(pred_csv)
    ok = res[~res["skipped"].astype(bool)]
    assert "CLEAN" in set(ok["y_true"]) and "CLEAN" in set(ok["y_pred"])
    # 불량 0~1% 의 none 웨이퍼는 미교정 규칙(clean_frac 0.02)으로도 CLEAN 이어야 분모가 '전체 웨이퍼'가 된다
    assert (ok.loc[ok["y_true"] == "CLEAN", "y_pred"] == "CLEAN").mean() > 0.9

    df = spc.load_predictions(pred_csv, verbose=False)
    assert spc.chart_mode(df) == "incidence"
    n_base = len(df) // 2
    thr, _ = spc.resolve_conf_threshold(df, n_base, None, 0.10)
    charts, sizes, dropped = spc.build_all(df, spc.CLASSES, 25, False, n_base, thr)
    names = {ch.name for ch in charts}
    assert names & set(spc.CLASSES), dropped                     # 패턴 발생률 관리도가 적어도 하나
    assert "LOW_CONFIDENCE" in names                             # score -> confidence 별칭 경로
    assert all(ch.n_base >= spc.MIN_BASE_GROUPS for ch in charts)
    alarms = spc.alarm_table(charts, "incidence")
    assert {"chart", "rule", "phase", "direction"} <= set(alarms.columns)


@pytest.mark.parametrize("script", PIPELINE_SCRIPTS)
def test_pipeline_scripts_answer_help(script):
    """argparse: --help 가 pkl 을 열지 않고 종료 코드 0 으로 사용법을 낸다."""
    r = subprocess.run([sys.executable, str(ROOT / script), "--help"], capture_output=True,
                       text=True, encoding="utf-8", env={**os.environ, "MPLBACKEND": "Agg"})
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("usage:") and "pkl" in r.stdout


def _console_literals(path: Path):
    """print(...) / sys.exit(...) 호출 안의 문자열 상수 (f-string 조각 포함)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        is_print = isinstance(f, ast.Name) and f.id == "print"
        is_exit = isinstance(f, ast.Attribute) and f.attr == "exit" and getattr(f.value, "id", "") == "sys"
        if not (is_print or is_exit):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                yield sub.lineno, sub.value


@pytest.mark.parametrize("script", sorted(p.name for p in ROOT.glob("*.py")) + ["tests/synthetic_wm811k.py"])
def test_console_strings_are_cp949_safe(script):
    """콘솔로 나가는 문자열에 cp949 밖 문자('—' U+2014, '−' U+2212 등)가 없어야 한다.
    각 스크립트가 stdout 을 UTF-8 로 reconfigure 하지만, PYTHONIOENCODING=cp949 나 일부 IDE 출력창에서는
    적용되지 않아 UnicodeEncodeError 로 죽는다. 그림·PDF·argparse help 문자열은 대상이 아니다."""
    bad = []
    for lineno, s in _console_literals(ROOT / script):
        try:
            s.encode("cp949")
        except UnicodeEncodeError as e:
            bad.append((lineno, f"U+{ord(s[e.start]):04X}", s[max(0, e.start - 10):e.end + 10]))
    assert not bad, bad


def test_evaluate_and_calibrate_split_agree(data, tmp_path, monkeypatch):
    """두 스크립트의 시드 42 로트 분할이 같은 test 로트를 고른다."""
    monkeypatch.setattr(ev, "HERE", tmp_path)
    res = ev.classify_all(ev.load_data(data["defects"]))
    res["split"] = ev.lot_group_split(res)
    ev_test = set(res.loc[(res["split"] == "test") & ~res["skipped"], "lot"].astype(str))

    monkeypatch.setattr(cal, "FEATURE_CACHE", tmp_path / "feat.csv")
    F = cal.build_features(data["defects"])
    rng = np.random.default_rng(cal.SPLIT_SEED)
    lots = F["lot"].astype(str).unique()
    cal_test = set(rng.choice(lots, size=int(len(lots) * cal.TEST_FRAC), replace=False))
    assert ev_test == cal_test and len(cal_test) > 0


# ──────────────────────────────────────────
# 3. prepare --sample
# ──────────────────────────────────────────
def test_prepare_sample_keeps_whole_lots(data, tmp_path):
    r = subprocess.run([sys.executable, str(ROOT / "prepare_wm811k.py"), str(data["src"]), str(tmp_path),
                        "--sample", "10", "--seed", "0"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    full = pd.read_pickle(data["labeled"])
    sub = pd.read_pickle(tmp_path / "wm811k_labeled.pkl")
    assert sub["lotName"].nunique() == 10
    assert set(sub["lotName"]) <= set(full["lotName"])
    # 로트 단위: 남은 로트는 통째로 남는다
    for lot, g in sub.groupby("lotName"):
        assert len(g) == int((full["lotName"] == lot).sum())
    assert (tmp_path / "wm811k_defects.pkl").exists()
    assert "--sample 10" in r.stdout


# ──────────────────────────────────────────
# 4. 규칙 동치 + calibrate / structural 스모크
# ──────────────────────────────────────────
def test_apply_rules_matches_classifier(data, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "FEATURE_CACHE", tmp_path / "feat.csv")
    F = cal.build_features(data["defects"])
    pred = cal.apply_rules(F, cal.Thresholds())
    mism = F.loc[pred != F["y_rule_default"].to_numpy(), ["y_rule_default"]].assign(vec=pred[pred != F["y_rule_default"].to_numpy()])
    assert mism.empty, f"벡터 규칙과 분류기 판정 불일치 {len(mism)}건:\n{mism.head()}"
    assert set(pred) <= set(cal.CLASSES) | {"CLEAN"}


def test_calibrate_main_smoke(data, tmp_path, monkeypatch):
    monkeypatch.setattr(cal, "HERE", tmp_path)
    monkeypatch.setattr(cal, "FEATURE_CACHE", tmp_path / "feat.csv")
    cal.main(data["defects"])
    out = pd.read_csv(tmp_path / "wm811k_calibrated.csv")
    assert {"split", "y_rule_tuned", "y_tree", "y_rule_default"} <= set(out.columns)
    assert set(out["split"]) == {"train", "test"}


def test_structural_main_smoke(data, validate_run, tmp_path, monkeypatch):
    # validate 캐시는 structural 이 쓰는 열(전역 6 + 구조 11)을 모두 담고 있어 재추출을 피한다
    monkeypatch.setattr(st, "HERE", tmp_path)
    monkeypatch.setattr(st, "CACHE", validate_run / "ext2.csv")
    st.main(data["defects"])
    out = pd.read_csv(tmp_path / "wm811k_structural_results.csv")
    assert "split" in out.columns and any(c.startswith("pred_") for c in out.columns)
