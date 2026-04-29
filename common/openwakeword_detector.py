import importlib.resources
import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_FRAME_LENGTH = 1280  # 80 ms at 16 kHz — matches openWakeWord's expected chunk size

# Maps short model names to bundled .onnx filenames
_BUNDLED_MODELS = {
    "hey_jarvis": "hey_jarvis_v0.1.onnx",
    "alexa": "alexa_v0.1.onnx",
    "hey_marvin": "hey_marvin_v0.1.onnx",
    "hey_mycroft": "hey_mycroft_v0.1.onnx",
    "weather": "weather_v0.1.onnx",
    "timer": "timer_v0.1.onnx",
}


def _resolve_model_path(model_name):
    """Return an absolute path to the model .onnx file.

    Accepts either a short name (e.g. "hey_jarvis") that resolves to a bundled
    model, or an absolute/relative path to a custom .onnx file.
    """
    if os.path.isabs(model_name) or model_name.endswith(".onnx"):
        return model_name

    filename = _BUNDLED_MODELS.get(model_name)
    if filename is None:
        available = ", ".join(sorted(_BUNDLED_MODELS))
        raise ValueError(
            f"Unknown openWakeWord model '{model_name}'. "
            f"Built-in options: {available}. "
            "Or provide an absolute path to a custom .onnx file."
        )

    pkg_resources = importlib.resources.files("openwakeword") / "resources" / "models" / filename
    return str(pkg_resources)


class OpenWakeWordDetector:
    """Wraps an openWakeWord model to expose a Porcupine-compatible interface.

    Provides ``sample_rate``, ``frame_length``, ``process(pcm)``, and ``delete()``
    so it can be used as a drop-in replacement for Porcupine inside
    WakeWordMode and BargeInDetector without changing their audio loop logic.
    """

    def __init__(self, model_name="hey_jarvis", threshold=0.5):
        from openwakeword.model import Model

        self._model_name = model_name
        self._threshold = threshold

        model_path = _resolve_model_path(model_name)
        self._model = Model(wakeword_model_paths=[model_path])

        # The prediction dict key is the model filename stem (without extension)
        self._prediction_key = os.path.splitext(os.path.basename(model_path))[0]

        logger.debug(
            "OpenWakeWord detector initialized: model=%s key=%s threshold=%.2f",
            model_name,
            self._prediction_key,
            threshold,
        )

    @property
    def sample_rate(self):
        return _SAMPLE_RATE

    @property
    def frame_length(self):
        return _FRAME_LENGTH

    def process(self, pcm):
        """Process one audio frame and return detection result.

        Args:
            pcm: Sequence of ``frame_length`` 16-bit signed integers.

        Returns:
            0 if the wake word score meets or exceeds the threshold, -1 otherwise.
        """
        audio = np.array(pcm, dtype=np.int16)
        prediction = self._model.predict(audio)
        score = prediction.get(self._prediction_key, 0.0)
        if score >= self._threshold:
            logger.debug(
                "Wake word detected: model=%s score=%.3f", self._model_name, score
            )
            return 0
        return -1

    def delete(self):
        """No-op — openWakeWord holds no native resources that require explicit release."""
