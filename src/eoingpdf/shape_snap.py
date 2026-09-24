"""Conservative single-stroke shape fitting in page coordinates, on pen release."""
from math import atan2, cos, hypot, isfinite, pi, sin, sqrt


def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


def segment_distance(point, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    t = max(0, min(1, ((point[0] - a[0]) * dx + (point[1] - a[1]) * dy) / length)) if length else 0
    return distance(point, (a[0] + t * dx, a[1] + t * dy))


def path_length(points):
    return sum(distance(a, b) for a, b in zip(points, points[1:]))


def resample(points, count=96):
    total = path_length(points)
    if total <= 0:
        return points[:1]
    result, segment, traversed = [], 0, 0.0
    for index in range(count):
        wanted = total * index / (count - 1)
        while segment < len(points) - 2 and traversed + distance(points[segment], points[segment + 1]) < wanted:
            traversed += distance(points[segment], points[segment + 1])
            segment += 1
        a, b = points[segment:segment + 2]
        length = distance(a, b)
        t = min(1, (wanted - traversed) / length) if length else 0
        result.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    return result


def fits(points, template, diagonal, mean_limit=.025):
    errors = [min(segment_distance(point, a, b) for a, b in zip(template, template[1:])) for point in points]
    ratio = path_length(points) / max(.001, path_length(template))
    covered = all(min(distance(vertex, point) for point in points) < diagonal * .10 for vertex in template)
    return (sum(errors) / len(errors) < diagonal * mean_limit and max(errors) < diagonal * .085
            and .8 < ratio < 1.2 and covered)


def rectangle(points, diagonal):
    # Try the directions of long chords instead of assuming axis alignment.
    angles = [atan2(b[1] - a[1], b[0] - a[0]) for a, b in zip(points[::8], points[8::8])]
    candidates = []
    for angle in angles:
        ca, sa = cos(angle), sin(angle)
        rotated = [(x * ca + y * sa, -x * sa + y * ca) for x, y in points]
        left, right = min(p[0] for p in rotated), max(p[0] for p in rotated)
        top, bottom = min(p[1] for p in rotated), max(p[1] for p in rotated)
        if min(right - left, bottom - top) < diagonal * .12:
            continue
        corners = [(left, top), (right, top), (right, bottom), (left, bottom), (left, top)]
        candidate = [(x * ca - y * sa, x * sa + y * ca) for x, y in corners]
        if fits(points, candidate, diagonal):
            candidates.append(((right - left) * (bottom - top), candidate))
    return min(candidates, key=lambda value: value[0])[1] if candidates else None


def star(points, bounds, diagonal):
    left, top, right, bottom = bounds
    if min(right - left, bottom - top) < diagonal * .35:
        return None
    for crossed in (False, True):
        for degrees in range(0, 72, 4):
            phase = degrees * pi / 180 - pi / 2
            if crossed:
                vertices = [(cos(phase + i * 4 * pi / 5), sin(phase + i * 4 * pi / 5)) for i in range(5)]
            else:
                vertices = [((1 if i % 2 == 0 else .382) * cos(phase + i * pi / 5),
                             (1 if i % 2 == 0 else .382) * sin(phase + i * pi / 5)) for i in range(10)]
            x0, x1 = min(p[0] for p in vertices), max(p[0] for p in vertices)
            y0, y1 = min(p[1] for p in vertices), max(p[1] for p in vertices)
            candidate = [(left + (x - x0) / (x1 - x0) * (right - left),
                          top + (y - y0) / (y1 - y0) * (bottom - top)) for x, y in vertices]
            candidate.append(candidate[0])
            if fits(points, candidate, diagonal, .03):
                return candidate
    return None


def arrow(points, diagonal):
    for sequence in (points, list(reversed(points))):
        tail = sequence[0]
        tip_index = max(range(len(sequence)), key=lambda index: distance(tail, sequence[index]))
        tip = sequence[tip_index]
        length = distance(tail, tip)
        # A hand-drawn arrow revisits its tip. Keep the first visit so both
        # wings participate even when the second visit is a little farther out.
        tip_index = next(i for i, point in enumerate(sequence) if distance(tail, point) >= length * .98)
        if length < diagonal * .7 or tip_index < 10 or tip_index > len(sequence) - 10:
            continue
        ux, uy = (tip[0] - tail[0]) / length, (tip[1] - tail[1]) / length
        head = sequence[tip_index:]
        projections = [((p[0] - tip[0]) * ux + (p[1] - tip[1]) * uy,
                        -(p[0] - tip[0]) * uy + (p[1] - tip[1]) * ux) for p in head]
        negative, positive = min(p[1] for p in projections), max(p[1] for p in projections)
        back = -min(p[0] for p in projections)
        if not (.07 * length < -negative < .4 * length and .07 * length < positive < .4 * length
                and .1 * length < back < .5 * length):
            continue
        wing = (positive - negative) / 2
        a = (tip[0] - back * ux - wing * uy, tip[1] - back * uy + wing * ux)
        b = (tip[0] - back * ux + wing * uy, tip[1] - back * uy - wing * ux)
        candidate = [tail, tip, a, tip, b]
        if fits(sequence, candidate, diagonal, .035):
            return candidate
    return None


def checkmark(points, diagonal):
    first, last = points[0], points[-1]
    middle = max(points[1:-1], key=lambda p: segment_distance(p, first, last))
    if segment_distance(middle, first, last) < diagonal * .12:
        return None
    if not (first[0] < middle[0] < last[0] and first[1] < middle[1] and last[1] < middle[1]):
        return None
    if distance(middle, last) < distance(first, middle) * 1.35:
        return None
    candidate = [first, middle, last]
    return candidate if fits(points, candidate, diagonal, .025) else None


def snap_shape(points, width, height):
    """Return (shape name, normalized vertices), or None for uncertain handwriting."""
    if not (isfinite(width) and isfinite(height) and width > 0 and height > 0) or not 6 <= len(points) <= 250000:
        return None
    source = [(float(point.x()) * width, float(point.y()) * height) for point in points]
    if not all(isfinite(x) and isfinite(y) for x, y in source):
        return None
    sampled = resample(source)
    if len(sampled) < 6:
        return None
    left, right = min(p[0] for p in sampled), max(p[0] for p in sampled)
    top, bottom = min(p[1] for p in sampled), max(p[1] for p in sampled)
    diagonal = hypot(right - left, bottom - top)
    if diagonal < 8:
        return None
    result = None
    if distance(sampled[0], sampled[-1]) < diagonal * .14:
        cx, cy = (left + right) / 2, (top + bottom) / 2
        radii = [hypot(x - cx, y - cy) for x, y in sampled]
        radius = sum(radii) / len(radii)
        variation = sqrt(sum((r - radius) ** 2 for r in radii) / len(radii)) / max(radius, .001)
        circumference = 2 * pi * radius
        if variation < .055 and .85 < (right - left) / max(.001, bottom - top) < 1.18 and .85 < path_length(sampled) / circumference < 1.15:
            result = ('circle', [(cx + radius * cos(i * 2 * pi / 72), cy + radius * sin(i * 2 * pi / 72)) for i in range(73)])
        if result is None:
            fitted = rectangle(sampled, diagonal)
            if fitted: result = ('rectangle', fitted)
        if result is None:
            fitted = star(sampled, (left, top, right, bottom), diagonal)
            if fitted: result = ('star', fitted)
    else:
        fitted = arrow(sampled, diagonal)
        if fitted: result = ('arrow', fitted)
        if result is None:
            fitted = checkmark(sampled, diagonal) or checkmark(list(reversed(sampled)), diagonal)
            if fitted: result = ('check', fitted)
    if result is None or any(not (0 <= x <= width and 0 <= y <= height) for x, y in result[1]):
        return None
    return result[0], [(x / width, y / height) for x, y in result[1]]
