"""
sys_screenshot – DPI-aware screenshot tool for K.AI (Windows)
==============================================================
Erfasst den Bildschirm in echter physischer Auflösung (korrekt bei jedem
Skalierungsfaktor, z.B. 125 %, 150 %, 200 %).

Methode 1 (primär):  Win32 BitBlt via ctypes + SetThreadDpiAwarenessContext
                     → liefert immer physische Pixel, keine Extra-Deps nötig
Methode 2 (Fallback): PIL ImageGrab (erfordert Pillow, installiert im venv)

Benötigt:
  - Pillow (PIL)  – bereits im venv vorhanden
  - ctypes        – Python stdlib
  - win32gui      – bereits im venv (pywin32), aber NICHT benötigt hier

Kein mss, kein pyautogui nötig.
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import datetime
from pathlib import Path
from typing import Dict

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent

# ── Win32-Konstanten ───────────────────────────────────────────────────────
_SRCCOPY         = 0x00CC0020
_BI_RGB          = 0
_DIB_RGB_COLORS  = 0

# SystemMetrics
_SM_CXSCREEN          = 0
_SM_CYSCREEN          = 1
_SM_XVIRTUALSCREEN    = 76
_SM_YVIRTUALSCREEN    = 77
_SM_CXVIRTUALSCREEN   = 78
_SM_CYVIRTUALSCREEN   = 79

# DPI Awareness Context (Win10 1703 / Win11)
_DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize",          wt.DWORD),
        ("biWidth",         wt.LONG),
        ("biHeight",        wt.LONG),
        ("biPlanes",        wt.WORD),
        ("biBitCount",      wt.WORD),
        ("biCompression",   wt.DWORD),
        ("biSizeImage",     wt.DWORD),
        ("biXPelsPerMeter", wt.LONG),
        ("biYPelsPerMeter", wt.LONG),
        ("biClrUsed",       wt.DWORD),
        ("biClrImportant",  wt.DWORD),
    ]


def _default_path() -> Path:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _ROOT_DIR / "data" / "workspace" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"screenshot_{ts}.png"


def sys_screenshot(path: str = "", monitor: int = 0) -> Dict:
    """
    Erstellt einen DPI-bewussten Screenshot und speichert ihn als PNG.

    path:    Zielpfad (Standard: data/workspace/screenshots/screenshot_YYYYMMDD_HHMMSS.png)
    monitor: 0 = alle Monitore kombiniert (Virtual Screen), 1 = nur primärer Monitor
    """
    out = Path(path).expanduser() if path else _default_path()
    out.parent.mkdir(parents=True, exist_ok=True)

    # Primär: Win32 BitBlt (physische Pixel, DPI-korrekt)
    try:
        return _capture_bitblt(out, monitor)
    except Exception as exc_w32:
        # Fallback: PIL ImageGrab
        try:
            return _capture_pil(out, monitor, fallback_reason=str(exc_w32))
        except Exception as exc_pil:
            return {
                "ok":    False,
                "error": f"Win32 fehler: {exc_w32} | PIL fehler: {exc_pil}",
            }


def _capture_bitblt(out: Path, monitor: int) -> Dict:
    """
    Win32 GDI BitBlt Screenshot.

    Setzt SetThreadDpiAwarenessContext(PER_MONITOR_AWARE_V2) temporär,
    damit GetSystemMetrics physische Pixelwerte zurückgibt – unabhängig vom
    System-Skalierungsfaktor (100 %, 125 %, 150 %, 200 %, etc.).
    """
    from PIL import Image

    user32 = ctypes.windll.user32
    gdi32  = ctypes.windll.gdi32

    # Temporär auf PER_MONITOR_AWARE_V2 umschalten (physische Pixelwerte)
    old_ctx = None
    try:
        old_ctx = user32.SetThreadDpiAwarenessContext(
            _DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        )
    except Exception:
        pass  # Ältere Windows-Versionen kennen diese API nicht → weiter

    try:
        if monitor == 0:
            # Virtueller Bildschirm = alle Monitore zusammen
            left   = user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)
            top    = user32.GetSystemMetrics(_SM_YVIRTUALSCREEN)
            width  = user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)
            height = user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)
        else:
            # Nur primärer Monitor
            left, top = 0, 0
            width  = user32.GetSystemMetrics(_SM_CXSCREEN)
            height = user32.GetSystemMetrics(_SM_CYSCREEN)

        if width <= 0 or height <= 0:
            raise RuntimeError(f"Ungültige Bildschirmgröße: {width}x{height}")

        # GDI-Objekte anlegen
        hdesktop = user32.GetDesktopWindow()
        hdc_src  = user32.GetWindowDC(hdesktop)
        hdc_mem  = gdi32.CreateCompatibleDC(hdc_src)
        hbm      = gdi32.CreateCompatibleBitmap(hdc_src, width, height)
        gdi32.SelectObject(hdc_mem, hbm)

        # Bildschirminhalt in Memory-DC kopieren
        gdi32.BitBlt(hdc_mem, 0, 0, width, height, hdc_src, left, top, _SRCCOPY)

        # BITMAPINFOHEADER für GetDIBits konfigurieren
        bmi            = _BITMAPINFOHEADER()
        bmi.biSize     = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.biWidth    = width
        bmi.biHeight   = -height  # negativ = Top-Down (normale Scanline-Reihenfolge)
        bmi.biPlanes   = 1
        bmi.biBitCount = 32       # BGRA
        bmi.biCompression = _BI_RGB

        # Pixel-Buffer befüllen
        buf_size = width * height * 4
        buf = ctypes.create_string_buffer(buf_size)
        gdi32.GetDIBits(hdc_mem, hbm, 0, height, buf, ctypes.byref(bmi), _DIB_RGB_COLORS)

        # GDI aufräumen
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(hdesktop, hdc_src)

    finally:
        # DPI-Context zurücksetzen
        if old_ctx is not None:
            try:
                user32.SetThreadDpiAwarenessContext(old_ctx)
            except Exception:
                pass

    # BGRA → RGB → PNG speichern
    img = Image.frombuffer("RGBA", (width, height), buf.raw, "raw", "BGRA", 0, 1)
    img = img.convert("RGB")
    img.save(str(out), "PNG", optimize=False)

    file_size_kb = round(out.stat().st_size / 1024, 1)
    return {
        "ok":          True,
        "path":        str(out),
        "width":       width,
        "height":      height,
        "size_kb":     file_size_kb,
        "method":      "Win32_BitBlt",
    }


def _capture_pil(out: Path, monitor: int, fallback_reason: str = "") -> Dict:
    """Fallback via PIL ImageGrab."""
    from PIL import ImageGrab
    img = ImageGrab.grab(all_screens=(monitor == 0))
    img = img.convert("RGB")
    img.save(str(out), "PNG")
    file_size_kb = round(out.stat().st_size / 1024, 1)
    result: Dict = {
        "ok":      True,
        "path":    str(out),
        "width":   img.width,
        "height":  img.height,
        "size_kb": file_size_kb,
        "method":  "PIL_ImageGrab",
    }
    if fallback_reason:
        result["win32_fallback_reason"] = fallback_reason
    return result


# Rückwärtskompatibilität: alter Stub-Name bleibt erreichbar
take_screenshot_stub = sys_screenshot
