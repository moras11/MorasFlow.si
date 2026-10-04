import io
import logging
import os
import re
import wave
from pathlib import Path

import numpy as np
import openai
import yaml
from faster_whisper import WhisperModel
from faster_whisper.vad import get_speech_timestamps

HERE = Path(__file__).parent
DEFAULT_MODELS = {"local": "small.en", "groq": "whisper-large-v3-turbo", "openai": "whisper-1"}
CLOUD = {"groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"), "openai": (None, "OPENAI_API_KEY")}


def make_fixer(fixes):
    """Return a function applying {"wrong": "right"} fixes to whole words, case-insensitively."""
    fixes = {str(wrong).lower(): str(right) for wrong, right in fixes.items()}
    if not fixes:
        return lambda text: text
    words = "|".join(map(re.escape, sorted(fixes, key=len, reverse=True)))  # longest match wins
    pattern = re.compile(rf"(?<!\w)(?:{words})(?!\w)", re.IGNORECASE)
    return lambda text: pattern.sub(lambda m: fixes[m.group(0).lower()], text)


def to_wav(audio, sample_rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes((np.clip(audio, -1, 1) * 32767).astype(np.int16).tobytes())
    return buf.getvalue()


def load_whisper(model, device):
    # Try the local cache first so startup makes no network call.
    try:
        return WhisperModel(model, device=device, compute_type="int8", local_files_only=True)
    except Exception:  # not downloaded yet
        try:
            return WhisperModel(model, device=device, compute_type="int8")
        except Exception as e:
            raise RuntimeError(f"Couldn't load the Whisper model '{model}' ({e}). The first run needs internet to "
                               "download it once; check config.yaml if the model or device is wrong.") from e


class Transcriber:
    def __init__(self, backend="local", model=None, device="auto"):
        self.notice = None  # set when we had to fall back, for the tray to show
        self.last_error = None  # why the last cloud transcription fell back to local, for the tray to show
        if backend != "local" and not os.environ.get(CLOUD[backend][1]):
            self.notice = f"{CLOUD[backend][1]} is not set in .env, so transcription is using local Whisper."
            backend, model = "local", None
        self.backend, self.model, self._device = backend, model or DEFAULT_MODELS[backend], device
        self._whisper = load_whisper(self.model, device) if backend == "local" else None
        if backend != "local":
            base_url, key_var = CLOUD[backend]
            # No retries: on failure we fall back to local Whisper rather than keep the user waiting.
            self._client = openai.OpenAI(base_url=base_url, api_key=os.environ[key_var], timeout=10, max_retries=0)
        vocab = HERE / "vocab.txt"  # personal, not in git; setup.bat creates it from vocab.example.txt
        lines = vocab.read_text(encoding="utf-8").splitlines() if vocab.exists() else []
        terms = [t.strip() for t in lines if t.strip() and not t.lstrip().startswith("#")]
        # Whisper mimics the prompt's style, so a punctuated list keeps punctuation in the output.
        # Only the last ~220 tokens are used, roughly 70 terms.
        self._prompt = ", ".join(terms) + "." if terms else None
        self._fix = make_fixer(yaml.safe_load((HERE / "replacements.yaml").read_text(encoding="utf-8")) or {})

    def transcribe(self, audio):
        """Corrected transcript. If the cloud fails, local Whisper transcribes instead, so nothing said is lost."""
        self.last_error = None
        if self.backend != "local":
            try:
                return self._fix(self._transcribe_cloud(audio))
            except Exception as e:
                self.last_error = e
                logging.getLogger("voiceflow").warning("Cloud transcription failed, using local Whisper: %s", e)
        return self._fix(self._transcribe_local(audio))

    def _transcribe_cloud(self, audio):
        if not get_speech_timestamps(audio):  # cloud Whisper invents text ("Thank you.") for silence
            return ""
        return self._client.audio.transcriptions.create(
            model=self.model, file=("audio.wav", to_wav(audio)), prompt=self._prompt or openai.omit,
            language="en").text.strip()

    def _transcribe_local(self, audio):
        if self._whisper is None:  # cloud backend: load local Whisper only the first time the cloud fails
            self._whisper = load_whisper(DEFAULT_MODELS["local"], self._device)
        # beam_size=1: ~1 s faster than the default 5 on CPU, same output in testing.
        segments, _ = self._whisper.transcribe(audio, beam_size=1, vad_filter=True, without_timestamps=True,
                                               initial_prompt=self._prompt)
        return "".join(s.text for s in segments).strip()


if __name__ == "__main__":
    fix = make_fixer({"XG boost": "XGBoost", "shap": "SHAP", "P.": "PyTorch"})
    assert fix("The xg Boost and Shap values, not shapely.") == "The XGBoost and SHAP values, not shapely."
    assert fix("against the P. baseline") == "against the PyTorch baseline"
    assert make_fixer({})("unchanged") == "unchanged"
    print("ok")
