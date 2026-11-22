"""The business-cycle wave drawn on the dashboard: one place for its shape.

Plain-English summary
---------------------
SEGMENTS holds the curve as 6 smooth pieces (cubic Bezier curves, drawn in a 820 x 290 picture).
path_d()      gives the text the page uses to draw the line.
curve_y(x)    gives the exact height of that same line at a given x, so the "You are here" dot
              is placed ON the line and cannot drift when the shape is edited.
Both read the same SEGMENTS list. A bad x or a bad shape raises ValueError (never a guess).

The module is not named "wave" because Python already has a built-in module with that name.
"""
from __future__ import annotations

START = (56.0, 212.0)
# Each piece: (control point 1, control point 2, end point). A piece starts where the last one ended.
SEGMENTS = [
    ((62, 216), (66, 218), (72, 218)),      # left edge down to the first bottom
    ((138, 218), (182, 184), (247, 138)),   # recovery: climbing through the normal-trend line
    ((312, 92), (356, 58), (422, 58)),      # expansion: climbing to the peak
    ((488, 58), (532, 92), (597, 138)),     # slowdown: falling through the normal-trend line
    ((662, 184), (706, 218), (772, 218)),   # contraction: falling to the second bottom
    ((782, 218), (790, 214), (798, 208)),   # right edge, turning up
]


def _pieces():
    """Yield (p0, p1, p2, p3) for every piece, checking that x only moves to the right."""
    p0 = START
    for c1, c2, end in SEGMENTS:
        xs = [p0[0], c1[0], c2[0], end[0]]
        if xs != sorted(xs):
            raise ValueError(f"curve piece starting at x={p0[0]} goes backwards in x; curve_y cannot work on it")
        yield p0, c1, c2, end
        p0 = end


def path_d() -> str:
    """The SVG path text for the wave line."""
    parts = [f"M {START[0]:g} {START[1]:g}"]
    for c1, c2, end in SEGMENTS:
        parts.append(f"C {c1[0]:g} {c1[1]:g}, {c2[0]:g} {c2[1]:g}, {end[0]:g} {end[1]:g}")
    return " ".join(parts)


def _point(piece, t):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = piece
    u = 1 - t
    a, b, c, d = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
    return a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3


def x_range() -> tuple[float, float]:
    return START[0], SEGMENTS[-1][2][0]


def curve_y(x: float) -> float:
    """Height of the wave line at x. Raises ValueError if x is outside the drawn line."""
    lo_x, hi_x = x_range()
    if not lo_x <= x <= hi_x:
        raise ValueError(f"x={x} is outside the drawn curve ({lo_x:g} to {hi_x:g})")
    for piece in _pieces():
        if piece[0][0] <= x <= piece[3][0]:
            lo, hi = 0.0, 1.0
            for _ in range(60):  # x grows with t, so bisection finds the t that matches x
                mid = (lo + hi) / 2
                if _point(piece, mid)[0] < x:
                    lo = mid
                else:
                    hi = mid
            return _point(piece, (lo + hi) / 2)[1]
    raise ValueError(f"no curve piece covers x={x}")  # unreachable if the pieces join up
