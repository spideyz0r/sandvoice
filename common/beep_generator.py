import os
import numpy as np
import lameenc
import wave
import tempfile


def generate_sine_wave_beep(freq=800, duration=0.1, sample_rate=44100, volume=0.3):
    """Generate sine wave audio data for beep.

    Args:
        freq: Frequency in Hz (default: 800Hz)
        duration: Duration in seconds (default: 0.1s)
        sample_rate: Sample rate in Hz (default: 44100Hz)
        volume: Volume multiplier 0.0-1.0 (default: 0.3)

    Returns:
        bytes: PCM audio data (16-bit signed integers)

    Raises:
        ValueError: If parameters are invalid
    """
    if freq <= 0:
        raise ValueError("freq must be positive")
    if duration <= 0:
        raise ValueError("duration must be positive")
    if sample_rate <= 0:
        raise ValueError("sample_rate must be positive")
    if not 0.0 <= volume <= 1.0:
        raise ValueError("volume must be between 0.0 and 1.0")

    num_samples = int(sample_rate * duration)
    t = np.linspace(0, duration, num_samples, endpoint=False)

    audio = volume * np.sin(2 * np.pi * freq * t)

    audio_int16 = np.clip(audio * 32767, -32768, 32767).astype(np.int16)

    return audio_int16.tobytes()


def create_confirmation_beep(freq=800, duration=0.1, tmp_path=None, bitrate=128):
    """Create and save confirmation beep to MP3 file.

    Args:
        freq: Frequency in Hz (default: 800Hz)
        duration: Duration in seconds (default: 0.1s)
        tmp_path: Directory to save beep file (default: ~/.sandvoice/tmp/)
        bitrate: MP3 bitrate in kbps (default: 128)

    Returns:
        str: Path to the saved beep MP3 file
    """
    if tmp_path is None:
        tmp_path = os.path.expanduser("~/.sandvoice/tmp/")

    os.makedirs(tmp_path, exist_ok=True)

    duration_ms = int(duration * 1000)
    beep_filename = f"confirmation_beep_{int(freq)}Hz_{duration_ms}ms_{int(bitrate)}kbps.mp3"
    beep_path = os.path.join(tmp_path, beep_filename)

    if os.path.exists(beep_path):
        return beep_path

    audio_data = generate_sine_wave_beep(freq, duration)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_temp:
        wav_temp_path = wav_temp.name

    try:
        sample_rate = 44100
        channels = 1

        with wave.open(wav_temp_path, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)

        lame = lameenc.Encoder()
        lame.set_bit_rate(bitrate)
        lame.set_in_sample_rate(sample_rate)
        lame.set_channels(channels)
        lame.set_quality(2)

        with open(wav_temp_path, "rb") as wav_file, open(beep_path, "wb") as mp3_file:
            mp3_data = lame.encode(wav_file.read())
            mp3_data += lame.flush()
            mp3_file.write(mp3_data)

    finally:
        if os.path.exists(wav_temp_path):
            os.remove(wav_temp_path)

    return beep_path


def create_ack_earcon(freq=600, duration=0.06, tmp_path=None, bitrate=128):
    """Create and save an ack earcon to an MP3 file.

    This is a short, subtle feedback sound distinct from the wake confirmation beep.

    Args:
        freq: Frequency in Hz
        duration: Duration in seconds
        tmp_path: Directory to save mp3
        bitrate: MP3 bitrate in kbps

    Returns:
        str: Path to the saved mp3 file
    """
    if tmp_path is None:
        tmp_path = os.path.expanduser("~/.sandvoice/tmp/")

    os.makedirs(tmp_path, exist_ok=True)

    duration_ms = int(duration * 1000)
    earcon_filename = f"ack_earcon_{int(freq)}Hz_{duration_ms}ms_{int(bitrate)}kbps.mp3"
    earcon_path = os.path.join(tmp_path, earcon_filename)

    if os.path.exists(earcon_path):
        return earcon_path

    audio_data = generate_sine_wave_beep(freq, duration)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wav_temp:
        wav_temp_path = wav_temp.name

    try:
        sample_rate = 44100
        channels = 1

        with wave.open(wav_temp_path, 'wb') as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)

        lame = lameenc.Encoder()
        lame.set_bit_rate(bitrate)
        lame.set_in_sample_rate(sample_rate)
        lame.set_channels(channels)
        lame.set_quality(2)

        with open(wav_temp_path, "rb") as wav_file, open(earcon_path, "wb") as mp3_file:
            mp3_data = lame.encode(wav_file.read())
            mp3_data += lame.flush()
            mp3_file.write(mp3_data)

    finally:
        if os.path.exists(wav_temp_path):
            os.remove(wav_temp_path)

    return earcon_path
