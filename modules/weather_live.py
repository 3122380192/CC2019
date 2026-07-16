"""Theme theo thời tiết thật — Bắc Ninh (Open-Meteo, không API key)."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

# Bắc Ninh city (~ trung tâm)
BAC_NINH_LAT = 21.1861
BAC_NINH_LON = 106.0763
LOCATION_NAME = "Bắc Ninh"

OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={BAC_NINH_LAT}&longitude={BAC_NINH_LON}"
    "&current=temperature_2m,weather_code,is_day,precipitation,"
    "cloud_cover,wind_speed_10m,relative_humidity_2m"
    "&timezone=Asia%2FBangkok"
)

# WMO code → mô tả ngắn tiếng Việt
_CODE_VI: dict[int, str] = {
    0: "Trời quang",
    1: "Ít mây",
    2: "Mây rải",
    3: "Nhiều mây",
    45: "Sương mù",
    48: "Sương đóng băng",
    51: "Mưa phùn nhẹ",
    53: "Mưa phùn",
    55: "Mưa phùn dày",
    56: "Mưa phùn lạnh",
    57: "Mưa phùn lạnh dày",
    61: "Mưa nhẹ",
    63: "Mưa vừa",
    65: "Mưa to",
    66: "Mưa lạnh",
    67: "Mưa lạnh to",
    71: "Tuyết nhẹ",
    73: "Tuyết vừa",
    75: "Tuyết dày",
    77: "Hạt tuyết",
    80: "Mưa rào nhẹ",
    81: "Mưa rào",
    82: "Mưa rào mạnh",
    85: "Tuyết rào nhẹ",
    86: "Tuyết rào",
    95: "Dông",
    96: "Dông + mưa đá nhẹ",
    99: "Dông + mưa đá",
}


@dataclass
class WeatherSnapshot:
    ok: bool = False
    temp_c: float | None = None
    code: int = 0
    is_day: bool = True
    precip_mm: float = 0.0
    cloud_pct: int = 0
    wind_kmh: float = 0.0
    humidity: int | None = None
    desc: str = "—"
    theme_id: str = "midnight"
    theme_name: str = "—"
    fetched_at: float = 0.0
    error: str = ""
    raw: dict = field(default_factory=dict)

    def short_label(self) -> str:
        if not self.ok:
            return "BN:—"
        t = f"{self.temp_c:.0f}°" if self.temp_c is not None else "?"
        return f"BN {t} {self.desc}"

    def detail_label(self) -> str:
        if not self.ok:
            return f"Bắc Ninh: lỗi ({self.error or '—'})"
        parts = [
            f"Bắc Ninh {self.temp_c:.1f}°C" if self.temp_c is not None else "Bắc Ninh",
            self.desc,
            f"mây {self.cloud_pct}%",
            f"gió {self.wind_kmh:.0f}km/h",
        ]
        if self.humidity is not None:
            parts.append(f"Độ ẩm {self.humidity}%")
        if self.precip_mm > 0:
            parts.append(f"mưa {self.precip_mm:.1f}mm")
        return " · ".join(parts)


def weather_code_desc(code: int) -> str:
    if code in _CODE_VI:
        return _CODE_VI[code]
    # nearest known
    for k in sorted(_CODE_VI.keys(), key=lambda x: abs(x - code)):
        if abs(k - code) <= 2:
            return _CODE_VI[k]
    return f"Mã {code}"


def map_weather_to_theme(
    code: int,
    *,
    is_day: bool = True,
    wind_kmh: float = 0.0,
    cloud_pct: int = 0,
    hour: int | None = None,
) -> str:
    """Chọn theme weather có sẵn theo điều kiện thật."""
    if hour is None:
        hour = datetime.now().hour

    # Dông / sấm sét
    if code in (95, 96, 97, 98, 99):
        return "lightning"

    # Tuyết (hiếm ở BN nhưng map đủ)
    if code in (71, 72, 73, 74, 75, 76, 77, 85, 86):
        return "snow"

    # Mưa / mưa rào / phùn
    if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        if code in (65, 67, 82) or wind_kmh >= 35:
            return "storm"
        return "rain"

    # Sương mù
    if code in (45, 48):
        return "fog"

    # Gió mạnh (không dông)
    if wind_kmh >= 40:
        return "wind"

    # Nhiều mây / u ám
    if code == 3 or cloud_pct >= 85:
        if not is_day:
            return "storm"
        return "fog" if cloud_pct >= 95 else "storm"

    # Ít mây / quang
    if code in (0, 1, 2):
        if not is_day:
            return "aurora_night"
        # bình minh / hoàng hôn theo giờ địa phương
        if 5 <= hour < 8:
            return "sunrise"
        if 16 <= hour < 19:
            return "sunset_sky"
        if wind_kmh >= 22:
            return "wind"
        # trời quang ban ngày → bình minh (ấm, sáng)
        return "sunrise" if hour < 11 else "sunset_sky" if hour >= 16 else "wind"

    # fallback
    return "storm" if not is_day else "fog"


def fetch_bac_ninh_weather(timeout: float = 8.0) -> WeatherSnapshot:
    snap = WeatherSnapshot(fetched_at=time.time())
    try:
        req = urllib.request.Request(
            OPEN_METEO_URL,
            headers={"User-Agent": "ACC2019-Weather/1.0 (Bac Ninh theme)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.URLError as exc:
        snap.error = str(exc.reason if hasattr(exc, "reason") else exc)
        return snap
    except Exception as exc:
        snap.error = str(exc)[:80]
        return snap

    cur = data.get("current") or {}
    try:
        code = int(cur.get("weather_code") or 0)
    except (TypeError, ValueError):
        code = 0
    try:
        temp = float(cur["temperature_2m"]) if cur.get("temperature_2m") is not None else None
    except (TypeError, ValueError):
        temp = None
    is_day = bool(int(cur.get("is_day") or 0))
    try:
        precip = float(cur.get("precipitation") or 0)
    except (TypeError, ValueError):
        precip = 0.0
    try:
        cloud = int(cur.get("cloud_cover") or 0)
    except (TypeError, ValueError):
        cloud = 0
    try:
        wind = float(cur.get("wind_speed_10m") or 0)
    except (TypeError, ValueError):
        wind = 0.0
    hum = cur.get("relative_humidity_2m")
    try:
        humidity = int(hum) if hum is not None else None
    except (TypeError, ValueError):
        humidity = None

    theme_id = map_weather_to_theme(
        code, is_day=is_day, wind_kmh=wind, cloud_pct=cloud,
    )
    from modules.theme_manager import THEMES
    theme_name = THEMES.get(theme_id, {}).get("name", theme_id)

    snap.ok = True
    snap.temp_c = temp
    snap.code = code
    snap.is_day = is_day
    snap.precip_mm = precip
    snap.cloud_pct = cloud
    snap.wind_kmh = wind
    snap.humidity = humidity
    snap.desc = weather_code_desc(code)
    snap.theme_id = theme_id
    snap.theme_name = theme_name
    snap.raw = cur
    return snap


class WeatherThemeService:
    """Background poll thời tiết Bắc Ninh → gợi ý / áp theme."""

    def __init__(
        self,
        *,
        interval_sec: int = 900,
        enabled: bool = False,
        on_update: Callable[[WeatherSnapshot], None] | None = None,
    ) -> None:
        self.interval_sec = max(120, int(interval_sec))
        self.enabled = bool(enabled)
        self.on_update = on_update
        self.last: WeatherSnapshot = WeatherSnapshot()
        self._running = True
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._force = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="weather-bn")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._force.set()

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        if self.enabled:
            self.refresh_now()

    def set_interval_min(self, minutes: int) -> None:
        self.interval_sec = max(120, int(minutes) * 60)

    def refresh_now(self) -> None:
        self._force.set()

    def _loop(self) -> None:
        # fetch ngay lần đầu nếu enabled
        first = True
        while self._running:
            if self.enabled or first:
                first = False
                if self.enabled or not self.last.ok:
                    snap = fetch_bac_ninh_weather()
                    with self._lock:
                        self.last = snap
                    if self.on_update:
                        try:
                            self.on_update(snap)
                        except Exception:
                            pass
            self._force.clear()
            # chờ interval hoặc force
            self._force.wait(timeout=self.interval_sec)

    def get_last(self) -> WeatherSnapshot:
        with self._lock:
            return self.last
