import asyncio
import logging
import os
import threading
from pathlib import Path
from typing import Any, Optional

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None

try:
    import edge_tts
except ImportError:
    edge_tts = None

import warnings
warnings.filterwarnings("ignore", category=RuntimeWarning, module="pydub")

import os
os.environ["PYDUB_SILENCE_WARNINGS"] = "1"
os.environ["FFMPEG_BINARY"] = "ffmpeg"

AudioSegment = None
try:
    from pydub import AudioSegment
except ImportError:
    pass


logger = logging.getLogger(__name__)


class AudioService:
    def __init__(self, workspace: Path, sst_model_size: str = "base", device: str = "cpu", compute_type: str = "int8"):
        self.workspace = workspace
        self.sst_model_size = sst_model_size
        self.device = device
        self.compute_type = compute_type
        self._sst_model: Any = None
        self._lock = threading.Lock()

        # Ensure models directory exists
        self.models_dir = self.workspace / "models" / "whisper"
        self.models_dir.mkdir(parents=True, exist_ok=True)

    def _get_sst_model(self) -> Any:
        if self._sst_model:
            return self._sst_model
            
        if not WhisperModel:
            logger.error("faster-whisper module not found. Please install it.")
            return None

        with self._lock:
            if self._sst_model:
                return self._sst_model
            try:
                logger.info(f"Loading Whisper model '{self.sst_model_size}' on {self.device}...")
                # download_root allows persistent caching of the model
                self._sst_model = WhisperModel(
                    self.sst_model_size, 
                    device=self.device, 
                    compute_type=self.compute_type,
                    download_root=str(self.models_dir)
                )
                logger.info("Whisper model loaded successfully.")
            except Exception as e:
                logger.error(f"Failed to load Whisper model: {e}")
                return None
            return self._sst_model

    def transcribe(self, audio_path: Path) -> str:
        """Transcribes audio file to text using Whisper."""
        if not audio_path.exists():
            logger.error(f"Audio file not found: {audio_path}")
            return ""

        # Check file size - warn if too small
        file_size = audio_path.stat().st_size
        if file_size < 1000:
            logger.warning(f"Audio file very small ({file_size} bytes), may be empty or corrupted: {audio_path}")

        model = self._get_sst_model()
        if not model:
            logger.error("Whisper model not available")
            return "[SST Error: Model not available]"

        try:
            logger.info(f"Starting transcription for: {audio_path} ({file_size} bytes)")
            # Use language detection and try with best options
            segments, info = model.transcribe(
                str(audio_path), 
                beam_size=5,
                language=None,  # Auto-detect
                task="transcribe",
                vad_filter=True,  # Use voice activity detection
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            segment_list = list(segments)
            
            if not segment_list:
                # Try again without VAD filter
                logger.info("No segments with VAD, retrying without VAD filter")
                segments2, info2 = model.transcribe(
                    str(audio_path), 
                    beam_size=5,
                    language=None
                )
                segment_list = list(segments2)
            
            text = " ".join([seg.text for seg in segment_list]).strip()
            logger.info(f"Transcription result ({len(segment_list)} segments): {text[:200]}")
            
            if not text:
                logger.warning(f"Transcription returned empty text for: {audio_path}")
                return "[SST Error: Keine Sprache erkannt - Datei möglicherweise zu kurz oder keine Sprache enthalten]"
            
            return text
        except Exception as e:
            logger.error(f"Transcription failed for {audio_path}: {e}")
            return f"[SST Error: {e}]"

    async def synthesize(self, text: str, output_path: Path, voice: str = "de-DE-ConradNeural") -> Optional[Path]:
        """Synthesizes text to speech using Edge-TTS."""
        if not edge_tts:
            logger.error("edge-tts module not found.")
            return None

        if not text.strip():
            return None

        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(str(output_path))
            return output_path
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            return None

    def convert_to_compatible_format(self, input_path: Path, target_ext: str = "mp3") -> Optional[Path]:
        """Converts audio to a compatible format using pydub (requires ffmpeg)."""
        if not AudioSegment:
            logger.warning("pydub not installed, skipping conversion.")
            return input_path # Try returning original

        try:
            audio = AudioSegment.from_file(str(input_path))
            output_path = input_path.with_suffix(f".{target_ext}")
            audio.export(str(output_path), format=target_ext)
            return output_path
        except Exception as e:
            logger.error(f"Audio conversion failed: {e}")
            return input_path
