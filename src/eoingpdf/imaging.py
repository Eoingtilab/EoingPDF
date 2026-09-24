"""Bounded scan cleanup and signature preparation. RGB input/output conventions."""
from .localization import tr
from dataclasses import dataclass
import math

import cv2
import numpy as np


@dataclass(frozen=True)
class DeskewResult:
    image: np.ndarray
    angle: float
    confidence: float


def validate(image):
    if not isinstance(image, np.ndarray) or image.dtype != np.uint8:
        raise ValueError(tr('8비트 이미지가 필요합니다.'))
    if image.ndim not in (2, 3) or (image.ndim == 3 and image.shape[2] not in (3, 4)):
        raise ValueError(tr('회색조, RGB 또는 RGBA 이미지를 선택해 주세요.'))
    height, width = image.shape[:2]
    if min(height, width) < 8 or height * width > 40_000_000:
        raise ValueError(tr('이미지 크기는 가로·세로 8픽셀 이상, 총 4천만 픽셀 이하여야 합니다.'))
    return height, width


def grayscale(image):
    validate(image)
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        alpha = image[:, :, 3:4].astype(np.float32) / 255
        image = (image[:, :, :3] * alpha + 255 * (1 - alpha)).astype(np.uint8)
    return cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)


def axial_angle(angle):
    return (float(angle) + 45) % 90 - 45


def estimate_skew(image):
    gray = grayscale(image)
    height, width = gray.shape
    scale = min(1.0, 1600 / max(height, width))
    if scale < 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    if float(gray.std()) < 1:
        return 0.0, 0.0
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    edges = cv2.Canny(enhanced, 40, 120)
    minimum = max(24, int(min(gray.shape) * .12))
    lines = cv2.HoughLinesP(edges, 1, np.pi / 720, threshold=30,
                            minLineLength=minimum, maxLineGap=12)
    angles, weights = [], []
    if lines is not None:
        for x1, y1, x2, y2 in lines[:, 0]:
            length = math.hypot(float(x2 - x1), float(y2 - y1))
            angle = axial_angle(math.degrees(math.atan2(float(y2 - y1), float(x2 - x1))))
            if abs(angle) <= 25:
                angles.append(angle)
                weights.append(length)
    # minAreaRect handles rounded corners without requiring four exact vertices.
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area = gray.shape[0] * gray.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        if cv2.contourArea(contour) < area * .08:
            continue
        rectangle = cv2.minAreaRect(contour)
        angle = axial_angle(rectangle[2])
        if abs(angle) <= 25:
            angles.append(angle)
            weights.append(max(rectangle[1]) * 2)
    if not angles:
        return 0.0, 0.0
    angles = np.asarray(angles)
    weights = np.asarray(weights)
    # Consensus prevents a decorative diagonal or portrait from rotating the page.
    support = np.array([weights[np.abs(angles - value) <= 1.5].sum() for value in angles])
    center = angles[int(support.argmax())]
    selected = np.abs(angles - center) <= 1.5
    confidence = float(weights[selected].sum() / weights.sum())
    if confidence < .55:
        return 0.0, confidence
    estimate = float(np.average(angles[selected], weights=weights[selected]))
    return (0.0 if abs(estimate) < .15 else estimate), confidence


def deskew(image, monochrome=False):
    height, width = validate(image)
    angle, confidence = estimate_skew(image)
    if angle:
        matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1)
        cosine, sine = abs(matrix[0, 0]), abs(matrix[0, 1])
        new_width = math.ceil(height * sine + width * cosine)
        new_height = math.ceil(height * cosine + width * sine)
        if new_width * new_height > 40_000_000:
            raise ValueError(tr('회전 후 이미지가 너무 큽니다. 해상도를 낮춰 주세요.'))
        matrix[0, 2] += (new_width - width) / 2
        matrix[1, 2] += (new_height - height) / 2
        border = 255 if image.ndim == 2 else (255,) * image.shape[2]
        result = cv2.warpAffine(image, matrix, (new_width, new_height),
                                flags=cv2.INTER_CUBIC, borderValue=border)
    else:
        result = image.copy()
    if monochrome:
        gray = grayscale(result)
        block = min(51, min(gray.shape) // 2 * 2 - 1)
        result = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY, max(3, block), 12)
    return DeskewResult(result, angle, confidence)


def knockout_white(image, threshold=235, feather=20):
    validate(image)
    if not 128 <= threshold <= 255 or not 1 <= feather <= 127:
        raise ValueError(tr('배경 제거 설정 범위를 확인해 주세요.'))
    rgb = cv2.cvtColor(image, cv2.COLOR_GRAY2RGB) if image.ndim == 2 else image[:, :, :3]
    whiteness = rgb.min(axis=2).astype(np.float32)
    alpha = np.clip((threshold - whiteness) / feather, 0, 1)
    if image.ndim == 3 and image.shape[2] == 4:
        alpha *= image[:, :, 3] / 255
    return np.dstack((rgb, (alpha * 255).astype(np.uint8)))


def remove_shadows(image):
    """Estimate smooth paper illumination at bounded resolution, retaining ink."""
    gray = grayscale(image)
    height, width = gray.shape
    scale = min(1.0, 768 / max(height, width))
    reduced = cv2.resize(gray, (max(8, round(width * scale)), max(8, round(height * scale))),
                         interpolation=cv2.INTER_AREA)
    kernel = max(3, round(min(reduced.shape) * .05) | 1)
    background = cv2.morphologyEx(reduced, cv2.MORPH_CLOSE,
                                 cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel, kernel)))
    background = cv2.GaussianBlur(background, (0, 0), max(1, kernel / 3))
    background = cv2.resize(background, (width, height), interpolation=cv2.INTER_LINEAR)
    # A dark photograph is not a sheet of paper. Limit amplification to 2x.
    denominator = np.maximum(background, 128)
    if image.ndim == 2:
        return cv2.divide(image, denominator, scale=255)
    rgb = image[:, :, :3]
    result = np.empty_like(rgb)
    for channel in range(3):
        result[:, :, channel] = cv2.divide(rgb[:, :, channel], denominator, scale=255)
    return result
