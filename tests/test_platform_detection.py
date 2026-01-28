import unittest
from unittest.mock import Mock, patch
from common.platform_detection import (
    get_platform,
    get_architecture,
    is_macos,
    is_linux,
    is_likely_raspberry_pi,
    is_arm_architecture,
    get_platform_info,
    log_platform_info
)


class TestPlatformDetection(unittest.TestCase):
    @patch('common.platform_detection.platform.system')
    def test_get_platform_macos(self, mock_system):
        """Test platform detection on macOS"""
        mock_system.return_value = 'Darwin'
        self.assertEqual(get_platform(), 'darwin')

    @patch('common.platform_detection.platform.system')
    def test_get_platform_linux(self, mock_system):
        """Test platform detection on Linux"""
        mock_system.return_value = 'Linux'
        self.assertEqual(get_platform(), 'linux')

    @patch('common.platform_detection.platform.machine')
    def test_get_architecture_arm64(self, mock_machine):
        """Test architecture detection for ARM64 (Apple Silicon)"""
        mock_machine.return_value = 'arm64'
        self.assertEqual(get_architecture(), 'arm64')

    @patch('common.platform_detection.platform.machine')
    def test_get_architecture_aarch64(self, mock_machine):
        """Test architecture detection for aarch64 (Pi 4)"""
        mock_machine.return_value = 'aarch64'
        self.assertEqual(get_architecture(), 'aarch64')

    @patch('common.platform_detection.platform.machine')
    def test_get_architecture_armv7l(self, mock_machine):
        """Test architecture detection for armv7l (Pi 3B)"""
        mock_machine.return_value = 'armv7l'
        self.assertEqual(get_architecture(), 'armv7l')

    @patch('common.platform_detection.platform.machine')
    def test_get_architecture_x86_64(self, mock_machine):
        """Test architecture detection for x86_64 (Intel Mac)"""
        mock_machine.return_value = 'x86_64'
        self.assertEqual(get_architecture(), 'x86_64')

    @patch('common.platform_detection.platform.system')
    def test_is_macos_true(self, mock_system):
        """Test is_macos returns True on macOS"""
        mock_system.return_value = 'Darwin'
        self.assertTrue(is_macos())

    @patch('common.platform_detection.platform.system')
    def test_is_macos_false(self, mock_system):
        """Test is_macos returns False on Linux"""
        mock_system.return_value = 'Linux'
        self.assertFalse(is_macos())

    @patch('common.platform_detection.platform.system')
    def test_is_linux_true(self, mock_system):
        """Test is_linux returns True on Linux"""
        mock_system.return_value = 'Linux'
        self.assertTrue(is_linux())

    @patch('common.platform_detection.platform.system')
    def test_is_linux_false(self, mock_system):
        """Test is_linux returns False on macOS"""
        mock_system.return_value = 'Darwin'
        self.assertFalse(is_linux())

    @patch('common.platform_detection.platform.machine')
    @patch('common.platform_detection.platform.system')
    def test_is_likely_raspberry_pi_true_armv7l(self, mock_system, mock_machine):
        """Test is_likely_raspberry_pi returns True for Pi 3B (armv7l)"""
        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'armv7l'
        self.assertTrue(is_likely_raspberry_pi())

    @patch('common.platform_detection.platform.machine')
    @patch('common.platform_detection.platform.system')
    def test_is_likely_raspberry_pi_true_aarch64(self, mock_system, mock_machine):
        """Test is_likely_raspberry_pi returns True for Pi 4 (aarch64)"""
        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'aarch64'
        self.assertTrue(is_likely_raspberry_pi())

    @patch('common.platform_detection.platform.machine')
    @patch('common.platform_detection.platform.system')
    def test_is_likely_raspberry_pi_false_macos(self, mock_system, mock_machine):
        """Test is_likely_raspberry_pi returns False on macOS ARM"""
        mock_system.return_value = 'Darwin'
        mock_machine.return_value = 'arm64'
        self.assertFalse(is_likely_raspberry_pi())

    @patch('common.platform_detection.platform.machine')
    @patch('common.platform_detection.platform.system')
    def test_is_likely_raspberry_pi_true_armv6l(self, mock_system, mock_machine):
        """Test is_likely_raspberry_pi returns True for Pi Zero (armv6l)"""
        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'armv6l'
        self.assertTrue(is_likely_raspberry_pi())

    @patch('common.platform_detection.platform.machine')
    @patch('common.platform_detection.platform.system')
    def test_is_likely_raspberry_pi_true_armv8(self, mock_system, mock_machine):
        """Test is_likely_raspberry_pi returns True for Pi with armv8"""
        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'armv8'
        self.assertTrue(is_likely_raspberry_pi())

    @patch('common.platform_detection.platform.machine')
    @patch('common.platform_detection.platform.system')
    def test_is_likely_raspberry_pi_false_linux_x86(self, mock_system, mock_machine):
        """Test is_likely_raspberry_pi returns False on Linux x86"""
        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'x86_64'
        self.assertFalse(is_likely_raspberry_pi())

    @patch('common.platform_detection.platform.machine')
    def test_is_arm_architecture_arm64(self, mock_machine):
        """Test is_arm_architecture returns True for arm64"""
        mock_machine.return_value = 'arm64'
        self.assertTrue(is_arm_architecture())

    @patch('common.platform_detection.platform.machine')
    def test_is_arm_architecture_aarch64(self, mock_machine):
        """Test is_arm_architecture returns True for aarch64"""
        mock_machine.return_value = 'aarch64'
        self.assertTrue(is_arm_architecture())

    @patch('common.platform_detection.platform.machine')
    def test_is_arm_architecture_armv7l(self, mock_machine):
        """Test is_arm_architecture returns True for armv7l"""
        mock_machine.return_value = 'armv7l'
        self.assertTrue(is_arm_architecture())

    @patch('common.platform_detection.platform.machine')
    def test_is_arm_architecture_false_x86(self, mock_machine):
        """Test is_arm_architecture returns False for x86_64"""
        mock_machine.return_value = 'x86_64'
        self.assertFalse(is_arm_architecture())

    @patch('common.platform_detection.platform.version')
    @patch('common.platform_detection.platform.release')
    @patch('common.platform_detection.platform.machine')
    @patch('common.platform_detection.platform.system')
    def test_get_platform_info_macos(self, mock_system, mock_machine, mock_release, mock_version):
        """Test get_platform_info returns complete info for macOS"""
        mock_system.return_value = 'Darwin'
        mock_machine.return_value = 'arm64'
        mock_release.return_value = '23.1.0'
        mock_version.return_value = 'Darwin Kernel Version 23.1.0'

        info = get_platform_info()

        self.assertEqual(info['system'], 'Darwin')
        self.assertEqual(info['platform'], 'darwin')
        self.assertEqual(info['machine'], 'arm64')
        self.assertEqual(info['release'], '23.1.0')
        self.assertTrue(info['is_macos'])
        self.assertFalse(info['is_linux'])
        self.assertFalse(info['is_likely_raspberry_pi'])
        self.assertTrue(info['is_arm'])

    @patch('common.platform_detection.platform.version')
    @patch('common.platform_detection.platform.release')
    @patch('common.platform_detection.platform.machine')
    @patch('common.platform_detection.platform.system')
    def test_get_platform_info_raspberry_pi(self, mock_system, mock_machine, mock_release, mock_version):
        """Test get_platform_info returns complete info for Raspberry Pi"""
        mock_system.return_value = 'Linux'
        mock_machine.return_value = 'armv7l'
        mock_release.return_value = '6.1.21-v7+'
        mock_version.return_value = '#1642 SMP Mon Apr  3 17:20:52 BST 2023'

        info = get_platform_info()

        self.assertEqual(info['system'], 'Linux')
        self.assertEqual(info['platform'], 'linux')
        self.assertEqual(info['machine'], 'armv7l')
        self.assertFalse(info['is_macos'])
        self.assertTrue(info['is_linux'])
        self.assertTrue(info['is_likely_raspberry_pi'])
        self.assertTrue(info['is_arm'])

    @patch('builtins.print')
    @patch('common.platform_detection.get_platform_info')
    def test_log_platform_info_debug_enabled(self, mock_get_info, mock_print):
        """Test log_platform_info prints when debug enabled"""
        mock_config = Mock()
        mock_config.debug = True

        mock_get_info.return_value = {
            'system': 'Darwin',
            'platform': 'darwin',
            'architecture': 'arm64',
            'machine': 'arm64',
            'release': '23.1.0',
            'is_macos': True,
            'is_linux': False,
            'is_likely_raspberry_pi': False,
            'is_arm': True,
        }

        log_platform_info(mock_config)

        # Should have called print multiple times
        self.assertGreater(mock_print.call_count, 5)

    @patch('builtins.print')
    @patch('common.platform_detection.get_platform_info')
    def test_log_platform_info_debug_disabled(self, mock_get_info, mock_print):
        """Test log_platform_info doesn't print when debug disabled"""
        mock_config = Mock()
        mock_config.debug = False

        log_platform_info(mock_config)

        # Should not have called print
        mock_print.assert_not_called()

    @patch('builtins.print')
    @patch('common.platform_detection.get_platform_info')
    def test_log_platform_info_no_config(self, mock_get_info, mock_print):
        """Test log_platform_info doesn't print when no config provided"""
        log_platform_info()

        # Should not have called print
        mock_print.assert_not_called()


if __name__ == '__main__':
    unittest.main()
