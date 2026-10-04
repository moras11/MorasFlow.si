import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
TAIL_SECONDS = 0.1  # keep capturing briefly after release so the last buffered block (and word) isn't clipped


class Recorder:
    """Keeps the mic stream open so recording starts instantly.

    Opening a stream on Windows takes ~0.5 s, which would cut off the first word.
    WASAPI is used because it idles cheapest (~0.8% of one core vs 1-3% for MME).
    """

    def __init__(self):
        wasapi = next(a for a in sd.query_hostapis() if "WASAPI" in a["name"])
        if wasapi["default_input_device"] < 0:
            raise RuntimeError("No microphone found. Plug one in (or enable it in Windows sound settings), "
                               "then start the app again.")
        self.device_name = sd.query_devices(wasapi["default_input_device"])["name"]
        self._chunks = None
        self._stream = sd.InputStream(
            device=wasapi["default_input_device"], samplerate=SAMPLE_RATE, channels=1,
            dtype="float32", blocksize=800, extra_settings=sd.WasapiSettings(auto_convert=True),
            callback=self._on_audio)
        self._stream.start()

    def _on_audio(self, indata, *_):
        chunks = self._chunks
        if chunks is not None:
            chunks.append(indata.copy())

    def record(self, keep_going):
        """Return mono float32 audio captured until keep_going() returns False."""
        if not self._stream.active:  # e.g. the mic was unplugged; otherwise every dictation looks like a silent tap
            raise RuntimeError("Microphone stream stopped. Quit and start the app again.")
        self._chunks = chunks = []
        while keep_going():
            sd.sleep(10)
        sd.sleep(int(TAIL_SECONDS * 1000))
        self._chunks = None
        return np.concatenate(chunks)[:, 0] if chunks else np.zeros(0, np.float32)

    def set_paused(self, paused):
        """Stopping the stream releases the mic, so Windows' mic-in-use indicator goes away."""
        self._stream.stop() if paused else self._stream.start()
