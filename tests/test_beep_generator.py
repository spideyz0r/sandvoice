import os
import unittest
import tempfile
import shutil

from common.beep_generator import generate_sine_wave_beep, create_confirmation_beep, create_ack_earcon


class TestGenerateSineWaveBeep(unittest.TestCase):
    def test_default_parameters(self):
        audio_data = generate_sine_wave_beep()
        self.assertIsInstance(audio_data, bytes)
        self.assertGreater(len(audio_data), 0)

    def test_custom_frequency(self):
        audio_data = generate_sine_wave_beep(freq=1000, duration=0.05)
        self.assertIsInstance(audio_data, bytes)
        expected_samples = int(44100 * 0.05)
        expected_bytes = expected_samples * 2
        self.assertEqual(len(audio_data), expected_bytes)

    def test_custom_duration(self):
        audio_data = generate_sine_wave_beep(duration=0.2)
        self.assertIsInstance(audio_data, bytes)
        expected_samples = int(44100 * 0.2)
        expected_bytes = expected_samples * 2
        self.assertEqual(len(audio_data), expected_bytes)

    def test_custom_sample_rate(self):
        sample_rate = 22050
        duration = 0.1
        audio_data = generate_sine_wave_beep(sample_rate=sample_rate, duration=duration)
        expected_samples = int(sample_rate * duration)
        expected_bytes = expected_samples * 2
        self.assertEqual(len(audio_data), expected_bytes)

    def test_invalid_freq(self):
        with self.assertRaises(ValueError) as context:
            generate_sine_wave_beep(freq=-100)
        self.assertIn("freq must be positive", str(context.exception))

        with self.assertRaises(ValueError) as context:
            generate_sine_wave_beep(freq=0)
        self.assertIn("freq must be positive", str(context.exception))

    def test_invalid_duration(self):
        with self.assertRaises(ValueError) as context:
            generate_sine_wave_beep(duration=-0.5)
        self.assertIn("duration must be positive", str(context.exception))

        with self.assertRaises(ValueError) as context:
            generate_sine_wave_beep(duration=0)
        self.assertIn("duration must be positive", str(context.exception))

    def test_invalid_sample_rate(self):
        with self.assertRaises(ValueError) as context:
            generate_sine_wave_beep(sample_rate=-44100)
        self.assertIn("sample_rate must be positive", str(context.exception))

        with self.assertRaises(ValueError) as context:
            generate_sine_wave_beep(sample_rate=0)
        self.assertIn("sample_rate must be positive", str(context.exception))

    def test_invalid_volume(self):
        with self.assertRaises(ValueError) as context:
            generate_sine_wave_beep(volume=-0.1)
        self.assertIn("volume must be between 0.0 and 1.0", str(context.exception))

        with self.assertRaises(ValueError) as context:
            generate_sine_wave_beep(volume=1.5)
        self.assertIn("volume must be between 0.0 and 1.0", str(context.exception))


class TestCreateConfirmationBeep(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_beep_file(self):
        beep_path = create_confirmation_beep(tmp_path=self.temp_dir)

        self.assertTrue(os.path.exists(beep_path))
        self.assertTrue(beep_path.endswith('.mp3'))
        self.assertGreater(os.path.getsize(beep_path), 0)

    def test_reuses_existing_beep(self):
        beep_path1 = create_confirmation_beep(tmp_path=self.temp_dir)
        mtime1 = os.path.getmtime(beep_path1)

        beep_path2 = create_confirmation_beep(tmp_path=self.temp_dir)
        mtime2 = os.path.getmtime(beep_path2)

        self.assertEqual(beep_path1, beep_path2)
        self.assertEqual(mtime1, mtime2)

    def test_custom_frequency(self):
        beep_path = create_confirmation_beep(freq=1200, tmp_path=self.temp_dir)
        self.assertTrue(os.path.exists(beep_path))

    def test_custom_duration(self):
        beep_path = create_confirmation_beep(duration=0.2, tmp_path=self.temp_dir)
        self.assertTrue(os.path.exists(beep_path))

    def test_default_tmp_path(self):
        default_path = os.path.expanduser("~/.sandvoice/tmp/")

        if os.path.isdir(default_path):
            for filename in os.listdir(default_path):
                if filename.startswith("confirmation_beep_") and filename.endswith(".mp3"):
                    os.remove(os.path.join(default_path, filename))

        beep_path = create_confirmation_beep()

        try:
            self.assertTrue(os.path.exists(beep_path))
            self.assertTrue(beep_path.startswith(default_path))
        finally:
            if os.path.exists(beep_path):
                os.remove(beep_path)


class TestCreateAckEarcon(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_creates_earcon_file(self):
        earcon_path = create_ack_earcon(tmp_path=self.temp_dir)
        self.assertTrue(os.path.exists(earcon_path))
        self.assertTrue(earcon_path.endswith('.mp3'))
        self.assertGreater(os.path.getsize(earcon_path), 0)

    def test_reuses_existing_earcon(self):
        earcon_path1 = create_ack_earcon(tmp_path=self.temp_dir)
        mtime1 = os.path.getmtime(earcon_path1)

        earcon_path2 = create_ack_earcon(tmp_path=self.temp_dir)
        mtime2 = os.path.getmtime(earcon_path2)

        self.assertEqual(earcon_path1, earcon_path2)
        self.assertEqual(mtime1, mtime2)


if __name__ == '__main__':
    unittest.main()
