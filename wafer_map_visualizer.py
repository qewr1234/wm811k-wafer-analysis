# wafer_map_visualizer.py
# 웨이퍼 맵 생성 및 시각화 도구
#
# 원본 대비 수정 사항
#   [버그] 다이 사각형이 0.5mm 밀려 그려지던 문제 (축소 후 재중심화 누락)
#   [버그] 불량 패턴 임계값이 300mm 하드코딩 → 다른 직경에서 불량 0개
#   [버그] plot의 wafer_radius가 데이터와 독립 → 직경 변경 시 불일치
#   [버그] df.attrs 의존 → pandas 연산 후 유실되어 수율이 조용히 0% 표시
#   [버그] 원 포함 판정에 half 사용 → 모서리 기준(half*√2)이 정확
#   [개선] iterrows + add_patch → PatchCollection (다이 수 증가 시 필수)
#   [개선] 전역 np.random.seed → default_rng
#   [개선] noise 파라미터 추가 (실제 데이터는 경계가 깨끗하지 않음)
#   [개선] WM-811K 라벨에 맞춰 donut, edge_loc 패턴 추가

from __future__ import annotations

from dataclasses import dataclass

import matplotlib.patches as mpatches
import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.collections import PatchCollection
from matplotlib.patches import Circle, Polygon, Rectangle

DEFECT_MODES = ("ring", "center", "scratch", "random", "donut", "edge_loc", "clean")

PASS_COLOR = "#4CAF50"
FAIL_COLOR = "#F44336"


@dataclass
class WaferGeometry:
    """DataFrame 연산에서 유실되지 않도록 기하 정보를 별도로 보관."""
    wafer_radius_mm: float
    die_size_mm: float
    edge_exclusion_mm: float
    defect_mode: str = "unknown"

    @property
    def effective_radius_mm(self) -> float:
        return self.wafer_radius_mm - self.edge_exclusion_mm


# ──────────────────────────────────────────
# 1. 샘플 웨이퍼 데이터 생성
# ──────────────────────────────────────────
def generate_sample_wafer_data(
    wafer_diameter_mm: float = 300.0,
    die_size_mm: float = 10.0,
    edge_exclusion_mm: float = 3.0,
    defect_mode: str = "ring",
    noise: float = 0.0,
    seed: int = 42,
) -> pd.DataFrame:
    """샘플 웨이퍼 다이 데이터 생성.

    Parameters
    ----------
    wafer_diameter_mm : 웨이퍼 직경 (mm)
    die_size_mm       : 다이 크기 (정사각형 가정, mm)
    edge_exclusion_mm : 엣지 제외 영역 (mm)
    defect_mode       : DEFECT_MODES 중 하나
    noise             : 각 다이의 상태를 뒤집을 확률 (0~1).
                        실제 결함은 경계가 불규칙하므로 0.02~0.05 권장.
    seed              : 난수 시드

    Returns
    -------
    pd.DataFrame
        die_x, die_y, radius, angle_deg, status 컬럼.
        기하 정보는 df.attrs['geometry']에 담기지만 유실될 수 있으므로,
        plot/classify 단계에서는 데이터로부터 재계산하거나 인자로 전달한다.

    Notes
    -----
    이 함수의 출력은 합성 데이터다. 여기서 나오는 수율이나 패턴은
    아래 임계값을 그대로 반영한 결과이며 공정에 대한 정보를 담지 않는다.
    렌더러/분류기 검증용으로만 사용하고, 성능 주장은 실측 데이터(WM-811K)로 할 것.
    """
    if defect_mode not in DEFECT_MODES:
        raise ValueError(f"defect_mode must be one of {DEFECT_MODES}, got {defect_mode!r}")
    if not 0.0 <= noise <= 1.0:
        raise ValueError(f"noise must be in [0, 1], got {noise}")

    rng = np.random.default_rng(seed)

    radius = wafer_diameter_mm / 2.0
    r_eff = radius - edge_exclusion_mm

    # 격자 좌표 — 원점을 다이 중심에 맞춘다
    n_half = int(np.floor(radius / die_size_mm))
    coords = np.arange(-n_half, n_half + 1) * die_size_mm

    gx, gy = np.meshgrid(coords, coords)
    gx, gy = gx.ravel(), gy.ravel()
    dist = np.hypot(gx, gy)

    # 다이 전체가 유효 영역 안에 들어오는지 판정.
    # 중심에서 가장 먼 점은 모서리이므로 half * √2 를 쓴다.
    corner = die_size_mm / 2.0 * np.sqrt(2.0)
    inside = dist + corner <= r_eff

    df = pd.DataFrame({
        "die_x": gx[inside],
        "die_y": gy[inside],
        "radius": dist[inside],
        "angle_deg": np.degrees(np.arctan2(gy[inside], gx[inside])),
    })
    if df.empty:
        raise ValueError(
            f"유효 다이가 없다. die_size_mm({die_size_mm})가 "
            f"유효 반경({r_eff:.1f}mm)에 비해 너무 크다."
        )

    # ── 불량 패턴 ──
    # 모든 임계값은 유효 반경에 대한 비율. 직경을 바꿔도 동일한 형태가 나온다.
    r = df["radius"].to_numpy()
    x, y = df["die_x"].to_numpy(), df["die_y"].to_numpy()
    ang = df["angle_deg"].to_numpy()

    if defect_mode == "ring":
        fail = r >= 0.82 * r_eff                      # 엣지 링
    elif defect_mode == "center":
        fail = r <= 0.22 * r_eff                      # 중심부
    elif defect_mode == "donut":
        fail = (r >= 0.40 * r_eff) & (r <= 0.62 * r_eff)   # 중간 반경 고리
    elif defect_mode == "edge_loc":
        fail = (r >= 0.80 * r_eff) & (np.abs(ang - 45.0) <= 35.0)  # 엣지 일부 구간
    elif defect_mode == "scratch":
        # 중심을 지나는 얇은 선. 폭은 다이 2개 수준.
        theta = np.radians(30.0)
        perp = np.abs(-np.sin(theta) * x + np.cos(theta) * y)
        fail = perp <= die_size_mm
    elif defect_mode == "random":
        fail = rng.random(len(df)) < 0.05
    else:  # clean
        fail = np.zeros(len(df), dtype=bool)

    # 경계를 흐트러뜨린다. 실제 결함은 링 안에 정상 다이가 섞여 있다.
    if noise > 0:
        flip = rng.random(len(df)) < noise
        fail = np.where(flip, ~fail, fail)

    df["status"] = np.where(fail, "FAIL", "PASS")

    df.attrs["geometry"] = WaferGeometry(
        wafer_radius_mm=radius,
        die_size_mm=die_size_mm,
        edge_exclusion_mm=edge_exclusion_mm,
        defect_mode=defect_mode,
    )
    return df


# ──────────────────────────────────────────
# 2. 웨이퍼 맵 시각화
# ──────────────────────────────────────────
def infer_geometry(df: pd.DataFrame) -> WaferGeometry:
    """DataFrame에서 기하 정보를 복원한다.

    attrs가 살아있으면 그것을 쓰고, 유실된 경우 좌표에서 추정한다.
    WM-811K처럼 외부에서 들어온 데이터에도 사용할 수 있다.
    """
    geom = df.attrs.get("geometry")
    if isinstance(geom, WaferGeometry):
        return geom

    xs = np.sort(df["die_x"].unique())
    die = float(np.min(np.diff(xs))) if len(xs) > 1 else 1.0
    r_eff = float(df["radius"].max()) + die / 2.0 * np.sqrt(2.0)
    return WaferGeometry(
        wafer_radius_mm=r_eff,          # 엣지 제외 영역은 알 수 없음
        die_size_mm=die,
        edge_exclusion_mm=0.0,
        defect_mode="unknown",
    )


def plot_wafer_map(
    df: pd.DataFrame,
    lot_id: str = "LOT_001",
    wafer_id: str = "W01",
    geometry: WaferGeometry | None = None,
    ax: plt.Axes | None = None,
    show_die_coords: bool = False,
    fill_ratio: float = 0.9,
    pattern_label: str | None = None,
) -> plt.Axes:
    """웨이퍼 맵을 Matplotlib Axes에 그린다.

    geometry를 넘기지 않으면 df에서 추정한다.
    수율은 항상 df에서 직접 계산하므로 attrs 유실과 무관하다.
    """
    geom = geometry or infer_geometry(df)
    R = geom.wafer_radius_mm
    die = geom.die_size_mm

    if ax is None:
        _, ax = plt.subplots(figsize=(9, 9))

    # ── 다이 렌더링 ──
    # 축소 후 재중심화. (x - die/2, y - die/2) + 축소 크기 조합은
    # 사각형을 (die*(1-fill_ratio)/2) 만큼 좌하단으로 밀어버린다.
    size = die * fill_ratio
    half = size / 2.0
    is_fail = (df["status"] == "FAIL").to_numpy()

    patches = [
        Rectangle((px - half, py - half), size, size,
                  facecolor=FAIL_COLOR if f else PASS_COLOR)
        for px, py, f in zip(df["die_x"], df["die_y"], is_fail)
    ]
    ax.add_collection(PatchCollection(
        patches, match_original=True,
        edgecolor="white", linewidth=0.3, alpha=0.85,
    ))

    if show_die_coords and len(df) < 200:
        for px, py in zip(df["die_x"], df["die_y"]):
            ax.text(px, py, f"({int(px)},\n{int(py)})",
                    fontsize=4, ha="center", va="center", color="white",
                    path_effects=[pe.withStroke(linewidth=0.5, foreground="black")])

    # ── 웨이퍼 외곽 / 엣지 제외 / 노치 ──
    ax.add_patch(Circle((0, 0), R, fill=False,
                        edgecolor="#455A64", linewidth=2.5))
    if geom.edge_exclusion_mm > 0:
        ax.add_patch(Circle((0, 0), geom.effective_radius_mm, fill=False,
                            edgecolor="#B0BEC5", linewidth=1.0, linestyle="--"))

    notch_w, notch_h = R * 0.033, R * 0.053
    ax.add_patch(Polygon(
        [[-notch_w, -R], [0, -R - notch_h], [notch_w, -R]],
        closed=True, facecolor="#455A64", edgecolor="#455A64",
    ))

    ax.set_xlim(-R * 1.15, R * 1.15)
    ax.set_ylim(-R * 1.25, R * 1.15)
    ax.set_aspect("equal")
    ax.set_facecolor("#ECEFF1")
    ax.grid(False)
    ax.tick_params(labelsize=8)
    ax.set_xlabel("X position (mm)", fontsize=9)
    ax.set_ylabel("Y position (mm)", fontsize=9)

    # ── 수율은 df에서 직접 계산 ──
    total = len(df)
    fail_n = int(is_fail.sum())
    pass_n = total - fail_n
    yield_pct = pass_n / total * 100 if total else 0.0
    label = pattern_label or geom.defect_mode

    ax.set_title(
        f"Lot: {lot_id}  |  Wafer: {wafer_id}\n"
        f"Yield: {yield_pct:.1f}%  |  Total: {total}  |  "
        f"FAIL: {fail_n}  |  Pattern: {label.upper()}",
        fontsize=10, fontweight="bold", pad=12,
    )
    ax.legend(
        handles=[
            mpatches.Patch(facecolor=PASS_COLOR, edgecolor="white", label=f"PASS ({pass_n})"),
            mpatches.Patch(facecolor=FAIL_COLOR, edgecolor="white", label=f"FAIL ({fail_n})"),
        ],
        loc="lower center", bbox_to_anchor=(0.5, -0.13), ncol=2,
        fontsize=9, framealpha=0.9, edgecolor="#B0BEC5",
    )
    return ax


# ──────────────────────────────────────────
# 3. WM-811K 변환 (실측 데이터 연결용)
# ──────────────────────────────────────────
def wafermap_to_df(wmap: np.ndarray, die_size_mm: float = 10.0) -> pd.DataFrame:
    """WM-811K의 2D waferMap 배열을 이 모듈의 DataFrame 형식으로 변환.

    셀 값 규약: 0 = 다이 없음(웨이퍼 밖), 1 = 정상, 2 = 불량.

    WM-811K는 맵 차원이 통일되어 있지 않고 실제 mm 크기도 알 수 없다.
    die_size_mm은 시각화 축 스케일용 임의값이며, 반경 기반 분석은
    비율로만 해석해야 한다.
    """
    wmap = np.asarray(wmap)
    if wmap.ndim != 2:
        raise ValueError(f"waferMap must be 2D, got shape {wmap.shape}")

    h, w = wmap.shape
    ys, xs = np.nonzero(wmap > 0)
    cx, cy = (w - 1) / 2.0, (h - 1) / 2.0

    dx = (xs - cx) * die_size_mm
    dy = (cy - ys) * die_size_mm        # 배열 행 인덱스는 아래로 증가

    df = pd.DataFrame({
        "die_x": dx,
        "die_y": dy,
        "radius": np.hypot(dx, dy),
        "angle_deg": np.degrees(np.arctan2(dy, dx)),
        "status": np.where(wmap[ys, xs] == 2, "FAIL", "PASS"),
    })
    df.attrs["geometry"] = infer_geometry(df)
    return df


# ──────────────────────────────────────────
if __name__ == "__main__":
    # 노이즈 없는 버전과 있는 버전을 비교. 오른쪽이 실제 데이터에 가깝다.
    modes = ["ring", "center", "scratch", "donut"]
    fig, axes = plt.subplots(2, 4, figsize=(30, 16))

    for col, mode in enumerate(modes):
        for row, nz in enumerate([0.0, 0.03]):
            df = generate_sample_wafer_data(defect_mode=mode, noise=nz)
            plot_wafer_map(
                df, lot_id="SYNTHETIC", wafer_id=f"{mode[:3].upper()}",
                ax=axes[row, col],
                pattern_label=f"{mode} (noise={nz})",
            )

    plt.tight_layout()
    plt.savefig("wafer_map_grid.png", dpi=120, bbox_inches="tight")
    print("저장 완료: wafer_map_grid.png")

    # 200mm 웨이퍼에서도 동작하는지 확인 (원본은 여기서 불량 0개가 나왔다)
    df200 = generate_sample_wafer_data(wafer_diameter_mm=200.0, die_size_mm=8.0,
                                       defect_mode="ring")
    n_fail = (df200["status"] == "FAIL").sum()
    print(f"200mm 웨이퍼: 다이 {len(df200)}개, FAIL {n_fail}개 "
          f"({'OK' if n_fail > 0 else 'FAILED — 임계값 확인 필요'})")

    plt.show()
