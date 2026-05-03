import contextlib
import logging
import os
import time
import wave

import pyaudio
import webrtcvad

from common.utils import _is_enabled_flag

logger = logging.getLogger(__name__)

_VAD_SAMPLE_RATES = [8000, 16000, 32000, 48000]


def _negotiate_sample_rate(desired_rate):
    """Return the closest VAD-supported sample rate to desired_rate."""
    if desired_rate in _VAD_SAMPLE_RATES:
        return desired_rate
    rate = min(_VAD_SAMPLE_RATES, key=lambda x: abs(x - desired_rate))
    logger.debug(
        "VAD requires specific sample rates. Using %sHz instead of %sHz",
        rate,
        desired_rate,
    )
    return rate


class VadRecorder:
    """Records a single audio utterance using WebRTC VAD.

    Handles sample rate negotiation, PyAudio stream lifecycle,
    VAD frame loop, silence detection, WAV file writing, and
    optional ack earcon playback.
    """

    def __init__(self, config, audio, audio_lock, ack_earcon_path=None):
        """
        Args:
            config:          Config instance (reads rate, vad_aggressiveness,
                             vad_frame_duration, vad_timeout, vad_silence_duration,
                             voice_ack_earcon, tmp_files_path, etc.)
            audio:           Audio instance (used to play ack earcon).
            audio_lock:      threading.Lock acquired around audio playback calls.
            ack_earcon_path: Path to the ack earcon file, or None if not configured.
                             Created once in WakeWordMode._initialize() and injected
                             here so VadRecorder does not recreate it on every
                             recording.
        """
        self._config = config
        self._audio = audio
        self._audio_lock = audio_lock
        self._ack_earcon_path = ack_earcon_path

    def record(self):
        """Open mic, run VAD loop, detect speech, save WAV.

        Returns:
            Path to the recorded WAV file on success.
            None if no audio frames were captured (non-error; caller should
            return to IDLE without processing).

        Raises:
            Exceptions from PyAudio on stream open, or from wave on WAV
            persistence, are allowed to propagate.

            Exceptions during audio_stream.read() or webrtcvad frame
            processing are caught internally: read errors break the loop
            (possibly returning None or a partial recording); VAD errors
            are logged and the frame is assumed to be speech.
        """
        vad = webrtcvad.Vad(self._config.vad_aggressiveness)

        vad_sample_rate = _negotiate_sample_rate(self._config.rate)
        frame_duration_ms = self._config.vad_frame_duration
        vad_frame_size = int(vad_sample_rate * frame_duration_ms / 1000)

        pa = None
        audio_stream = None
        frames = []
        silence_start = None
        speech_detected = False
        recording_start = time.time()

        try:
            pa = pyaudio.PyAudio()
            audio_stream = pa.open(
                rate=vad_sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=vad_frame_size,
            )

            logger.debug(
                "Recording with VAD: %sHz, frame_duration=%sms",
                vad_sample_rate,
                frame_duration_ms,
            )

            while True:
                elapsed = time.time() - recording_start
                if elapsed > self._config.vad_timeout:
                    logger.debug("VAD timeout reached (%ss)", self._config.vad_timeout)
                    break

                try:
                    pcm = audio_stream.read(vad_frame_size, exception_on_overflow=False)
                except Exception as e:
                    logger.error("Error reading audio frame: %s", e)
                    break

                frames.append(pcm)

                try:
                    is_speech = vad.is_speech(pcm, vad_sample_rate)
                except Exception as e:
                    logger.warning("VAD processing error: %s", e)
                    is_speech = True  # Assume speech on error

                if is_speech:
                    speech_detected = True
                    silence_start = None
                else:
                    if speech_detected:
                        if silence_start is None:
                            silence_start = time.time()
                        else:
                            silence_duration = time.time() - silence_start
                            if silence_duration >= self._config.vad_silence_duration:
                                logger.debug("Silence detected (%.2fs)", silence_duration)
                                break
                    else:
                        # No speech yet: bail out after vad_silence_duration so we don't
                        # hold the mic for the full vad_timeout window waiting for speech
                        # that never comes.
                        if (time.time() - recording_start) >= self._config.vad_silence_duration:
                            logger.debug("No speech detected within %.2fs, discarding", self._config.vad_silence_duration)
                            break

            if not frames or not speech_detected:
                return None

            elapsed = time.time() - recording_start

            sample_width = None
            try:
                sample_width = pa.get_sample_size(pyaudio.paInt16)
            except Exception as e:
                logger.warning("Failed to get sample width: %s", e)
                sample_width = 2  # 16-bit PCM

            # Close input stream before playing earcon (improves compatibility)
            self._cleanup_stream(audio_stream, pa)
            audio_stream = None
            pa = None

            wav_path = os.path.join(
                self._config.tmp_files_path,
                f"wake_word_recording_{int(time.time())}.wav",
            )
            os.makedirs(self._config.tmp_files_path, exist_ok=True)

            try:
                with wave.open(wav_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(sample_width)
                    wf.setframerate(vad_sample_rate)
                    wf.writeframes(b"".join(frames))
            except Exception:
                try:
                    if os.path.exists(wav_path):
                        os.remove(wav_path)
                finally:
                    wav_path = None
                raise

            logger.debug("Recorded audio saved: %s", wav_path)
            logger.debug("Recording duration: %.2fs, %s frames", elapsed, len(frames))

            self._play_ack_earcon()

            return wav_path

        finally:
            self._cleanup_stream(audio_stream, pa)

    def _cleanup_stream(self, audio_stream, pa):
        """Stop and close a PyAudio stream and terminate PyAudio."""
        if audio_stream is not None:
            try:
                audio_stream.stop_stream()
            except Exception as e:
                logger.debug("Error stopping audio stream: %s", e)
            try:
                audio_stream.close()
            except Exception as e:
                logger.debug("Error closing audio stream: %s", e)
        if pa is not None:
            try:
                pa.terminate()
            except Exception as e:
                logger.debug("Error terminating PyAudio: %s", e)

    def _play_ack_earcon(self):
        """Play the ack earcon if configured and not already playing audio."""
        if not _is_enabled_flag(getattr(self._config, "voice_ack_earcon", False)):
            return
        if not self._ack_earcon_path or not os.path.exists(self._ack_earcon_path):
            return
        try:
            audio_playing = False
            is_playing_fn = getattr(self._audio, "is_playing", None)
            if callable(is_playing_fn):
                audio_playing = bool(is_playing_fn())
            if not audio_playing:
                with (self._audio_lock or contextlib.nullcontext()):
                    self._audio.play_audio_file(self._ack_earcon_path)
            else:
                logger.debug("Skipping ack earcon: audio is already playing")
        except Exception as e:
            logger.warning("Failed to play ack earcon: %s", e)
