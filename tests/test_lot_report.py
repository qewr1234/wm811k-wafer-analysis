# tests/test_lot_report.py
# wm811k_lot_report (로트 단위 트러블슈팅 리포트) 의 코딩 오류를 합성 데이터로 잡는다.
# 판정이 기대와 맞는 것은 로직 확인이지 성능이 아니다 - 생성기와 판정 규칙이 같은 가정을 공유한다.
#
# 검사 항목
#   - --demo 가 PDF 3개 + JSON 3개를 만들고 기대 판정과 일치한다 (subprocess, --output 에만 쓴다)
#   - analyze_lot: n < 3 로트는 insufficient, 지배 1~2장은 event, 과반은 process, 3장 이상 과반 미만은 mixed
#   - NEAR_FULL 1장 로트의 test_exclusion_flags 에 '재테스트', 2장 이상이면 OCAP L3
#   - EDGE_LOC 고정각 로트의 suspects 첫 항목이 챔버 비대칭/EBR 계열, scattered 면 로봇 센터링 계열
#   - SCRATCH 직선 재현 로트는 반송계 먼저, 호 다수 로트는 CMP(타사) 인계 먼저
#   - grid_repeat_score: 심은 격자 반복은 suspect, 링/센터/랜덤 맵은 아님
#   - findings_to_json 이 json.dumps 가능 (NaN 없음), 익명화 시 원래 로트명·장비·챔버 ID 가 JSON·PDF 에 없다
#   - PDF 생성 중 'missing from font' 경고 0건, 페이지 수가 메타데이터와 같다, --lang en 전환
#   - LABELS ko/en 키 집합 동일, 모든 문구 cp949 인코딩 가능
#   - 8패턴 + CLEAN 지배 로트 전부가 analyze_lot + render_lot_pdf + findings_to_json 을 예외 없이 지난다
#     (DONUT 의 ':' 없는 점검 문구가 IndexError 를 내던 회귀), rank_suspects 전수 조합에 예외 없음
#   - 점검 문구의 모듈 라벨에 여는 괄호가 없다 (CENTER 의 괄호 안 ':' 가 라벨 경계로 잘리던 회귀)
#   - 예측 CSV 쪽 wafer_index 결측 -> 행 순서 결합, 이력과 로트가 안 겹치면 공통성만 생략하고 리포트는 생성
#   - 저신뢰 임계값: 명시값 > 예측 전체 분위수(q0.10) > 고정 0.7, 근거가 헤더·JSON 에 남는다

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import warnings
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import wm811k_lot_report as lr  # noqa: E402
import wm811k_scratch_shape as ss  # noqa: E402
from synthetic_wm811k import LABELS as SYN_LABELS, df_to_wafermap, make_wafermap  # noqa: E402
from wafer_map_visualizer import generate_sample_wafer_data  # noqa: E402
from wafer_pattern_classifier import ACTION_DETAIL  # noqa: E402

SYN_TO_CLASS = {"ring": "EDGE_RING", "center": "CENTER", "scratch": "SCRATCH", "random": "RANDOM", "donut": "DONUT",
                "edge_loc": "EDGE_LOC", "loc": "LOC", "near_full": "NEAR_FULL"}


def _count_pages(pdf_bytes: bytes) -> int:
    try:
        import pypdfium2 as pdfium  # type: ignore
        return len(pdfium.PdfDocument(pdf_bytes))
    except ImportError:
        return len(re.findall(rb"/Type\s*/Page(?![s\w])", pdf_bytes))


def _pdf_text(path: Path) -> str | None:
    try:
        import pypdfium2 as pdfium  # type: ignore
    except ImportError:
        return None
    doc = pdfium.PdfDocument(str(path))
    return "\n".join(doc[i].get_textpage().get_text_range() for i in range(len(doc)))


def _lot(rows: list[tuple[str, int, np.ndarray, str]], conf: float | None = 0.9) -> tuple[pd.DataFrame, pd.DataFrame]:
    """[(lot, wafer_index, waferMap, y_pred)] -> (records, preds)."""
    rec = pd.DataFrame([{"waferMap": m, "lot": L, "wafer_index": w} for L, w, m, _ in rows])
    pr = pd.DataFrame([{"lot": L, "wafer_index": w, "y_pred": y} for L, w, _, y in rows])
    if conf is not None:
        pr["confidence"] = conf
    return rec, pr


@pytest.fixture
def rng():
    """테스트마다 새 생성기 - 실행 순서와 무관하게 결정적이다."""
    return np.random.default_rng(0)


@pytest.fixture(scope="module")
def demo():
    """합성 로트 3개 + 배경 로트 + 이력. 여러 테스트가 공유한다."""
    records, preds, hist = lr.demo_records(seed=0, n_background_lots=30)
    return {"records": records, "preds": preds, "hist": hist}


# ──────────────────────────────────────────
# 판정 규칙
# ──────────────────────────────────────────
def test_repeat_verdict_rules():
    assert lr.repeat_verdict(2, 2) == "insufficient"
    assert lr.repeat_verdict(3, 2) == "process"            # 2/3 >= 0.5
    assert lr.repeat_verdict(5, 2) == "event"
    assert lr.repeat_verdict(10, 4) == "mixed"
    assert lr.repeat_verdict(8, 8) == "process"


def test_insufficient_lot_and_event_lot(rng):
    rows = [("small", 1, make_wafermap("ring", 1, rng), "EDGE_RING"), ("small", 2, make_wafermap("ring", 2, rng), "EDGE_RING")]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "small")
    assert f.n == 2 and f.repeat_verdict == "insufficient" and f.ocap_level == "L1"
    assert f.dominant == "EDGE_RING" and f.mix == {"EDGE_RING": 2}

    rows = [("ev", i, make_wafermap("random", 10 + i, rng), "RANDOM") for i in range(1, 6)]
    rows += [("ev", 6, make_wafermap("center", 16, rng), "CENTER")]
    rows += [("ev", 7, make_wafermap("random", 17, rng), "CLEAN")]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "ev")
    assert f.dominant == "RANDOM" and f.dominant_count == 5 and f.repeat_verdict == "process"
    assert f.mix["CLEAN"] == 1 and f.n == 7 and f.ocap_level == "L1"       # RANDOM 은 monitor -> L1
    # CLEAN 은 지배 패턴이 될 수 없다 (결함 패턴이 하나라도 있으면)
    rows = [("c", 1, make_wafermap("random", 1, rng), "CLEAN")] * 4 + [("c", 5, make_wafermap("center", 5, rng), "CENTER")]
    rec, pr = _lot([(L, i + 1, m, y) for i, (L, _, m, y) in enumerate(rows)])
    f = lr.analyze_lot(rec, pr, "c")
    assert f.dominant == "CENTER" and f.repeat_verdict == "event" and f.ocap_level == "L1"


def test_near_full_single_flags_retest_and_two_is_L3(rng):
    rows = [("nf", i, make_wafermap("random", 20 + i, rng), "RANDOM") for i in range(1, 5)]
    rows += [("nf", 5, make_wafermap("near_full", 25, rng), "NEAR_FULL")]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "nf")
    assert any("재테스트" in s for s in f.test_exclusion_flags)
    assert f.ocap_level == "L1" and "재테스트" in f.ocap_reason["ko"] and "retest" in f.ocap_reason["en"]
    rows += [("nf", 6, make_wafermap("near_full", 26, rng), "NEAR_FULL")]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "nf")
    assert f.ocap_level == "L3" and any("NEAR_FULL 2장" in s for s in f.test_exclusion_flags)
    # 지배가 NEAR_FULL 이면 rule_out_first(재테스트)가 0순위
    rows = [("nf2", i, make_wafermap("near_full", 30 + i, rng), "NEAR_FULL") for i in range(1, 4)]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "nf2")
    assert f.suspects[0]["source"] == "rule_out_first" and "재테스트" in f.suspects[0]["check"]
    assert f.ocap_level == "L3"


def test_edge_loc_fixed_angle_suspects_chamber_first(demo):
    f = lr.analyze_lot(demo["records"], demo["preds"], lr.DEMO_LOTS[0], history=demo["hist"], synthetic=True)
    assert f.dominant == "EDGE_LOC" and f.repeat_verdict == "process" and f.ocap_level == "L2"
    assert f.azimuth["verdict"] == "fixed_angle" and f.azimuth["n"] == 8 and abs(f.azimuth["mean_deg"] - 135) < 10
    top = f.suspects[0]
    assert "챔버" in top["module"] or "EBR" in top["check"] or "챔버 비대칭" in top["check"]
    assert "fixed_angle" in top["basis"] and top["source"].startswith("first_checks[")
    # 모듈 라벨은 check 본문에서 떼어냈다 (중복 표시 방지)
    assert not top["check"].startswith(top["module"])
    assert len(f.wafers) == 8 and all(w["theta_deg"] is not None for w in f.wafers)
    assert f.evidence["customer"] and f.evidence["tool"] and f.handoff
    assert "EDGE_LOC 8장" in f.d2_draft and "[합성 데이터]" in f.d2_draft
    assert len(f.commonality_top) <= 3 and all({"step", "tool", "q_bh", "this_lot_passed"} <= set(c) for c in f.commonality_top)
    assert f.slot["slots"] == list(range(1, 9)) and f.slot["end_concentrated"] is False


def test_edge_loc_scattered_suspects_handling_first(rng):
    import wm811k_azimuth as az
    rows = [("sc", w + 1, az._synthetic_edge_loc_map(float(a), 50 + w, rng), "EDGE_LOC")
            for w, a in enumerate((-150, -90, -30, 30, 90, 150))]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "sc")
    assert f.azimuth["verdict"] == "scattered"
    assert "로봇" in f.suspects[0]["check"] or "핸들링" in f.suspects[0]["basis"]
    assert "scattered" in f.suspects[0]["basis"]


def test_scratch_line_vs_arc_suspects(demo, rng):
    f = lr.analyze_lot(demo["records"], demo["preds"], lr.DEMO_LOTS[1], synthetic=True)
    assert f.scratch["verdict"] == "reproducible_line" and f.scratch["n_line"] == 5
    assert "반송" in f.suspects[0]["module"] or "반송" in f.suspects[0]["check"]
    assert all(w["shape"] == "line" for w in f.wafers)
    # 호가 다수인 로트 -> CMP(타사) 인계가 먼저
    rows = []
    for w in range(4):
        ang = rng.uniform(0, 2 * np.pi)
        rows.append(("arc", w + 1, ss.synthetic_scratch_map("arc", 700 + w, arc_center=(float(180 * np.cos(ang)), float(180 * np.sin(ang)))), "SCRATCH"))
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "arc")
    assert f.scratch["n_arc"] >= 3 and f.scratch["verdict"] == "random"
    assert "CMP" in f.suspects[0]["check"] and "타사" in f.suspects[0]["basis"]


def test_end_slot_concentration_bumps_furnace_check(rng):
    rows = []
    for s in range(1, 26):
        hit = s in (1, 2, 3, 23, 24, 25, 8, 12, 16)              # 끝 슬롯 6/6, 가운데 3/19
        rows.append(("fur", s, make_wafermap("ring" if hit else "clean", 400 + s, rng), "EDGE_RING" if hit else "CLEAN"))
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "fur")
    assert f.dominant == "EDGE_RING" and f.dominant_count == 9 and f.repeat_verdict == "mixed"
    assert f.slot["end_concentrated"] and f.slot["n_end_slot_hits"] == 6 and f.slot["rate_end"] > 2 * f.slot["rate_mid"]
    assert f.slot["longest_run"] == 3
    assert "퍼니스" in f.suspects[0]["check"] and "끝 슬롯" in f.suspects[0]["basis"]
    # 끝에 몰리지 않으면 기본 순서
    rows = [("flat", s, make_wafermap("ring", 430 + s, rng), "EDGE_RING") for s in range(1, 26)]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "flat")
    assert not f.slot["end_concentrated"] and f.suspects[0]["source"] == "first_checks[0]"


# ──────────────────────────────────────────
# 모든 패턴의 지배 로트 (회귀: DONUT 의 ':' 없는 점검 문구가 IndexError 를 냈다)
# ──────────────────────────────────────────
@pytest.mark.parametrize("mode", list(SYN_LABELS) + ["clean"])
def test_every_dominant_pattern_reports_without_error(mode, rng, tmp_path):
    label = SYN_TO_CLASS.get(mode, "CLEAN")
    rows = [(f"all_{mode}", i, make_wafermap("random" if mode == "clean" else mode, 1000 + i, rng), label) for i in (1, 2, 3)]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, f"all_{mode}", synthetic=True)
    assert f.dominant == label and f.n == 3
    expected_checks = len(ACTION_DETAIL[label]["first_checks"]) + (1 if label in ("NEAR_FULL",) else 0)
    assert len(f.suspects) == expected_checks
    for s in f.suspects:
        assert s["check"] and "(" not in s["module"] and not s["check"].startswith(":")
        if s["module"] != "common":
            assert not s["check"].startswith(s["module"])
    d = lr.findings_to_json(f)
    json.dumps(d, ensure_ascii=False, allow_nan=False)
    out = tmp_path / f"{mode}.pdf"
    lr.render_lot_pdf(f, rec, out, lang="ko")
    assert 1 <= _count_pages(out.read_bytes()) <= 3
    text = _pdf_text(out)
    if text is not None:
        assert f"all_{mode}" in text and "OCAP" in text


def test_rank_suspects_all_verdict_combinations_no_exception():
    """ACTION_DETAIL 전 패턴 x repeat x 방위각 x 모양 x 격자 x 슬롯 전수 조합 - 예외 없고 본문이 비지 않는다."""
    n = 0
    for pat in ACTION_DETAIL:
        for rep in ("process", "event", "mixed", "insufficient"):
            for az in (None, "fixed_angle", "scattered", "insufficient"):
                for sc in (None, "reproducible_line", "random", "insufficient"):
                    for grid in (False, True):
                        for slot in (False, True):
                            out = lr.rank_suspects(pat, rep, az, sc, {"line": 1, "arc": 3} if sc else None,
                                                   slot, grid, {pat: 3, "NEAR_FULL": 2})
                            assert out and [s["rank"] for s in out] == list(range(1, len(out) + 1))
                            assert all(s["check"] for s in out) and len({s["source"] for s in out}) == len(out)
                            n += 1
    assert n == len(ACTION_DETAIL) * 4 * 4 * 4 * 2 * 2


def test_split_check_module_label_rules():
    """모듈 라벨은 ':' 앞 40자 이하 + 장비 키워드 + 여는 괄호 없음. 전 first_checks 에서 라벨에 '(' 가 없다."""
    assert lr.split_check("타사 CMP 다존 헤드 존 경계(인계)") == ("common", "타사 CMP 다존 헤드 존 경계(인계)")      # ':' 없음
    assert lr.split_check("CLEAN TRACK LITHIUS Pro: EBR 편심") == ("CLEAN TRACK LITHIUS Pro", "EBR 편심")
    c = "VHF CCP 식각이면 RF 정재파(center-high: 전극 지름이 유효 RF 파장의 절반 수준) 조건"
    assert lr.split_check(c) == ("common", c)                                                           # 괄호 안 ':'
    assert lr.split_check("링 폭 추세: 로트 사이에 서서히") == ("common", "링 폭 추세: 로트 사이에 서서히")   # 키워드 없음
    assert lr._module_of("Tactras / Episode UL: ESC") == "Tactras / Episode UL"
    for pat, d in ACTION_DETAIL.items():
        for c in d["first_checks"] + [d.get("rule_out_first", "")]:
            mod, body = lr.split_check(c)
            assert "(" not in mod and len(mod) <= lr.MODULE_LABEL_MAX_LEN, (pat, mod)
            assert body == (c if mod == "common" else c.split(":", 1)[1].strip())
    center = [lr._module_of(c) for c in ACTION_DETAIL["CENTER"]["first_checks"]]
    assert not any("정재파" in m for m in center)


# ──────────────────────────────────────────
# 격자 반복 휴리스틱
# ──────────────────────────────────────────
def _periodic_map(seed: int, pitch: int = 5, size: int = 2, noise: float = 0.03) -> np.ndarray:
    r = np.random.default_rng(seed)
    df = generate_sample_wafer_data(wafer_diameter_mm=300, die_size_mm=8, defect_mode="clean", noise=0.0, seed=seed)
    x = np.rint(df["die_x"] / 8).astype(int)
    y = np.rint(df["die_y"] / 8).astype(int)
    fail = ((x - r.integers(pitch)) % pitch < size) & ((y - r.integers(pitch)) % pitch < size)
    fail = np.where(r.random(len(df)) < noise, ~fail, fail)
    df["status"] = np.where(fail, "FAIL", "PASS")
    return df_to_wafermap(df, 8)


def test_grid_repeat_score_detects_planted_grid_only(rng):
    for pitch in (4, 6):
        g = lr.grid_repeat_score(_periodic_map(pitch, pitch=pitch))
        assert g["suspect"] and g["lag_x"] == pitch and g["lag_y"] == pitch, g
    for mode in ("ring", "center", "random", "edge_loc", "scratch", "loc", "near_full"):
        hits = sum(lr.grid_repeat_score(make_wafermap(mode, 900 + i, rng))["suspect"] for i in range(6))
        assert hits == 0, (mode, hits)
    assert lr.grid_repeat_score(np.ones((5, 5)))["suspect"] is False           # 불량 없음
    assert lr.grid_repeat_score(np.full((4, 4), 2))["suspect"] is False        # 너무 작은 맵


def test_grid_repeat_raises_flag_in_lot(rng):
    rows = [("grid", i, _periodic_map(i), "LOC") for i in range(1, 4)]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "grid")
    assert any("격자" in s for s in f.test_exclusion_flags) and all(w["grid_repeat"]["suspect"] for w in f.wafers)
    assert f.suspects[0]["source"] == "rule_out_first" and "격자" in f.suspects[0]["basis"]


# ──────────────────────────────────────────
# 입력 결합
# ──────────────────────────────────────────
def test_merge_by_order_and_by_index_and_errors(rng):
    maps = [make_wafermap("center", 60 + i, rng) for i in range(3)]
    rec = pd.DataFrame({"waferMap": maps, "lot": "m", "wafer_index": [np.nan] * 3})
    pr = pd.DataFrame({"lot": ["m"] * 3, "y_pred": ["CENTER", "CENTER", "RANDOM"]})
    f = lr.analyze_lot(rec, pr, "m")                                  # 행 순서 결합
    assert f.mix == {"CENTER": 2, "RANDOM": 1} and f.slot is None and f.n_low_conf is None
    with pytest.raises(ValueError, match="결합할 수 없다.*결측.*행 수"):
        lr.analyze_lot(rec, pr.iloc[:2], "m")
    with pytest.raises(ValueError, match="없다"):
        lr.analyze_lot(rec, pr, "nope")
    with pytest.raises(ValueError, match="예측 CSV 에 로트"):
        lr.analyze_lot(pd.DataFrame({"waferMap": maps, "lot": "q", "wafer_index": [1, 2, 3]}), pr, "q")
    # 예측 없이 y_true 로
    rec["y_true"] = ["CENTER", "CENTER", "CENTER"]
    f = lr.analyze_lot(rec, None, "m")
    assert f.label_source == "y_true" and f.dominant == "CENTER" and f.repeat_verdict == "process"
    # 라벨이 일부에만 있으면 그 웨이퍼만
    rec2 = pd.DataFrame({"waferMap": maps, "lot": "k", "wafer_index": [1, 2, 3]})
    pr2 = pd.DataFrame({"lot": ["k", "k"], "wafer_index": [3, 1], "y_pred": ["CENTER", "LOC"], "confidence": [0.5, 0.95]})
    f = lr.analyze_lot(rec2, pr2, "k")
    assert f.n == 2 and [w["wafer_index"] for w in f.wafers] == [1, 3] and f.n_low_conf == 1


def test_pred_wafer_index_nan_falls_back_to_order(rng, capsys):
    """예측 CSV 쪽 wafer_index 만 결측(records 는 있음) -> 행 순서 결합. 예전엔 '라벨 있는 웨이퍼가 없다'."""
    maps = [make_wafermap("edge_loc", 80 + i, rng) for i in range(4)]
    rec = pd.DataFrame({"waferMap": maps, "lot": "D", "wafer_index": [1, 2, 3, 4]})
    pr = pd.DataFrame({"lot": "D", "wafer_index": [np.nan] * 4, "y_pred": ["EDGE_LOC"] * 3 + ["CLEAN"],
                       "confidence": [0.9, 0.8, 0.95, 0.6]})
    f = lr.analyze_lot(rec, pr, "D", verbose=True)
    assert f.n == 4 and f.mix == {"EDGE_LOC": 3, "CLEAN": 1} and [w["wafer_index"] for w in f.wafers] == [1, 2, 3, 4]
    assert "순서 결합 4장" in capsys.readouterr().out
    # 일부 키만 결측: 키 행은 키로, 결측 행은 남은 행끼리 순서로
    pr2 = pd.DataFrame({"lot": "D", "wafer_index": [4, np.nan, 2, np.nan], "y_pred": ["w4", "x", "w2", "y"]})
    f = lr.analyze_lot(rec, pr2, "D")
    assert [w["y_pred"] for w in f.wafers] == ["x", "w2", "y", "w4"]
    # 키가 전혀 안 맞고 행 수도 다르면 결합 실패 - 결측 장수가 문구에 있다
    pr3 = pd.DataFrame({"lot": "D", "wafer_index": [9, 10], "y_pred": ["a", "b"]})
    with pytest.raises(ValueError, match="records 0장, 예측 0행"):
        lr.analyze_lot(rec, pr3, "D")


def test_history_without_overlapping_lots_skips_commonality_only(demo, rng, tmp_path, capsys):
    hist = demo["hist"].copy()
    hist["lot"] = "other_" + hist["lot"].astype(str)
    f = lr.analyze_lot(demo["records"], demo["preds"], lr.DEMO_LOTS[0], history=hist, synthetic=True, verbose=True)
    assert f.commonality_top == [] and "겹치지" in f.commonality_note
    assert "[주의] 공통성 생략" in capsys.readouterr().out
    assert f.dominant == "EDGE_LOC" and f.ocap_level == "L2"                # 나머지 판정은 그대로
    d = lr.findings_to_json(f)
    assert d["commonality_note"] == f.commonality_note
    out = tmp_path / "nohist.pdf"
    lr.render_lot_pdf(f, demo["records"], out, lang="en")
    text = _pdf_text(out)
    if text is not None:
        assert "commonality skipped" in text
    # 이력이 맞으면 note 는 비어 있다
    f2 = lr.analyze_lot(demo["records"], demo["preds"], lr.DEMO_LOTS[0], history=demo["hist"], synthetic=True)
    assert f2.commonality_note == "" and f2.commonality_top


# ──────────────────────────────────────────
# 저신뢰 임계값
# ──────────────────────────────────────────
def test_low_conf_threshold_rule(demo, rng):
    t, basis, n = lr.resolve_low_conf_threshold(demo["preds"])
    conf = demo["preds"]["confidence"].to_numpy(float)
    assert basis == "quantile" and n == len(conf) >= lr.MIN_N_CONF_QUANTILE and t == pytest.approx(np.quantile(conf, 0.10))
    assert lr.resolve_low_conf_threshold(demo["preds"], threshold=0.5) == (0.5, "explicit", 0)
    assert lr.resolve_low_conf_threshold(demo["preds"].head(10)) == (lr.LOW_CONF_FALLBACK, "fixed", 10)
    assert lr.resolve_low_conf_threshold(demo["preds"].drop(columns="confidence")) == (lr.LOW_CONF_FALLBACK, "fixed", 0)
    assert lr.resolve_low_conf_threshold(None) == (lr.LOW_CONF_FALLBACK, "fixed", 0)
    assert lr.resolve_low_conf_threshold(demo["preds"], quantile=0.5)[0] == pytest.approx(np.median(conf))
    # analyze_lot: 로트 하나만 넘기면 고정값, 예측 전체면 분위수, 명시값이 우선
    f = lr.analyze_lot(demo["records"], demo["preds"], lr.DEMO_LOTS[0], synthetic=True)
    assert f.conf_threshold_basis == "quantile" and f.conf_threshold == pytest.approx(t)
    assert f.n_low_conf == int((demo["preds"].loc[demo["preds"]["lot"] == lr.DEMO_LOTS[0], "confidence"] < t).sum())
    f = lr.analyze_lot(demo["records"], demo["preds"], lr.DEMO_LOTS[0], synthetic=True, conf_threshold=0.99)
    assert f.conf_threshold_basis == "explicit" and f.n_low_conf == 8
    rows = [("one", i, make_wafermap("ring", 90 + i, rng), "EDGE_RING") for i in (1, 2, 3)]
    rec, pr = _lot(rows, conf=0.65)
    f = lr.analyze_lot(rec, pr, "one")
    assert f.conf_threshold == lr.LOW_CONF_FALLBACK and f.conf_threshold_basis == "fixed" and f.n_low_conf == 3
    for lang in ("ko", "en"):
        s = lr.conf_basis_text(f, lr.LABELS[lang])
        assert "3" in s and str(lr.MIN_N_CONF_QUANTILE) in s
    d = lr.findings_to_json(f)
    assert d["conf_threshold"] == 0.7 and d["conf_threshold_basis"] == "fixed" and d["conf_threshold_n"] == 3


# ──────────────────────────────────────────
# JSON / PDF
# ──────────────────────────────────────────
def test_findings_json_serializable_and_anonymized(demo, tmp_path):
    f = lr.analyze_lot(demo["records"], demo["preds"], lr.DEMO_LOTS[0], history=demo["hist"], synthetic=True)
    d = lr.findings_to_json(f)
    s = json.dumps(d, ensure_ascii=False, allow_nan=False)             # NaN 이 있으면 ValueError
    assert d["synthetic"] is True and d["anonymized"] is False and d["lot"] == lr.DEMO_LOTS[0]
    assert d["ocap_label"]["ko"].startswith("L2") and "notch_deg=-90" in d["notch_note"]
    assert "Synthetic" in d["disclaimer"] and d["azimuth"]["verdict"] == "fixed_angle"
    da = lr.save_findings_json(f, tmp_path / "a.json", anonymize=True, salt=b"s")
    text = (tmp_path / "a.json").read_text(encoding="utf-8")
    assert lr.DEMO_LOTS[0] not in text and da["lot"].startswith("LOT-") and da["anonymized"] is True
    assert da["lot"] in da["d2_draft"]
    assert len(s) > 1000
    # 장비·챔버 ID 도 익명화된다 (docs/handoff.md 4절). 공정 단계명은 남는다. 같은 salt 면 같은 해시.
    tools = {c["tool"] for c in f.commonality_top}
    assert tools and all(re.fullmatch(r"(ETCH|CVD|TRK|CLN)-\d\d", t) for t in tools)      # 가상 ID 원문
    assert not any(t in text for t in tools) and all(c["tool"].startswith("TOOL-") for c in da["commonality_top"])
    assert all(re.fullmatch(r"CH-[0-9a-f]{8}", c["chamber"]) for c in da["commonality_top"] if c["chamber"])
    assert {c["step"] for c in da["commonality_top"]} == {c["step"] for c in f.commonality_top}
    assert lr.anonymize_commonality(f.commonality_top, b"s") == da["commonality_top"]
    assert lr.anonymize_commonality(f.commonality_top, b"t") != da["commonality_top"]
    assert lr.anonymize_unit_id("", b"s", "CH-") == ""
    out = tmp_path / "anon.pdf"
    lr.render_lot_pdf(f, demo["records"], out, lang="en", anonymize=True, salt=b"s")
    ptext = _pdf_text(out)
    if ptext is not None:
        assert not any(t in ptext for t in tools) and da["commonality_top"][0]["tool"] in ptext
        assert lr.DEMO_LOTS[0] not in ptext


@pytest.fixture(scope="module")
def rendered(demo, tmp_path_factory):
    out = tmp_path_factory.mktemp("lot") / "edge.pdf"
    f = lr.analyze_lot(demo["records"], demo["preds"], lr.DEMO_LOTS[0], history=demo["hist"], synthetic=True)
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        lr.render_lot_pdf(f, demo["records"], out, lang="ko")
    return {"findings": f, "path": out, "bytes": out.read_bytes(), "warnings": [str(x.message) for x in w]}


def test_pdf_no_missing_glyph_warnings(rendered):
    bad = [m for m in rendered["warnings"] if "missing from font" in m]
    assert not bad, bad[:3]


def test_pdf_pages_and_metadata(rendered):
    data = rendered["bytes"]
    n = _count_pages(data)
    assert 1 <= n <= 3
    assert f"{n} pages".encode() in data and b"synthetic data" in data and b"OCAP L2" in data
    assert b"lot_report" in data.replace(b"wm811k_lot_report", b"lot_report")
    text = _pdf_text(rendered["path"])
    if text is not None:
        assert lr.DEMO_LOTS[0] in text and "fixed_angle" in text and "OCAP" in text and "case_study_8d" in text
        assert "[ ]" in text                                              # 증거 체크박스


def test_pdf_en_and_anonymize_and_no_rose_for_small_lot(demo, tmp_path, rng):
    f = lr.analyze_lot(demo["records"], demo["preds"], lr.DEMO_LOTS[2], synthetic=True)
    out = tmp_path / "nf_en.pdf"
    lr.render_lot_pdf(f, demo["records"], out, lang="en", anonymize=True, salt=b"salt")
    data = out.read_bytes()
    assert b"lot id anonymized" in data and b"OCAP L1" in data
    text = _pdf_text(out)
    if text is not None:
        assert lr.DEMO_LOTS[2] not in text and "LOT-" in text and "Rule out test causes first" in text
    # EDGE_LOC 2장짜리 로트는 로즈 없이 1페이지에 들어갈 수 있어야 한다 (예외 없이 생성)
    rows = [("two", i, make_wafermap("edge_loc", 70 + i, rng), "EDGE_LOC") for i in (1, 2)]
    rec, pr = _lot(rows)
    f2 = lr.analyze_lot(rec, pr, "two")
    assert f2.azimuth["verdict"] == "insufficient" and f2.azimuth["n"] == 2
    out2 = tmp_path / "two.pdf"
    lr.render_lot_pdf(f2, rec, out2, lang="ko")
    assert 1 <= _count_pages(out2.read_bytes()) <= 2
    with pytest.raises(ValueError):
        lr.resolve_lang("jp")
    import batch_wafer_report as bwr
    assert lr.resolve_lang is bwr.resolve_lang                               # 한 곳에서만 정의한다


def test_many_wafers_spill_to_extra_thumbnail_page(rng, tmp_path):
    rows = [("big", i, make_wafermap("ring", 500 + i, rng), "EDGE_RING") for i in range(1, 41)]
    rec, pr = _lot(rows)
    f = lr.analyze_lot(rec, pr, "big")
    assert f.n == 40 and f.repeat_verdict == "process" and f.ocap_level == "L2"
    out = tmp_path / "big.pdf"
    lr.render_lot_pdf(f, rec, out, lang="ko")
    assert _count_pages(out.read_bytes()) >= 3                            # 썸네일 36 + 4, 텍스트


def test_labels_symmetric_and_cp949_safe():
    assert set(lr.LABELS["ko"]) == set(lr.LABELS["en"])
    for L in lr.LABELS.values():
        for v in L.values():
            for s in (v.values() if isinstance(v, dict) else [v]):
                s.encode("cp949")
    for lvl in lr.OCAP_LEVELS.values():
        for s in lvl.values():
            s.encode("cp949")
    src = Path(lr.__file__).read_text(encoding="utf-8")
    assert not any(ch in src for ch in "\u2014\u2212\u2248\u2192")        # em dash, minus, approx, arrow: 콘솔·PDF 글리프 안전
    Path(__file__).read_text(encoding="utf-8").encode("cp949")           # 이 테스트 파일도 cp949 안전


# ──────────────────────────────────────────
# CLI
# ──────────────────────────────────────────
def test_cli_demo_writes_pdf_and_json(tmp_path):
    out = tmp_path / "demo_out"
    r = subprocess.run([sys.executable, str(ROOT / "wm811k_lot_report.py"), "--demo", "--output", str(out)],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path,
                       env={**os.environ, "MPLBACKEND": "Agg"})
    assert r.returncode == 0, r.stderr
    assert "all as expected" in r.stdout
    for lot in lr.DEMO_LOTS:
        assert (out / f"lot_report_{lot}.pdf").stat().st_size > 10_000
        d = json.loads((out / f"lot_report_{lot}.json").read_text(encoding="utf-8"))
        assert d["synthetic"] is True and d["lot"] == lot
    assert not (ROOT / "lot_report_demo").exists()                        # --output 에만 쓴다
    assert "Glyph" not in r.stderr


def test_cli_real_path_with_pred_csv(demo, tmp_path):
    """pkl + 예측 CSV + 이력 CSV 경로 (LSWMD 형식 pkl 을 합성으로 만든다)."""
    rec = demo["records"]
    pkl = tmp_path / "rec.pkl"
    pd.DataFrame({"waferMap": rec["waferMap"], "lotName": rec["lot"], "waferIndex": rec["wafer_index"],
                  "failureType": [np.array([["Edge-Loc"]])] * len(rec)}).to_pickle(pkl)
    demo["preds"].to_csv(tmp_path / "pred.csv", index=False)
    demo["hist"].to_csv(tmp_path / "h.lot_history.csv", index=False)
    out = tmp_path / "o"
    r = subprocess.run([sys.executable, str(ROOT / "wm811k_lot_report.py"), str(pkl), "--pred", str(tmp_path / "pred.csv"),
                        "--lot", lr.DEMO_LOTS[1], "--history", str(tmp_path / "h.lot_history.csv"),
                        "--lang", "en", "--anonymize", "--output", str(out)],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path,
                       env={**os.environ, "MPLBACKEND": "Agg"})
    assert r.returncode == 0, r.stderr
    files = sorted(p.name for p in out.iterdir())
    assert len(files) == 2 and all(re.fullmatch(r"lot_report_LOT-[0-9a-f]{8}\.(pdf|json)", n) for n in files)
    assert lr.DEMO_LOTS[1] not in r.stdout and "repeat=process" in r.stdout and "q0.10" in r.stdout
    d = json.loads((out / files[0]).read_text(encoding="utf-8"))
    assert d["anonymized"] is True and d["scratch"]["verdict"] == "reproducible_line" and d["synthetic"] is False
    assert d["conf_threshold_basis"] == "quantile"
    assert not re.search(r"(ETCH|CVD|TRK|CLN)-\d\d", (out / files[0]).read_text(encoding="utf-8"))   # 장비 ID 없음
    # --conf-threshold 명시 + 이력과 안 겹치는 로트 -> 공통성만 생략, exit 0
    hist = demo["hist"].copy()
    hist["lot"] = "x_" + hist["lot"].astype(str)
    hist.to_csv(tmp_path / "h2.lot_history.csv", index=False)
    r = subprocess.run([sys.executable, str(ROOT / "wm811k_lot_report.py"), str(pkl), "--pred", str(tmp_path / "pred.csv"),
                        "--lot", lr.DEMO_LOTS[0], "--history", str(tmp_path / "h2.lot_history.csv"),
                        "--conf-threshold", "0.8", "--output", str(tmp_path / "o2")],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path, env={**os.environ, "MPLBACKEND": "Agg"})
    assert r.returncode == 0, r.stderr
    assert "[주의] 공통성 생략" in r.stdout and "confidence < 0.800" in r.stdout and "--conf-threshold" in r.stdout
    d = json.loads((tmp_path / "o2" / f"lot_report_{lr.DEMO_LOTS[0]}.json").read_text(encoding="utf-8"))
    assert d["commonality_top"] == [] and "겹치지" in d["commonality_note"] and d["conf_threshold"] == 0.8
    # 결합 실패는 traceback 이 아니라 한 줄 오류로 끝난다
    bad = demo["preds"].copy()
    bad["wafer_index"] = bad["wafer_index"] + 1000
    bad.to_csv(tmp_path / "bad.csv", index=False)
    r = subprocess.run([sys.executable, str(ROOT / "wm811k_lot_report.py"), str(pkl), "--pred", str(tmp_path / "bad.csv"),
                        "--lot", lr.DEMO_LOTS[0], "--output", str(tmp_path / "o3")],
                       capture_output=True, text=True, encoding="utf-8", cwd=tmp_path, env={**os.environ, "MPLBACKEND": "Agg"})
    assert r.returncode == 1 and "Traceback" not in r.stderr and "[오류]" in r.stderr and "결합할 수 없다" in r.stderr
