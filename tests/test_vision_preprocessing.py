import pytest
import sys

try:
    import numpy as np
    import cv2  # noqa: F401
    # If it's a MagicMock from our test_main.py, we still want to skip it because we can't test real methods.
    if isinstance(np, type(sys)): # It's a real module, usually Mocks aren't modules but MagicMock could act like one.
        pass
    if 'MagicMock' in str(type(np)):
        pytest.skip("numpy is mocked, skipping", allow_module_level=True)
except ImportError:
    pytest.skip("numpy/cv2 not installed, skipping", allow_module_level=True)

from houndmind_ai.optional.vision_preprocessing import VisionPreprocessor

def test_resize():
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 127
    pre = VisionPreprocessor({"resize": (224, 224), "normalize": False})
    out = pre.process(frame)
    assert out.shape == (224, 224, 3)

def test_normalize():
    frame = np.ones((224, 224, 3), dtype=np.uint8) * 255
    pre = VisionPreprocessor({"resize": (224, 224), "normalize": True})
    out = pre.process(frame)
    assert np.allclose(out.mean(), (1.0 - pre.mean).mean() / pre.std.mean(), atol=0.1)

def test_roi():
    frame = np.ones((480, 640, 3), dtype=np.uint8) * 100
    pre = VisionPreprocessor({"resize": (224, 224), "normalize": False, "roi": (100, 100, 200, 200)})
    out = pre.process(frame)
    assert out.shape == (224, 224, 3)
