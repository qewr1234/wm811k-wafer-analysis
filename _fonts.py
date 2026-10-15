# _fonts.py
# matplotlib 한글 폰트 설정 - 동봉 폰트 우선, 시스템 폰트 폴백, 없으면 경고 한 번
#
# 배경
#   matplotlib 기본 폰트(DejaVu Sans)에는 한글 글리프가 없다. 그대로 그리면 PDF·PNG 의
#   한글이 전부 빈 사각형으로 나오고 'Glyph ... missing from font' 경고가 글자 수만큼
#   쏟아진다. GitHub Actions ubuntu 러너, 일부 리눅스 PC, 폰트를 설치하지 않은 Windows
#   서버가 그런 환경이다. 고객이나 본사에 보내는 리포트가 환경에 따라 깨지면 안 된다.
#
# 무엇을 하나
#   setup_korean_font() 가 아래 순서로 폰트를 고르고 rcParams 를 설정한다.
#     (a) 동봉 폰트 docs/fonts/NanumGothic-Regular.ttf (SIL OFL 1.1) 가 있으면
#         fontManager.addfont 로 등록하고 font.family 를 폴백 리스트로 둔다.
#     (b) 없으면 시스템 후보(Malgun Gothic, AppleGothic, NanumGothic, ...)를 찾는다.
#     (c) 그래도 없으면 None 을 돌려주고 stderr 에 설치 안내를 한 번만 적는다.
#         이때 'Glyph missing' 경고는 warnings.filterwarnings("once") 로 한 번만 요약한다.
#   has_korean_font() 는 호출 측(배치 리포트 --lang 자동 전환 등)이 쓰는 bool.
#   결과는 프로세스 안에서 캐시된다(force=True 로 다시 탐색).
#
# 왜
#   폰트 설정이 batch_wafer_report 안에만 있어 wm811k_spc 가 그것을 import 하고,
#   테스트는 폰트 없이 그려 경고가 났다. 한 모듈로 모아 모든 그리기 진입점이 먼저 부른다.
#
# 한계
#   - 동봉 폰트는 Regular 한 벌이다. fontweight="bold" 는 같은 Regular 글리프로 그려지며,
#     matplotlib 가 그때 남기는 'Failed to find font weight bold' 로그는 이 모듈이 거른다.
#   - rcParams['font.family'] 의 폴백 리스트는 실제로 설치된 패밀리만 남긴다. 설치되지
#     않은 이름을 리스트에 두면 matplotlib 가 텍스트를 그릴 때마다 'Font family not
#     found' 를 로그에 남기기 때문이다.
#   - 폰트 캐시가 오래됐을 때 addfont 가 실패하면 시스템 폰트 탐색으로 넘어간다.
#
# 사용법
#   from _fonts import setup_korean_font, has_korean_font
#   name = setup_korean_font()      # 'NanumGothic' / 'Malgun Gothic' / ... / None
#   python _fonts.py                # 현재 환경에서 어떤 폰트가 잡히는지 출력

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import matplotlib
from matplotlib import font_manager
from matplotlib.font_manager import FontProperties, findfont

HERE = Path(__file__).resolve().parent
BUNDLED_FONT = HERE / "docs" / "fonts" / "NanumGothic-Regular.ttf"
BUNDLED_FAMILY = "NanumGothic"

# 동봉 폰트가 있을 때의 폴백 순서. 설치된 것만 rcParams 에 남긴다.
FALLBACK_FAMILIES = ["NanumGothic", "Malgun Gothic", "AppleGothic",
                     "Noto Sans CJK KR", "DejaVu Sans"]
# 동봉 폰트가 없을 때 찾아보는 시스템 폰트. Windows / macOS / Linux 순.
SYSTEM_CANDIDATES = ["Malgun Gothic", "AppleGothic", "NanumGothic", "NanumBarunGothic",
                     "Noto Sans CJK KR", "Noto Sans KR", "WenQuanYi Zen Hei", "UnDotum"]

INSTALL_HINT = (
    "[경고] 한글 폰트를 찾지 못했다. 한글 라벨이 빈 사각형으로 그려진다.\n"
    "  - 동봉 폰트: docs/fonts/NanumGothic-Regular.ttf 가 저장소에 있는지 확인 (git clone 시 포함)\n"
    "  - Ubuntu/Debian: sudo apt-get install -y fonts-nanum\n"
    "  - macOS: brew install --cask font-nanum-gothic\n"
    "  - Windows: 'Malgun Gothic' 이 기본 설치되어 있으므로 보통 이 경고가 나지 않는다\n"
    "  설치 후 matplotlib 폰트 캐시(~/.cache/matplotlib)를 지우고 다시 실행한다."
)

GLYPH_WARNING_RE = r"Glyph \d+ .*missing from font"

_cache: dict[str, object] = {"resolved": False, "font": None, "warned": False}


class _DropWeightWarning(logging.Filter):
    """동봉 Regular 한 벌로 bold 를 그릴 때 나오는 matplotlib 로그를 거른다."""

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not (msg.startswith("findfont: Failed to find font weight")
                    and BUNDLED_FAMILY in msg)


_weight_filter = _DropWeightWarning()


def _font_available(family: str) -> bool:
    """패밀리 이름으로 실제 파일이 잡히는지. DejaVu 로 떨어지는 경우는 미발견으로 본다."""
    try:
        path = findfont(FontProperties(family=family), fallback_to_default=False)
    except Exception:
        return False
    if not path:
        return False
    name = Path(path).name.lower()
    return not (name.startswith("dejavusans") and family.lower() != "dejavu sans")


def _register_bundled() -> str | None:
    if not BUNDLED_FONT.is_file():
        return None
    try:
        font_manager.fontManager.addfont(str(BUNDLED_FONT))
        family = FontProperties(fname=str(BUNDLED_FONT)).get_name()
    except Exception:
        return None
    if not _font_available(family):
        return None
    return family


def _find_system() -> str | None:
    for name in SYSTEM_CANDIDATES:
        if _font_available(name):
            return name
    return None


def _apply(primary: str, fallbacks: list[str]) -> None:
    families = [primary] + [f for f in fallbacks if f != primary and _font_available(f)]
    if "DejaVu Sans" not in families:
        families.append("DejaVu Sans")
    matplotlib.rcParams["font.family"] = families
    matplotlib.rcParams["axes.unicode_minus"] = False


def setup_korean_font(force: bool = False) -> str | None:
    """한글 폰트를 rcParams 에 설정하고 폰트 패밀리 이름을 돌려준다. 없으면 None.

    동봉 폰트 -> 시스템 폰트 -> None 순서. 결과는 캐시되며 force=True 면 다시 찾는다.
    None 일 때는 stderr 에 설치 안내를 한 번 적고, 'Glyph missing' 경고를 한 번으로 줄인다.
    """
    if _cache["resolved"] and not force:
        return _cache["font"]  # type: ignore[return-value]

    log = logging.getLogger("matplotlib.font_manager")
    font = _register_bundled()
    if font:
        log.addFilter(_weight_filter)
        _apply(font, FALLBACK_FAMILIES)
    else:
        log.removeFilter(_weight_filter)
        font = _find_system()
        if font:
            _apply(font, FALLBACK_FAMILIES)
        else:
            matplotlib.rcParams["axes.unicode_minus"] = False
            # 글자마다 나오는 경고를 한 번으로. 폰트가 있으면 이 필터는 걸지 않는다.
            warnings.filterwarnings("once", message=GLYPH_WARNING_RE, category=UserWarning)
            if not _cache["warned"]:
                print(INSTALL_HINT, file=sys.stderr)
                _cache["warned"] = True

    _cache["resolved"] = True
    _cache["font"] = font
    return font


def has_korean_font() -> bool:
    """한글을 그릴 폰트가 잡혀 있는가. 아직 setup 전이면 setup 을 먼저 한다."""
    return setup_korean_font() is not None


if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    name = setup_korean_font(force=True)
    print(f"동봉 폰트 파일: {BUNDLED_FONT} ({'있음' if BUNDLED_FONT.is_file() else '없음'})")
    print(f"선택된 폰트: {name}")
    print(f"font.family: {matplotlib.rcParams['font.family']}")
