import json
import os
from pathlib import Path


def _load_config(config_path: Path) -> dict:
    try:
        raw = config_path.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _workspace_root(project_root: Path, cfg: dict) -> Path:
    ws = str(cfg.get("workspace", "data\\workspace") or "data\\workspace")
    return (project_root / ws).resolve()


def _model_size(cfg: dict) -> str:
    size = str(cfg.get("audio", {}).get("sst_model_size", "") or "").strip()
    return size if size else "base"


def _download_model(model_size: str, models_dir: Path) -> None:
    try:
        from faster_whisper import WhisperModel
    except Exception as exc:
        raise RuntimeError(f"faster-whisper nicht installiert: {exc}") from exc

    models_dir.mkdir(parents=True, exist_ok=True)
    # Trigger download into models_dir
    _ = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=str(models_dir))


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    cfg = _load_config(project_root / "config.json")
    ws_root = _workspace_root(project_root, cfg)
    models_dir = ws_root / "models" / "whisper"
    model_size = _model_size(cfg)
    _download_model(model_size, models_dir)
    print(f"ok: downloaded whisper model '{model_size}' to {models_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
