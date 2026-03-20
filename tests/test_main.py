import sys
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import socket
import importlib

# To test `main.py` without requiring the "full" Pi4 dependencies to be installed
# in the test environment (which would cause ModuleNotFoundErrors on import),
# we mock out the missing heavy dependencies in sys.modules.
# We only mock them if they are not already installed to avoid breaking other tests.
_heavy_dependencies = [
    'numpy', 'cv2', 'scipy.spatial.transform', 'scipy.spatial', 'scipy',
    'face_recognition', 'SpeechRecognition', 'pyaudio', 'sounddevice', 'pyttsx3', 'vosk', 'rtabmap'
]

_mocked_modules = {}
for mod_name in _heavy_dependencies:
    if mod_name not in sys.modules:
        try:
            # Check if it actually exists
            importlib.import_module(mod_name)
        except ImportError:
            _mocked_modules[mod_name] = MagicMock()

if _mocked_modules:
    sys.modules.update(_mocked_modules)

from houndmind_ai.main import main, build_modules  # noqa: E402
from houndmind_ai.mapping import default_path_planning_hook  # noqa: E402

class TestMain(unittest.TestCase):
    @patch("houndmind_ai.main.build_modules")
    @patch("houndmind_ai.main.HoundMindRuntime")
    @patch("houndmind_ai.main.load_config")
    @patch("houndmind_ai.main.setup_logging")
    def test_main_basic(
        self, mock_setup_logging, mock_load_config, mock_runtime_cls, mock_build_modules
    ):
        """Test that main() initializes logging, runtime, and calls run()."""
        mock_config = MagicMock()
        mock_config.settings = {}
        mock_load_config.return_value = mock_config

        mock_build_modules.return_value = []
        mock_setup_logging.return_value = MagicMock()

        mock_runtime_instance = MagicMock()
        mock_context = MagicMock()
        mock_runtime_instance.context = mock_context
        mock_runtime_cls.return_value = mock_runtime_instance

        with patch.object(sys, "argv", ["houndmind"]):
            main()

        mock_load_config.assert_called_once_with(None)
        mock_setup_logging.assert_called_once_with({})
        mock_build_modules.assert_called_once_with(mock_config)
        mock_runtime_cls.assert_called_once_with(mock_config, [])
        mock_runtime_instance.run.assert_called_once()

        expected_hostname = socket.gethostname()
        mock_context.set.assert_any_call("device_id", expected_hostname)

    @patch("houndmind_ai.main.build_modules")
    @patch("houndmind_ai.main.HoundMindRuntime")
    @patch("houndmind_ai.main.load_config")
    @patch("houndmind_ai.main.setup_logging")
    def test_main_with_config_arg(
        self, mock_setup_logging, mock_load_config, mock_runtime_cls, mock_build_modules
    ):
        """Test that main() correctly passes the --config argument."""
        mock_config = MagicMock()
        mock_config.settings = {}
        mock_load_config.return_value = mock_config
        mock_build_modules.return_value = []
        mock_setup_logging.return_value = MagicMock()
        mock_runtime_instance = MagicMock()
        mock_runtime_cls.return_value = mock_runtime_instance

        config_path = "custom_settings.jsonc"
        with patch.object(sys, "argv", ["houndmind", "--config", config_path]):
            main()

        mock_load_config.assert_called_once_with(Path(config_path))

    @patch("houndmind_ai.main.build_modules")
    @patch("houndmind_ai.main.HoundMindRuntime")
    @patch("houndmind_ai.main.load_config")
    @patch("houndmind_ai.main.setup_logging")
    def test_main_device_id_from_config(
        self, mock_setup_logging, mock_load_config, mock_runtime_cls, mock_build_modules
    ):
        """Test that main() uses device_id from config if provided."""
        mock_config = MagicMock()
        mock_config.settings = {"device": {"device_id": "test-device-123"}}
        mock_load_config.return_value = mock_config
        mock_build_modules.return_value = []
        mock_setup_logging.return_value = MagicMock()
        mock_runtime_instance = MagicMock()
        mock_context = MagicMock()
        mock_runtime_instance.context = mock_context
        mock_runtime_cls.return_value = mock_runtime_instance

        with patch.object(sys, "argv", ["houndmind"]):
            main()

        mock_context.set.assert_any_call("device_id", "test-device-123")

    @patch("houndmind_ai.main.build_modules")
    @patch("houndmind_ai.main.HoundMindRuntime")
    @patch("houndmind_ai.main.load_config")
    @patch("houndmind_ai.main.setup_logging")
    def test_main_path_planning_hook_enabled(
        self, mock_setup_logging, mock_load_config, mock_runtime_cls, mock_build_modules
    ):
        """Test that path planning hook is registered when enabled in config."""
        mock_config = MagicMock()
        mock_config.settings = {"mapping": {"path_planning_enabled": True}}
        mock_load_config.return_value = mock_config
        mock_build_modules.return_value = []
        mock_setup_logging.return_value = MagicMock()
        mock_runtime_instance = MagicMock()
        mock_context = MagicMock()
        mock_runtime_instance.context = mock_context
        mock_runtime_cls.return_value = mock_runtime_instance

        with patch.object(sys, "argv", ["houndmind"]):
            main()

        mock_context.set.assert_any_call("path_planning_hook", default_path_planning_hook)

    def test_build_modules(self):
        """Test build_modules returns correct modules passing config values."""
        mock_config = MagicMock()
        mock_config.modules = {
            "hal_sensors": {"enabled": True},
            "perception": {"some_param": "value"}
        }

        module_names = [
            "SensorModule", "MotorModule", "PerceptionModule", "ScanningModule",
            "OrientationModule", "CalibrationModule", "MappingModule",
            "LocalPlannerModule", "ObstacleAvoidanceModule", "BehaviorModule",
            "HabituationModule", "AttentionModule", "EventLoggerModule",
            "LedManagerModule", "HealthMonitorModule", "ServiceWatchdogModule",
            "WatchdogModule", "BalanceModule", "SafetyModule", "EnergyEmotionModule",
            "VisionModule", "VisionPi4Module", "VoiceModule", "FaceRecognitionModule",
            "SemanticLabelerModule", "SlamPi4Module", "TelemetryDashboardModule"
        ]

        patchers = []
        mocked_modules = {}

        try:
            for name in module_names:
                p = patch(f"houndmind_ai.main.{name}")
                mocked_modules[name] = p.start()
                patchers.append(p)

            modules = build_modules(mock_config)

            self.assertEqual(len(modules), len(module_names))

            mocked_modules["SensorModule"].assert_called_once_with("hal_sensors", enabled=True)
            mocked_modules["PerceptionModule"].assert_called_once_with("perception", some_param="value")
            mocked_modules["MotorModule"].assert_called_once_with("hal_motors")

        finally:
            for p in patchers:
                p.stop()

if __name__ == "__main__":
    unittest.main()
