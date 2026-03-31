from __future__ import annotations

try:
    import edge_tts
    _TTS_AVAILABLE = True
except ImportError:
    _TTS_AVAILABLE = False

try:
    from faster_whisper import WhisperModel
    _SST_AVAILABLE = True
except ImportError:
    _SST_AVAILABLE = False


def tts_available() -> bool:
    return _TTS_AVAILABLE


def sst_available() -> bool:
    return _SST_AVAILABLE


# wrap callables in this module where present
try:
    from app.tools.wrapper import validated_tool
    for _n, _v in list(globals().items()):
        if callable(_v) and getattr(_v, "__module__", "").endswith("app.tools.tts"):
            globals()[_n] = validated_tool(f"tts.{_n}", None)(_v)
except Exception:
    pass
