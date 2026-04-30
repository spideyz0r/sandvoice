import logging
import os
import warnings

import numpy as np

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_FRAME_LENGTH = 1280  # 80 ms at 16 kHz — matches openWakeWord's expected chunk size

# Short names of models bundled with the package (present in 0.4.x, downloadable in 0.6.x)
_KNOWN_MODELS = frozenset([
    "hey_jarvis",
    "alexa",
    "hey_marvin",
    "hey_mycroft",
    "weather",
    "timer",
    "hey_rhasspy",
])


class OpenWakeWordDetector:
    """Wraps an openWakeWord model to expose a Porcupine-compatible interface.

    Provides ``sample_rate``, ``device_sample_rate``, ``frame_length``,
    ``process(pcm)``, and ``delete()`` so it can be used as a drop-in
    replacement for Porcupine inside WakeWordMode and BargeInDetector.
    """

    def __init__(self, model_name="hey_jarvis", threshold=0.5, device_sample_rate=None):
        """Initialise the detector.

        Args:
            model_name: Short built-in name (e.g. "hey_jarvis") or absolute
                path to a custom .onnx file.
            threshold: Detection score threshold (0.0–1.0).
            device_sample_rate: Sample rate of the audio device. When it
                differs from 16000 Hz the detector downsamples each frame
                before inference. Defaults to 16000 (no resampling).
        """
        from openwakeword.model import Model

        self._model_name = model_name
        self._threshold = threshold
        self._device_rate = device_sample_rate or _SAMPLE_RATE

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if os.path.isabs(model_name) or model_name.endswith(".onnx"):
                self._model = Model(wakeword_model_paths=[model_name], inference_framework="onnx")
                self._prediction_key = os.path.splitext(os.path.basename(model_name))[0]
            else:
                self._model = Model(wakeword_models=[model_name], inference_framework="onnx")
                self._prediction_key = model_name

        # Warm up the prediction buffer so keys are initialised
        _dummy = np.zeros(_FRAME_LENGTH, dtype=np.int16)
        self._model.predict(_dummy)

        logger.debug(
            "OpenWakeWord detector initialized: model=%s threshold=%.2f device_rate=%d",
            model_name,
            threshold,
            self._device_rate,
        )

    @property
    def sample_rate(self):
        """Model's required sample rate (16000 Hz)."""
        return _SAMPLE_RATE

    @property
    def device_sample_rate(self):
        """Sample rate to open the audio device at."""
        return self._device_rate

    @property
    def frame_length(self):
        """Samples per frame at device_sample_rate (covers the same 80 ms window)."""
        if self._device_rate == _SAMPLE_RATE:
            return _FRAME_LENGTH
        return int(_FRAME_LENGTH * self._device_rate / _SAMPLE_RATE)

    def process(self, pcm):
        """Process one audio frame and return detection result.

        Args:
            pcm: Sequence of ``frame_length`` 16-bit signed integers recorded
                at ``device_sample_rate``. Downsampled to 16 kHz if needed.

        Returns:
            0 if the wake word score meets or exceeds the threshold, -1 otherwise.
        """
        audio = np.array(pcm, dtype=np.int16)
        if self._device_rate != _SAMPLE_RATE:
            from math import gcd
            _g = gcd(self._device_rate, _SAMPLE_RATE)
            _up = _SAMPLE_RATE // _g
            _down = self._device_rate // _g
            from scipy.signal import resample_poly
            audio = resample_poly(audio, _up, _down).astype(np.int16)

        prediction = self._model.predict(audio)
        score = prediction.get(self._prediction_key, 0.0)
        if score > 0.05:
            logger.debug("Wake word score: model=%s score=%.3f threshold=%.2f", self._model_name, score, self._threshold)
        if score >= self._threshold:
            logger.debug("Wake word detected: model=%s score=%.3f", self._model_name, score)
            return 0
        return -1

    def reset(self):
        """Reset the model's internal prediction buffer.

        Call this before re-entering detection after a response cycle so that
        audio processed during TTS playback (bot's own voice picked up by the
        mic) does not carry over into the next IDLE loop as a false positive.
        """
        try:
            self._model.reset()
            logger.debug("OpenWakeWord model buffer reset")
        except Exception as e:
            logger.debug("OpenWakeWord model reset failed (non-fatal): %s", e)

    def delete(self):
        """No-op — openWakeWord holds no native resources requiring explicit release."""
