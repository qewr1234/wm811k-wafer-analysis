# plotly_wafer_heatmap.py
# Plotly go.Heatmap 기반 웨이퍼 파라메트릭(연속값) 맵
#
# 배경
#   빈 맵(pass/fail)은 테스트 결과라 모든 공정이 누적된 뒤에야 나온다. 현장
#   엔지니어가 그보다 먼저 보는 것은 파라메트릭 맵이다: 성막 두께(Triase+ /
#   Episode / TELINDY PLUS 계열 CVD·ALD·퍼니스의 두께 맵), 코터/디벨로퍼의 CD 맵
#   (CLEAN TRACK LITHIUS Pro 계열), 식각 깊이·CD 맵(Tactras 계열). 장비 균일도
#   이상(엣지 링 마모, 존 온도, 샤워헤드)은 빈 맵의 EDGE_RING/CENTER/DONUT 보다
#   이 맵에서 먼저 드러난다.
#
# 무엇을 하나
#   측정값 + 타깃 + 스펙 한계(±spec_frac)로 PASS/FAIL 을 도출하고, 타깃 중심의
#   발산형 컬러스케일로 '두꺼움/얇음' 양쪽 이탈을 구분해 그린다. 여러 웨이퍼를
#   서브플롯으로 묶고, 셀 위에 마우스를 올리면 좌표·값·판정이 보인다.
#
# 왜 자기완결 HTML 인가
#   팹 사무망·장비 PC 는 외부 인터넷이 차단된 경우가 많다. CDN 으로 plotly.js 를
#   불러오면 파일을 열어도 빈 화면이다. 그래서 기본값은 plotly.js 를 HTML 안에
#   포함(약 4MB)하고, 작은 파일이 필요할 때만 --cdn 을 쓴다.
#
# 한계
#   --demo(기본)는 합성 데이터다. 아래 타깃·스펙·저하량은 임의로 지정한 값이라
#   여기서 나오는 수율은 공정에 대한 정보가 아니다. 실측 연결은 --csv 로
#   (die_x, die_y, value) 를 읽는 경로이며, 스펙은 --target/--spec-frac 으로 준다.
#   TEL 장비의 실제 계측 포맷·내부 구현은 모른다.
#
# 사용법
#   python plotly_wafer_heatmap.py                       # 합성 6장 -> HERE/wafer_heatmap.html (오프라인 열람)
#   python plotly_wafer_heatmap.py --cdn                 # plotly.js 를 CDN 에서 (작은 파일, 인터넷 필요)
#   python plotly_wafer_heatmap.py --csv thick.csv --target 435 --spec-frac 0.05 --value-name 두께 --unit A
#   python plotly_wafer_heatmap.py --csv a.csv --csv b.csv --out lot.html
#
# 원본 대비 수정 사항
#   (여기서 '원본'은 이 저장소 최초 커밋 1df6309 'Add files via upload' 의 초기
#    스크립트다.)
#   [버그] 격자 비대칭 — grid_size=30, center=15 이면 좌표가 -15..+14 가 되어
#          웨이퍼 원이 0.5칸 치우친다. center=(grid_size-1)/2 로 수정.
#   [버그] 종횡비 미고정 — 히트맵 셀이 정사각이 아니어서 웨이퍼가 타원으로
#          그려진다. yaxis.scaleanchor 로 1:1 고정.
#   [버그] np.random.seed(2024)가 함수 안에 있어 같은 mode의 웨이퍼가
#          완전히 동일하게 생성된다. 또한 전역 시드를 오염시킨다.
#          → 웨이퍼별 seed 인자 + default_rng.
#   [버그] showscale=(idx==0) 이면 컬러바가 전체 figure 우측에 붙어
#          두 번째 서브플롯을 덮는다. 위치/길이를 명시.
#   [개선] Z의 의미 변경 — 다이별 "수율 점수 0~100"은 실측 대응물이 없다.
#          팹에서 실제로 그리는 것은 파라메트릭 맵(두께, Vt, 누설전류 등)이므로
#          측정값 + 스펙 한계로 바꾸고 PASS/FAIL을 스펙에서 도출한다.
#   [개선] 발산형(diverging) 컬러스케일 — 타깃 중심의 양쪽 이탈을 구분한다.
#          기존 순차형은 "타깃보다 두꺼움"과 "얇음"을 모두 초록으로 칠했다.
#   [개선] 이중 for 루프 → meshgrid 벡터화
#   [개선] 서브플롯 제목에 수율 표시, 웨이퍼 경계 원 추가
#   [개선] defect_mode를 wafer_map_visualizer와 동일한 7종으로 통일
#   [개선] write_html 기본 include_plotlyjs=True (오프라인), --cdn 옵션, 저장 경로 HERE 기준,
#          실측 CSV(die_x, die_y, value) 입력 --csv, Windows 콘솔 UTF-8.

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

HERE = Path(__file__).resolve().parent

DEFECT_MODES = ("ring", "center", "donut", "edge_loc", "scratch", "random", "clean")

# 측정 파라미터 기본값 — 성막 두께(Å)를 가정한 임의값(합성 데모용)
TARGET_A = 435.0
SPEC_FRAC = 0.05
DEPRESSION_A = 45.0     # 결함 영역의 두께 저하량 (스펙 폭의 약 2배)


@dataclass
class WaferField:
    """히트맵 한 장의 데이터."""
    Z: np.ndarray               # 측정값 (웨이퍼 밖은 NaN)
    x: np.ndarray               # 셀 중심 좌표
    y: np.ndarray
    target: float
    spec_lo: float
    spec_hi: float
    radius: float               # 웨이퍼 반경 (셀 단위) — 경계 원 그리기용

    @property
    def n_die(self) -> int:
        return int(np.isfinite(self.Z).sum())

    @property
    def n_fail(self) -> int:
        m = np.isfinite(self.Z)
        return int(((self.Z[m] < self.spec_lo) | (self.Z[m] > self.spec_hi)).sum())

    @property
    def yield_pct(self) -> float:
        return (1 - self.n_fail / self.n_die) * 100 if self.n_die else 0.0


def create_wafer_heatmap_data(
    grid_size: int = 31,
    wafer_radius: float = 14.5,
    defect_mode: str = "ring",
    target: float = TARGET_A,
    spec_frac: float = SPEC_FRAC,
    depression: float = DEPRESSION_A,
    noise_sd: float = 6.0,
    seed: int = 2024,
) -> WaferField:
    """웨이퍼 파라메트릭 맵 생성.

    측정값 = 타깃 + 완만한 반경 방향 프로파일 + 결함 영역 저하 + 계측 노이즈
    """
    if defect_mode not in DEFECT_MODES:
        raise ValueError(f"defect_mode must be one of {DEFECT_MODES}")

    rng = np.random.default_rng(seed)

    # 격자를 원점 대칭으로. center = (n-1)/2 여야 좌표가 ±동일 범위가 된다.
    c = (grid_size - 1) / 2.0
    coords = np.arange(grid_size) - c
    gx, gy = np.meshgrid(coords, coords)      # gy는 행 방향
    dist = np.hypot(gx, gy)
    inside = dist <= wafer_radius

    rn = np.divide(dist, wafer_radius, out=np.zeros_like(dist), where=wafer_radius > 0)
    ang = np.degrees(np.arctan2(gy, gx))

    # 실제 증착은 중심-엣지 간 완만한 기울기를 갖는다 (결함과 별개)
    Z = target - 4.0 * rn + rng.normal(0.0, noise_sd, size=dist.shape)

    if defect_mode == "ring":
        mask = rn > 0.80
    elif defect_mode == "center":
        mask = rn < 0.25
    elif defect_mode == "donut":
        mask = (rn > 0.40) & (rn < 0.62)
    elif defect_mode == "edge_loc":
        mask = (rn > 0.78) & (np.abs(ang - 45.0) <= 35.0)
    elif defect_mode == "scratch":
        theta = np.radians(30.0)
        mask = np.abs(-np.sin(theta) * gx + np.cos(theta) * gy) <= 1.2
    elif defect_mode == "random":
        mask = rng.random(dist.shape) < 0.05
    else:                                      # clean
        mask = np.zeros_like(dist, dtype=bool)

    # 결함 영역은 저하량에 산포를 준다. 경계가 칼같이 떨어지지 않게.
    Z = np.where(mask, Z - rng.normal(depression, depression * 0.25, size=dist.shape), Z)
    Z[~inside] = np.nan

    tol = target * spec_frac
    return WaferField(Z=Z, x=coords, y=coords, target=target,
                      spec_lo=target - tol, spec_hi=target + tol,
                      radius=wafer_radius)


def field_from_csv(
    path: str | Path,
    target: float | None = None,
    spec_frac: float = SPEC_FRAC,
) -> WaferField:
    """실측 CSV(die_x, die_y, value) -> WaferField.

    die_x/die_y 는 mm 든 다이 인덱스든 상관없다. 관측된 최소 간격을 다이 피치로
    보고 정수 격자에 올린다(같은 셀에 여러 행이면 평균). 격자 밖은 NaN.
    target 을 주지 않으면 측정값의 중앙값을 타깃으로 쓴다 - 스펙 판정이 데이터에
    끌려가므로 실제 사용 시에는 --target 을 명시할 것.
    """
    df = pd.read_csv(path)
    need = {"die_x", "die_y", "value"}
    if not need <= set(df.columns):
        raise ValueError(f"CSV 에 {sorted(need)} 열이 필요하다. 있는 열: {list(df.columns)}")
    df = df.dropna(subset=["die_x", "die_y"])
    if df.empty:
        raise ValueError("CSV 에 유효한 행이 없다")

    def _pitch(v: np.ndarray) -> float:
        u = np.unique(v)
        return float(np.min(np.diff(u))) if len(u) > 1 else 1.0

    px, py = _pitch(df["die_x"].to_numpy(float)), _pitch(df["die_y"].to_numpy(float))
    pitch = min(px, py)
    ix = np.rint(df["die_x"].to_numpy(float) / pitch).astype(int)
    iy = np.rint(df["die_y"].to_numpy(float) / pitch).astype(int)
    ix -= ix.min()
    iy -= iy.min()
    w, h = int(ix.max()) + 1, int(iy.max()) + 1

    Z = np.full((h, w), np.nan)
    cnt = np.zeros((h, w))
    acc = np.zeros((h, w))
    np.add.at(acc, (iy, ix), df["value"].to_numpy(float))
    np.add.at(cnt, (iy, ix), 1.0)
    has = cnt > 0
    Z[has] = acc[has] / cnt[has]

    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0
    x = np.arange(w) - cx
    y = np.arange(h) - cy
    gx, gy = np.meshgrid(x, y)
    radius = float(np.hypot(gx[has], gy[has]).max()) + 0.5

    t = float(np.nanmedian(Z)) if target is None else float(target)
    tol = t * spec_frac
    return WaferField(Z=Z, x=x, y=y, target=t, spec_lo=t - tol, spec_hi=t + tol, radius=radius)


def create_interactive_wafer_heatmap(
    lot_data: list[dict],
    value_name: str = "두께",
    unit: str = "Å",
    cols_max: int = 3,
) -> go.Figure:
    """여러 웨이퍼의 파라메트릭 맵을 서브플롯으로 구성.

    lot_data 항목: {"lot_id", "wafer_id", "mode"(합성) 또는 "field"(WaferField, 실측)}.
    """
    n = len(lot_data)
    cols = min(cols_max, n)
    rows = (n + cols - 1) // cols

    fields, titles = [], []
    for i, d in enumerate(lot_data):
        if "field" in d:
            f = d["field"]
            label = d.get("label", "measured")
        else:
            f = create_wafer_heatmap_data(
                defect_mode=d.get("mode", "random"),
                seed=d.get("seed", 2024 + i),      # 웨이퍼마다 다른 시드
            )
            label = d.get("mode", "random")
        fields.append(f)
        titles.append(
            f"{d['lot_id']} / {d['wafer_id']} ({label})<br>"
            f"<sub>Yield {f.yield_pct:.1f}%  |  "
            f"FAIL {f.n_fail}/{f.n_die}</sub>"
        )

    fig = make_subplots(rows=rows, cols=cols, subplot_titles=titles,
                        horizontal_spacing=0.06, vertical_spacing=0.16)

    # 발산형 스케일. 타깃이 중앙(흰색), 양쪽 이탈이 각각 붉은/푸른 계열.
    # 순차형(0=적, 100=녹)은 타깃 초과와 미달을 구분하지 못한다.
    f0 = fields[0]
    zmin, zmax = f0.target - 90.0, f0.target + 90.0
    colorscale = [
        [0.00, "#67001F"], [0.18, "#D6604D"], [0.38, "#FDDBC7"],
        [0.50, "#F7F7F7"],
        [0.62, "#D1E5F0"], [0.82, "#4393C3"], [1.00, "#053061"],
    ]

    for idx, (d, f) in enumerate(zip(lot_data, fields)):
        r, c = idx // cols + 1, idx % cols + 1

        status = np.where(
            np.isnan(f.Z), "",
            np.where((f.Z < f.spec_lo) | (f.Z > f.spec_hi), "FAIL", "PASS"),
        )
        # customdata로 넘기면 hover 문자열을 파이썬 이중 루프로 만들 필요가 없다
        fig.add_trace(
            go.Heatmap(
                z=f.Z, x=f.x, y=f.y,
                customdata=status,
                hovertemplate=(
                    "X %{x}, Y %{y}<br>"
                    + f"{value_name} " + "%{z:.1f}" + unit + "<br>"
                    "%{customdata}<extra></extra>"
                ),
                colorscale=colorscale, zmin=zmin, zmax=zmax,
                showscale=(idx == 0),
                colorbar=dict(
                    title=dict(text=f"{value_name}<br>({unit})", side="right"),
                    len=0.85, y=0.5, x=1.02, thickness=14,
                    tickvals=[f.spec_lo, f.target, f.spec_hi],
                ),
                xgap=0.4, ygap=0.4,
            ),
            row=r, col=c,
        )

        # 웨이퍼 경계 — 데이터의 반경을 그대로 쓴다 (하드코딩하면 인자와 어긋난다)
        fig.add_shape(type="circle", x0=-f.radius, y0=-f.radius, x1=f.radius, y1=f.radius,
                      line=dict(color="#455A64", width=1.5),
                      row=r, col=c)

        # 셀을 정사각으로 고정하지 않으면 웨이퍼가 타원으로 보인다
        fig.update_xaxes(constrain="domain", row=r, col=c)
        fig.update_yaxes(scaleanchor=f"x{'' if idx == 0 else idx + 1}",
                         scaleratio=1, constrain="domain", row=r, col=c)

    spec_frac = (f0.spec_hi - f0.target) / f0.target if f0.target else SPEC_FRAC
    fig.update_layout(
        title=dict(
            text=f"웨이퍼 파라메트릭 맵 - {value_name} "
                 f"(타깃 {f0.target:.0f}{unit} +/-{spec_frac:.0%})",
            font=dict(size=16), x=0.02,
        ),
        height=430 * rows, width=360 * cols + 140,
        paper_bgcolor="#F5F5F5", plot_bgcolor="#FFFFFF",
        font=dict(family="Arial, sans-serif", size=11),
        margin=dict(t=110, r=110),
    )
    fig.update_annotations(font=dict(size=11))
    return fig


def write_heatmap_html(fig: go.Figure, out: Path, cdn: bool = False) -> Path:
    """HTML 저장. 기본은 plotly.js 포함(오프라인 팹 PC 에서 열림), cdn=True 면 작은 파일."""
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out), include_plotlyjs="cdn" if cdn else True, full_html=True,
                   config={"displayModeBar": True, "scrollZoom": True})
    return out


def _demo_wafers() -> list[dict]:
    return [
        {"lot_id": "LOT_A", "wafer_id": "W01", "mode": "ring"},
        {"lot_id": "LOT_A", "wafer_id": "W02", "mode": "center"},
        {"lot_id": "LOT_B", "wafer_id": "W01", "mode": "random"},
        {"lot_id": "LOT_B", "wafer_id": "W02", "mode": "donut"},
        {"lot_id": "LOT_C", "wafer_id": "W01", "mode": "scratch"},
        {"lot_id": "LOT_C", "wafer_id": "W02", "mode": "clean"},
    ]


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="웨이퍼 파라메트릭 맵 인터랙티브 HTML")
    ap.add_argument("--csv", action="append", type=Path, default=[],
                    help="실측 CSV(die_x, die_y, value). 여러 번 주면 여러 웨이퍼. 없으면 합성 데모")
    ap.add_argument("--demo", action="store_true", help="합성 6장 데모 (CSV 를 주지 않으면 기본)")
    ap.add_argument("--target", type=float, default=None, help="타깃값 (CSV 입력 시; 없으면 중앙값)")
    ap.add_argument("--spec-frac", type=float, default=SPEC_FRAC, help="스펙 한계 비율 (기본 0.05)")
    ap.add_argument("--value-name", default="두께", help="값 이름 (예: 두께, CD)")
    ap.add_argument("--unit", default="Å", help="단위 (예: Å, nm)")
    ap.add_argument("--out", type=Path, default=HERE / "wafer_heatmap.html",
                    help="저장 경로 (기본: 스크립트 폴더의 wafer_heatmap.html)")
    ap.add_argument("--cdn", action="store_true",
                    help="plotly.js 를 CDN 에서 로드 (파일 작음, 인터넷 필요). 기본은 HTML 에 포함")
    args = ap.parse_args(argv)

    if args.csv:
        wafers = []
        for p in args.csv:
            f = field_from_csv(p, target=args.target, spec_frac=args.spec_frac)
            wafers.append({"lot_id": p.stem, "wafer_id": f"{f.n_die} die", "field": f, "label": "measured"})
        source = "measured CSV"
    else:
        wafers = _demo_wafers()
        source = "synthetic demo"

    fig = create_interactive_wafer_heatmap(wafers, value_name=args.value_name, unit=args.unit)
    out = write_heatmap_html(fig, args.out, cdn=args.cdn)
    print(f"저장: {out}  ({source}, plotly.js {'CDN' if args.cdn else '포함'}, {out.stat().st_size / 1e6:.1f} MB)")

    for w in wafers:
        f = w["field"] if "field" in w else create_wafer_heatmap_data(defect_mode=w["mode"])
        m = np.isfinite(f.Z)
        label = w.get("label", w.get("mode", ""))
        print(f"  {label:9s} 다이 {f.n_die:4d}  FAIL {f.n_fail:4d}  "
              f"Yield {f.yield_pct:5.1f}%  "
              f"{args.value_name} {f.Z[m].mean():6.1f} +/- {f.Z[m].std():4.1f}")
    if not args.csv:
        print("합성 데이터다. 수율은 지정한 타깃·스펙·저하량의 결과이지 공정 정보가 아니다.")
    return 0


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
