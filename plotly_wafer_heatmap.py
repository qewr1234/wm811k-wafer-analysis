# plotly_wafer_heatmap.py
# Plotly go.Heatmap 기반 웨이퍼 파라메트릭 맵
#
# 원본 대비 수정 사항
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
#
# 주의: 합성 데이터다. 아래 임계값과 감소량을 직접 지정했으므로
#       여기서 나오는 수율은 공정에 대한 정보가 아니다.

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DEFECT_MODES = ("ring", "center", "donut", "edge_loc", "scratch", "random", "clean")

# 측정 파라미터 기본값 — process_data_generator의 CVD 타깃과 맞춤
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
                      spec_lo=target - tol, spec_hi=target + tol)


def create_interactive_wafer_heatmap(
    lot_data: list[dict],
    value_name: str = "두께",
    unit: str = "Å",
    cols_max: int = 3,
) -> go.Figure:
    """여러 웨이퍼의 파라메트릭 맵을 서브플롯으로 구성."""
    n = len(lot_data)
    cols = min(cols_max, n)
    rows = (n + cols - 1) // cols

    fields, titles = [], []
    for i, d in enumerate(lot_data):
        f = create_wafer_heatmap_data(
            defect_mode=d.get("mode", "random"),
            seed=d.get("seed", 2024 + i),      # 웨이퍼마다 다른 시드
        )
        fields.append(f)
        titles.append(
            f"{d['lot_id']} / {d['wafer_id']} ({d.get('mode', 'random')})<br>"
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

        # 웨이퍼 경계
        fig.add_shape(type="circle", x0=-14.5, y0=-14.5, x1=14.5, y1=14.5,
                      line=dict(color="#455A64", width=1.5),
                      row=r, col=c)

        # 셀을 정사각으로 고정하지 않으면 웨이퍼가 타원으로 보인다
        fig.update_xaxes(constrain="domain", row=r, col=c)
        fig.update_yaxes(scaleanchor=f"x{'' if idx == 0 else idx + 1}",
                         scaleratio=1, constrain="domain", row=r, col=c)

    fig.update_layout(
        title=dict(
            text=f"웨이퍼 파라메트릭 맵 — {value_name} "
                 f"(타깃 {f0.target:.0f}{unit} ±{SPEC_FRAC:.0%})",
            font=dict(size=16), x=0.02,
        ),
        height=430 * rows, width=360 * cols + 140,
        paper_bgcolor="#F5F5F5", plot_bgcolor="#FFFFFF",
        font=dict(family="Arial, sans-serif", size=11),
        margin=dict(t=110, r=110),
    )
    fig.update_annotations(font=dict(size=11))
    return fig


if __name__ == "__main__":
    wafers = [
        {"lot_id": "LOT_A", "wafer_id": "W01", "mode": "ring"},
        {"lot_id": "LOT_A", "wafer_id": "W02", "mode": "center"},
        {"lot_id": "LOT_B", "wafer_id": "W01", "mode": "random"},
        {"lot_id": "LOT_B", "wafer_id": "W02", "mode": "donut"},
        {"lot_id": "LOT_C", "wafer_id": "W01", "mode": "scratch"},
        {"lot_id": "LOT_C", "wafer_id": "W02", "mode": "clean"},
    ]

    fig = create_interactive_wafer_heatmap(wafers)
    fig.write_html("wafer_heatmap.html", include_plotlyjs="cdn", full_html=True,
                   config={"displayModeBar": True, "scrollZoom": True})
    print("저장: wafer_heatmap.html")

    for w in wafers:
        f = create_wafer_heatmap_data(defect_mode=w["mode"])
        m = np.isfinite(f.Z)
        print(f"  {w['mode']:9s} 다이 {f.n_die:4d}  FAIL {f.n_fail:4d}  "
              f"Yield {f.yield_pct:5.1f}%  "
              f"두께 {f.Z[m].mean():6.1f} ± {f.Z[m].std():4.1f}")
