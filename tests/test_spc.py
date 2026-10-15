# tests/test_spc.py
# SPC 규칙·관리도 계산·데모 시나리오·현장 옵션(--group-col, --event-col, --anonymize)의 코딩 오류를 잡는다.
# 전부 합성 데이터다. 탐지 성능 주장이 아니라 로직 확인이다.

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import wm811k_spc as spc  # noqa: E402

INJECTED = {"EDGE_RING": 3000, "LOW_CONFIDENCE": 3750, "SCRATCH": 4125}   # 데모에 심은 시점 (웨이퍼 순번)
NOT_INJECTED = ["CENTER", "LOC", "EDGE_LOC", "DONUT", "RANDOM", "NEAR_FULL"]


@pytest.fixture(scope="module")
def demo():
    """데모 시퀀스와 그 관리도. 모듈 안에서 한 번만 만든다."""
    df = spc.demo_predictions()
    n_base_rows = len(df) // 2
    thr, how = spc.resolve_conf_threshold(df, n_base_rows, None, 0.10)
    charts, sizes, dropped = spc.build_all(df, spc.CLASSES, 25, False, n_base_rows, thr)
    alarms = spc.alarm_table(charts, spc.chart_mode(df))
    return dict(df=df, n_base_rows=n_base_rows, thr=thr, how=how, charts=charts,
                sizes=sizes, dropped=dropped, alarms=alarms)


# ──────────────────────────────────────────
# 규칙
# ──────────────────────────────────────────
def test_western_electric_rules_fire_where_expected():
    z = np.zeros(20)
    z[5] = 3.5                                  # R1
    z[10], z[11] = 2.5, 2.5                     # R2: 3점 중 2점 2σ 밖 (같은 쪽)
    r = spc.western_electric(z)
    assert r["R1"][5] and r["R1"].sum() == 1
    assert r["R2"][11]
    assert not r["R2"][10]                      # 창이 완성되는 점에서만 표시

    z = np.full(12, 0.5)                        # R4: 8점 연속 같은 쪽
    r = spc.western_electric(z)
    assert not r["R4"][6] and r["R4"][7] and r["R4"][11]

    z = np.array([1.5, 1.5, -0.2, 1.5, 1.5])    # R3: 5점 중 4점 1σ 밖
    assert spc.western_electric(z)["R3"][4]
    assert not spc.western_electric(-z)["R2"].any()


def test_western_electric_sides_do_not_mix():
    z = np.array([2.5, -2.5, 0.1])              # 2σ 밖 2점이 서로 반대쪽 → R2 아님
    assert not spc.western_electric(z)["R2"].any()
    z = np.array([2.5, -2.5, 2.5])              # 가운데가 반대쪽이어도 같은 쪽 2점 → R2
    assert spc.western_electric(z)["R2"][2]


def test_ewma_limits_grow_to_asymptote():
    assert spc.EWMA_LAMBDA == 0.2 and spc.EWMA_L == 2.86      # λ=0.2, ARL0≈500 (Lucas & Saccucci 1990 표)
    e, lim = spc.ewma_chart(np.zeros(200))
    assert np.all(np.diff(lim) >= 0)
    assert lim[-1] == pytest.approx(spc.EWMA_L * np.sqrt(spc.EWMA_LAMBDA / (2 - spc.EWMA_LAMBDA)), rel=1e-3)
    assert np.all(e == 0)


# ──────────────────────────────────────────
# 부분군 묶기 / 입력
# ──────────────────────────────────────────
def test_chunk_ids_fixed_and_by_lot():
    df = pd.DataFrame({"lot": ["a"] * 10 + ["b"] * 30 + ["c"] * 8 + ["d"] * 3})
    gid = spc.chunk_ids(df, 25, by_lot=False)
    assert gid[:25].tolist() == [0] * 25 and gid[25:50].tolist() == [1] * 25
    assert (gid[50:] == -1).all()               # 꼬리 1장은 버린다
    gid = spc.chunk_ids(df, 25, by_lot=True)
    assert (gid[:40] == 0).all()                # a+b 를 합쳐 40장 ≥ 25
    assert (gid[40:] == -1).all()               # c+d 11장 < 25/2 → 버림


def test_chunk_ids_lot_larger_than_target_is_its_own_subgroup():
    df = pd.DataFrame({"lot": ["big"] * 60 + ["s1"] * 10 + ["s2"] * 20})
    gid = spc.chunk_ids(df, 25, by_lot=True)
    assert (gid[:60] == 0).all()                # 60장 로트는 쪼개지 않고 그대로 한 부분군
    assert (gid[60:] == 1).all()                # s1+s2 = 30 ≥ 25


def test_load_predictions_filters_skipped_and_sorts_by_time_col(tmp_path, capsys):
    p = tmp_path / "pred.csv"
    pd.DataFrame({"lot": ["L1", "L1", "L2", "L2"], "y_pred": ["CENTER", "LOC", None, "SCRATCH"],
                  "skipped": [False, False, True, False], "score": [0.9, 0.8, 0.0, 0.7],
                  "t": [3, 2, 1, 0]}).to_csv(p, index=False)
    df = spc.load_predictions(p, time_col="t")
    assert len(df) == 2 + 1                     # skipped 1행 제외 (y_pred None 인 행이 그 행)
    assert df["t"].tolist() == sorted(df["t"].tolist())      # 역순 입력이 시간 순으로
    assert df["y_pred"].tolist() == ["SCRATCH", "LOC", "CENTER"]
    # confidence 가 없고 score 만 있으면 별칭 + 경고
    assert "confidence" in df.columns and df.attrs["confidence_source"] == "score"
    assert "휴리스틱" in capsys.readouterr().out


def test_chart_mode_incidence_vs_share():
    assert spc.chart_mode(pd.DataFrame({"y_pred": ["CENTER", "CLEAN"]})) == "incidence"
    assert spc.chart_mode(pd.DataFrame({"y_pred": ["CENTER", "none"]})) == "incidence"
    assert spc.chart_mode(pd.DataFrame({"y_pred": ["CENTER", "LOC"]})) == "share"


# ──────────────────────────────────────────
# 관리도 계산
# ──────────────────────────────────────────
def test_p_chart_center_from_baseline_only():
    S = pd.DataFrame({"n": [25] * 10, "count": [5] * 5 + [20] * 5, "end_idx": np.arange(25, 251, 25)})
    ch = spc.p_chart("X", S, n_base=5, laney=False)
    assert ch.center == pytest.approx(0.2)
    assert ch.alarms["R1"][5:].all() and not ch.alarms["R1"][:5].any()
    assert (ch.ucl <= 1).all() and (ch.lcl >= 0).all()


def test_laney_widens_limits_under_overdispersion():
    rng = np.random.default_rng(0)
    n = np.full(60, 100)
    # 부분군마다 p 자체가 크게 흔들리는 과산포 시퀀스
    p_true = np.clip(rng.normal(0.3, 0.12, 60), 0.02, 0.98)
    count = rng.binomial(n, p_true)
    S = pd.DataFrame({"n": n, "count": count, "end_idx": np.cumsum(n) - 1})
    plain = spc.p_chart("X", S, n_base=30, laney=False)
    laney = spc.p_chart("X", S, n_base=30, laney=True)
    assert laney.sigma_z > 1.5 and not laney.laney_skipped
    assert laney.alarms["R1"].sum() < plain.alarms["R1"].sum()


def test_laney_skipped_when_baseline_is_short():
    rng = np.random.default_rng(1)
    n = np.full(40, 100)
    S = pd.DataFrame({"n": n, "count": rng.binomial(n, 0.3), "end_idx": np.cumsum(n) - 1})
    ch = spc.p_chart("X", S, n_base=10, laney=True)       # 10 < 20 → 보정 생략
    assert ch.laney_skipped and ch.sigma_z == 1.0
    ch = spc.p_chart("X", S, n_base=20, laney=True)
    assert not ch.laney_skipped


@pytest.mark.parametrize("seed", [0, 1, 2])
def test_laney_near_one_for_iid_binomial(seed):
    """i.i.d. 이항 데이터(과산포 없음)에서 n_base ≥ 30 이면 σz 추정이 1.2 를 넘지 않아야 한다."""
    rng = np.random.default_rng(seed)
    n = np.full(80, 200)
    S = pd.DataFrame({"n": n, "count": rng.binomial(n, 0.1), "end_idx": np.cumsum(n) - 1})
    ch = spc.p_chart("X", S, n_base=40, laney=True)
    assert 1.0 <= ch.sigma_z <= 1.2


def test_build_charts_drops_when_baseline_has_fewer_than_3_subgroups():
    rng = np.random.default_rng(0)
    n = 600
    df = pd.DataFrame({"lot": [f"l{i // 25}" for i in range(n)],
                       "y_pred": rng.choice(["CENTER", "CLEAN"], size=n, p=[0.3, 0.7])})
    # baseline 150장 = 25장 부분군 6개 → CENTER 관리도 생성
    charts, sizes, dropped = spc.build_charts(df, ["CENTER"], 25, False, 150, None)
    assert [c.name for c in charts] == ["CENTER"] and charts[0].n_base == 6
    # baseline 60장 = 부분군 2개 < 3 → 관리도 없음, 사유 기록. 감시 구간을 끌어오지 않는다
    charts, sizes, dropped = spc.build_charts(df, ["CENTER"], 25, False, 60, None)
    assert charts == [] and "CENTER" in dropped and "baseline 부분군 2개" in dropped["CENTER"]


def test_build_charts_uses_both_normal_approximation_conditions():
    rng = np.random.default_rng(0)
    n = 4000
    y = np.where(rng.random(n) < 0.96, "CENTER", "CLEAN")      # p ≈ 0.96 → n(1-p) ≥ 5 가 제약
    df = pd.DataFrame({"lot": [f"l{i // 25}" for i in range(n)], "y_pred": y})
    charts, sizes, dropped = spc.build_charts(df, ["CENTER"], 25, False, 2000, None)
    assert sizes["CENTER"] >= 125                               # 5 / 0.04 = 125


def test_low_confidence_chart_from_confidence_or_score_alias(tmp_path, capsys):
    rng = np.random.default_rng(0)
    n = 2000
    base = pd.DataFrame({"lot": [f"l{i // 25}" for i in range(n)],
                         "y_pred": rng.choice(["CENTER", "LOC", "CLEAN"], size=n, p=[0.1, 0.1, 0.8])})
    conf = rng.beta(8, 1.2, size=n)
    # (1) confidence 열 → LOW_CONFIDENCE 관리도 생성, 임계값은 baseline 분위수
    df = base.assign(confidence=conf)
    thr, how = spc.resolve_conf_threshold(df, 1000, None, 0.10)
    assert how.startswith("baseline q") and thr == pytest.approx(np.quantile(conf[:1000], 0.10))
    charts, _, _ = spc.build_charts(df, ["CENTER"], 25, False, 1000, thr)
    assert "LOW_CONFIDENCE" in {c.name for c in charts}
    # (2) score 만 있으면 load_predictions 가 별칭 경고를 내고, 그 뒤 똑같이 생성
    p = tmp_path / "pred.csv"
    base.assign(score=conf).to_csv(p, index=False)
    df2 = spc.load_predictions(p)
    assert "확률 아님" in capsys.readouterr().out
    thr2, _ = spc.resolve_conf_threshold(df2, 1000, None, 0.10)
    charts2, _, _ = spc.build_charts(df2, ["CENTER"], 25, False, 1000, thr2)
    assert "LOW_CONFIDENCE" in {c.name for c in charts2}
    # (3) 명시 임계값은 그대로
    assert spc.resolve_conf_threshold(df, 1000, 0.5, 0.10) == (0.5, "--conf-threshold")


# ──────────────────────────────────────────
# 데모 시나리오
# ──────────────────────────────────────────
def test_demo_is_incidence_scenario_with_mostly_clean_wafers(demo):
    df = demo["df"]
    assert spc.chart_mode(df) == "incidence"
    assert 0.80 < (df["y_pred"][: demo["n_base_rows"]] == "CLEAN").mean() < 0.90
    assert set(df["chamber"]) == {"A", "B"} and set(df.columns) >= {"lot", "y_pred", "confidence", "chamber", "event"}
    assert df.loc[2900, "event"] == "focus_ring_replaced" and (df["event"] != "").sum() == len(spc.DEMO["events"])
    # 드리프트는 B 챔버에만: A 챔버의 EDGE_RING 비율은 전후가 같은 수준
    a = df[df["chamber"] == "A"]
    before = (a["y_pred"][a.index < 3000] == "EDGE_RING").mean()
    after = (a["y_pred"][a.index >= 4000] == "EDGE_RING").mean()
    assert abs(after - before) < 0.03


def test_demo_detects_injected_shifts_in_window(demo):
    by_name = {ch.name: ch for ch in demo["charts"]}
    assert {"EDGE_RING", "SCRATCH", "LOW_CONFIDENCE"} <= set(by_name)
    fd = spc.first_detection(demo["alarms"]).set_index(["chart", "rule"])["first_wafer_idx"]
    # 심은 시점 이후, 완만한 드리프트(40로트 램프)는 1000장, 계단·저신뢰는 부분군 몇 개 안
    assert 3000 <= fd[("EDGE_RING", "EWMA")] <= 3000 + 1000
    assert 3750 <= fd[("LOW_CONFIDENCE", "EWMA")] <= 3750 + 400
    assert 4125 <= fd[("SCRATCH", "EWMA")] <= 4125 + 1000
    # 심은 시점 이전의 감시 구간에는 상승 알람이 없어야 한다
    mon = demo["alarms"][(demo["alarms"]["phase"] == "monitor") & (demo["alarms"]["direction"] == "up")]
    for name, t0 in INJECTED.items():
        assert not ((mon["chart"] == name) & (mon["wafer_end_idx"] < t0)).any(), name


def test_demo_non_injected_patterns_stay_quiet(demo):
    """발생률 관리도라 EDGE_RING 이 올라도 다른 패턴이 기계적으로 내려가지 않는다."""
    mon = demo["alarms"][(demo["alarms"]["phase"] == "monitor") & (demo["alarms"]["direction"] == "up")]
    assert int(mon["chart"].isin(NOT_INJECTED).sum()) <= 3
    base = demo["alarms"][demo["alarms"]["phase"] == "baseline"]
    assert len(base) <= 0.03 * sum(ch.n_base for ch in demo["charts"])


def test_demo_plot_and_report(demo, tmp_path):
    events = spc.event_marks(demo["df"], "event")
    spc.plot_charts(demo["charts"], demo["n_base_rows"], tmp_path / "demo.png", "t", lang="en", events=events)
    assert (tmp_path / "demo.png").stat().st_size > 10_000
    ev = spc.event_distance(demo["charts"], demo["alarms"], events)
    spc.write_report(tmp_path / "r.md", dict(
        lang="ko", stem="t", source="demo", synthetic=True, mode="incidence", range_text="r",
        settings_text="s", base_rate_text="b", charts=demo["charts"], alarms=demo["alarms"],
        n_down=0, event_dist=ev, group_table=None, dropped=demo["dropped"], png_name="demo.png"))
    text = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "EDGE_RING" in text and "합성" in text and "demo.png" in text


def test_alarm_table_marks_down_alarms_and_has_field_columns():
    S = pd.DataFrame({"n": [100] * 12, "count": [30] * 6 + [5, 60, 5, 60, 5, 60], "end_idx": np.arange(100, 1300, 100)})
    ch = spc.p_chart("CENTER", S, n_base=6, laney=False)
    a = spc.alarm_table([ch], "share")
    assert {"acknowledged_at", "action", "verified_at", "note", "lots"} <= set(a.columns)
    down = a[a["direction"] == "down"]
    assert len(down) and (down["note"] == "down: 다른 패턴 상승의 반작용 가능").all()
    assert (a.loc[a["direction"] == "up", "note"] == "").all()
    assert spc.first_detection(a, up_only=True)["rule"].tolist()          # 상승만 남는다
    assert set(spc.first_detection(a, up_only=False)["chart"]) == {"CENTER"}


# ──────────────────────────────────────────
# 현장 옵션: --group-col, --event-col, --anonymize
# ──────────────────────────────────────────
def test_group_col_demo_alarms_only_in_chamber_b(demo):
    df, nb = demo["df"], demo["n_base_rows"]
    charts, sizes, dropped = spc.build_all(df, spc.CLASSES, 25, False, nb, demo["thr"], group_col="chamber")
    names = {ch.name for ch in charts}
    assert "EDGE_RING@A" in names and "EDGE_RING@B" in names
    assert all(ch.end_idx.max() < len(df) for ch in charts)               # x축은 전역 웨이퍼 순번
    alarms = spc.alarm_table(charts, "incidence")
    mon = alarms[(alarms["phase"] == "monitor") & (alarms["direction"] == "up")]
    ewma = mon[mon["rule"] == "EWMA"]
    assert not ewma["chart"].str.endswith("@A").any()                    # A 챔버는 EWMA 알람 없음
    fd = spc.first_detection(alarms).set_index(["chart", "rule"])["first_wafer_idx"]
    assert 3000 <= fd[("EDGE_RING@B", "EWMA")] <= 4000
    assert 3750 <= fd[("LOW_CONFIDENCE@B", "EWMA")] <= 4150
    # 그룹 간 발생률 검정: 감시 구간에서 EDGE_RING 만 유의, baseline 에서는 둘 다 유의하지 않음
    t = spc.group_rate_test(df, "chamber", ["EDGE_RING", "CENTER"], nb).set_index("pattern")
    assert t.loc["EDGE_RING", "p_monitor"] < 1e-3 and t.loc["EDGE_RING", "p_baseline"] > 0.01
    assert t.loc["CENTER", "p_monitor"] > 0.01
    assert t.loc["EDGE_RING", "rate@B"] > t.loc["EDGE_RING", "rate@A"] + 0.03


def test_event_col_distance_to_nearest_previous_event(demo):
    df = demo["df"]
    events = spc.event_marks(df, "event", group_col="chamber")
    assert events["idx"].tolist() == sorted(spc.DEMO["events"]) and events.loc[1, "group"] == "B"
    ev = spc.event_distance(demo["charts"], demo["alarms"], events).set_index("chart")
    fd = spc.first_detection(demo["alarms"]).groupby("chart")["first_wafer_idx"].min()
    for name in ("EDGE_RING", "SCRATCH", "LOW_CONFIDENCE"):
        assert ev.loc[name, "event"] == "focus_ring_replaced"              # 2900 이 가장 가까운 이전 이벤트
        assert ev.loc[name, "wafers_since_event"] == fd[name] - 2900
    # 이벤트가 알람보다 뒤에만 있으면 '이전 이벤트 없음'
    late = pd.DataFrame({"idx": [5990], "label": ["x"], "group": [None]})
    ev2 = spc.event_distance(demo["charts"], demo["alarms"], late).set_index("chart")
    assert (ev2["event_idx"] == -1).all()


def test_anonymize_removes_original_ids_from_outputs(demo, tmp_path):
    df = demo["df"]
    anon = spc.anonymize_ids(df, ["lot", "chamber"], salt=b"test")
    assert not set(anon["lot"]) & set(df["lot"]) and anon["lot"].nunique() == df["lot"].nunique()
    assert set(anon["chamber"]) & {"A", "B"} == set() and anon["chamber"].nunique() == 2
    # 같은 salt 면 같은 해시, 다른 salt 면 다른 해시 (매핑 표를 저장하지 않아도 한 실행 안에서는 일관)
    assert anon["lot"].equals(spc.anonymize_ids(df, ["lot"], salt=b"test")["lot"])
    assert not anon["lot"].equals(spc.anonymize_ids(df, ["lot"], salt=b"other")["lot"])
    charts, _, _ = spc.build_charts(anon, ["EDGE_RING"], 25, False, demo["n_base_rows"], None)
    alarms = spc.alarm_table(charts, "incidence")
    out = tmp_path / "a.csv"
    alarms.to_csv(out, index=False)
    text = out.read_text()
    assert "lot0" not in text and "lots" in text and len(alarms)


def test_main_demo_end_to_end(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(spc, "setup_korean_font", lambda: None)        # 폰트 없는 환경 → 그림만 en
    spc.main(["--demo", "--group-col", "chamber", "--event-col", "event", "--anonymize",
              "--output", str(tmp_path)])
    out = capsys.readouterr().out
    assert "발생률 관리도" in out and "영문(en)으로 전환" in out and "focus_ring_replaced" in out
    for suffix in (".png", "_alarms.csv", "_subgroups.csv", "_report.md"):
        assert (tmp_path / f"spc_demo{suffix}").exists()
    a = pd.read_csv(tmp_path / "spc_demo_alarms.csv")
    assert not a["chart"].str.endswith("@A").any() and not a["chart"].str.endswith("@B").any()   # 그룹 ID 익명화
    assert {"acknowledged_at", "action", "verified_at"} <= set(a.columns)
