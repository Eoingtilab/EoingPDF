import sys
from pathlib import Path
import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from eoingpdf.imaging import deskew, estimate_skew, knockout_white


def card(angle=0, low_contrast=False):
    image = np.full((700, 1000, 3), 250, dtype=np.uint8)
    shade = 185 if low_contrast else 40
    cv2.rectangle(image, (130, 160), (860, 530), (shade,) * 3, 3)
    for y in (260, 320, 380, 440):
        cv2.line(image, (200, y), (700, y), (shade,) * 3, 3)
    cv2.putText(image, 'SYNTHETIC ID', (220, 220), cv2.FONT_HERSHEY_SIMPLEX, .9, (shade,) * 3, 2)
    matrix = cv2.getRotationMatrix2D((500, 350), angle, 1)
    return cv2.warpAffine(image, matrix, (1000, 700), borderValue=(250, 250, 250))


@pytest.mark.parametrize('angle', [-14, -7, -2, 0, 3, 8, 15])
@pytest.mark.parametrize('low_contrast', [False, True])
def test_synthetic_deskew(angle, low_contrast):
    source = card(angle, low_contrast)
    result = deskew(source)
    assert abs(result.angle + angle) < 1.0
    residual, confidence = estimate_skew(result.image)
    assert abs(residual) < 1.0
    assert confidence >= .55
    assert result.image.shape[0] >= source.shape[0]


def test_uniform_rounded_and_monochrome():
    blank = np.full((200, 300, 3), 255, dtype=np.uint8)
    result = deskew(blank)
    assert result.angle == 0
    assert np.array_equal(result.image, blank)
    image = card(6)
    # Removing corner pixels simulates rounded identity-card edges.
    cv2.circle(image, (150, 180), 25, (250, 250, 250), -1)
    result = deskew(image, monochrome=True)
    assert result.image.ndim == 2
    assert set(np.unique(result.image)).issubset({0, 255})
    with pytest.raises(ValueError):
        deskew(np.zeros((2, 2), dtype=np.uint8))


def test_signature_knockout_preserves_red_ink():
    image = np.full((100, 200, 3), 255, dtype=np.uint8)
    image[30:70, 50:150] = (180, 10, 10)
    result = knockout_white(image)
    assert result[0, 0, 3] == 0
    assert result[50, 100, 3] == 255
    assert tuple(result[50, 100, :3]) == (180, 10, 10)
