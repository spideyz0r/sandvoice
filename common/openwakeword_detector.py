import logging

import numpy as np

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 16000
_FRAME_LENGTH = 1280  # 80 ms at 16 kHz — matches openWakeWord's expected chunk size


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
        self._model = Model(wakeword_models=[model_name], inference_framework="onnx")
        logger.debug(
            "OpenWakeWord detector initialized: model=%s threshold=%.2f",
            model_name,
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
        score = prediction.get(self._model_name, 0.0)
        if score >= self._threshold:
            logger.debug(
                "Wake word detected: model=%s score=%.3f", self._model_name, score
            )
            return 0
        return -1

    def delete(self):
        """No-op — openWakeWord holds no native resources that require explicit release."""
