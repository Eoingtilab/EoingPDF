"""Page-normalized strokes shared by GPU, Qt and PDF annotation export."""
from time import monotonic


class InkStroke(list):
    def __init__(self, points=(), kind='pen'):
        super().__init__(points)
        self.kind = kind
        self.width = 2.5
        self.color = (1, .82, 0)
        self.opacity = .3 if kind == 'highlight' else .9
        self.fill = kind == 'highlight'
        self.created = monotonic()

    def alpha(self, now=None):
        if self.kind != 'ghost':
            return self.opacity
        age = (monotonic() if now is None else now) - self.created
        return self.opacity * min(1, max(0, (3.6 - age) / .6))


def permanent(stroke):
    return len(stroke) > 1 and getattr(stroke, 'kind', 'pen') != 'ghost'
