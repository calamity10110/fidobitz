import pytest
from unittest.mock import MagicMock, patch

from houndmind_ai.optional.face_recognition import FaceRecognitionModule

@pytest.fixture
def module():
    return FaceRecognitionModule("face_recognition")

def test_apply_lbph_recognition_no_recognizer(module):
    module._recognizer = None
    entry = {"bbox": [0, 0, 10, 10]}
    face_roi = MagicMock()

    module._apply_lbph_recognition(entry, face_roi, threshold=70.0)

    assert "label" not in entry
    assert "confidence" not in entry

def test_apply_lbph_recognition_success(module):
    mock_recognizer = MagicMock()
    mock_recognizer.predict.return_value = (1, 50.0) # label_id, confidence
    module._recognizer = mock_recognizer
    module._label_map = {1: "Alice"}

    entry = {"bbox": [0, 0, 10, 10]}
    face_roi = MagicMock()

    module._apply_lbph_recognition(entry, face_roi, threshold=70.0)

    assert entry["label"] == "Alice"
    assert entry["confidence"] == 50.0

def test_apply_lbph_recognition_unknown_due_to_threshold(module):
    mock_recognizer = MagicMock()
    mock_recognizer.predict.return_value = (1, 80.0) # label_id, confidence
    module._recognizer = mock_recognizer
    module._label_map = {1: "Alice"}

    entry = {"bbox": [0, 0, 10, 10]}
    face_roi = MagicMock()

    module._apply_lbph_recognition(entry, face_roi, threshold=70.0)

    # Confidence is 80.0, which is > threshold 70.0, so it should be "unknown"
    assert entry["label"] == "unknown"
    assert entry["confidence"] == 80.0

@patch("houndmind_ai.optional.face_recognition.logger")
def test_apply_lbph_recognition_exception(mock_logger, module):
    mock_recognizer = MagicMock()
    mock_recognizer.predict.side_effect = Exception("OpenCV Error")
    module._recognizer = mock_recognizer

    entry = {"bbox": [0, 0, 10, 10]}
    face_roi = MagicMock()

    module._apply_lbph_recognition(entry, face_roi, threshold=70.0)

    # Check that exception was handled and logged
    mock_logger.warning.assert_called_once()
    assert "label" not in entry
    assert "confidence" not in entry

def test_detect_opencv(module):
    mock_cv2 = MagicMock()
    mock_cv2.COLOR_BGR2GRAY = "COLOR_BGR2GRAY"
    # Return a dummy gray image

    class DummyGray:
        def __getitem__(self, val):
            return MagicMock()

    mock_cv2.cvtColor.return_value = DummyGray()
    module._cv2 = mock_cv2

    mock_cascade = MagicMock()
    # Returns [x, y, w, h] list of arrays representing faces
    mock_cascade.detectMultiScale.return_value = [[10, 10, 50, 50]]
    module._cascade = mock_cascade

    # Mock the helper to just set a label to verify it was called
    def mock_apply(entry, roi, threshold):
        entry["label"] = "mocked"

    module._apply_lbph_recognition = MagicMock(side_effect=mock_apply)

    frame = MagicMock()
    settings = {"lbph": {"confidence_threshold": 70.0}}

    results = module._detect_opencv(frame, settings)

    assert len(results) == 1
    assert results[0]["bbox"] == [10, 10, 50, 50]
    assert results[0]["label"] == "mocked"
    module._apply_lbph_recognition.assert_called_once()
    # Ensure it's called with the correct ROI
    args, _ = module._apply_lbph_recognition.call_args
    assert args[0] == results[0]
    # Check that the threshold was passed correctly
    assert args[2] == 70.0
