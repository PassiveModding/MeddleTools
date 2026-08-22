import math

import numpy as np


def next_power_of_two(value):
    """Smallest power of two >= value (minimum 1)."""
    power = 1
    while power < value:
        power *= 2
    return power


def pack_rects(sizes):
    """Pack rectangles into the smallest feasible power-of-two sheet.

    ``sizes`` is a list of ``(width, height)`` pixel pairs. Returns
    ``(sheet_width, sheet_height, offsets)`` where ``offsets[i]`` is the
    bottom-left ``(x, y)`` placement of ``sizes[i]``.

    Sheets are tried in increasing power-of-two area (most square shape
    first at each area), packing with MaxRects best-area-fit. Falls back to
    shelf packing if MaxRects can't fit within a reasonable area.
    """
    if not sizes:
        return 0, 0, []

    total_area = sum(width * height for width, height in sizes)
    min_width = next_power_of_two(max(width for width, _ in sizes))
    min_height = next_power_of_two(max(height for _, height in sizes))
    area = max(next_power_of_two(total_area), min_width * min_height)

    # Largest-first; ties broken by shape so the outcome is independent of
    # input order (identical sizes are interchangeable).
    order = sorted(
        range(len(sizes)),
        key=lambda i: (sizes[i][0] * sizes[i][1], max(sizes[i]), sizes[i]),
        reverse=True)

    for _ in range(8):  # each miss doubles the area; 8 is already 256x waste
        for sheet_width, sheet_height in _sheet_shapes(
                area, min_width, min_height):
            offsets = _pack_maxrects(sizes, order, sheet_width, sheet_height)
            if offsets is not None:
                return sheet_width, sheet_height, offsets
        area *= 2
    return _pack_shelf(sizes)


def _sheet_shapes(area, min_width, min_height):
    """Power-of-two ``(width, height)`` pairs of ``area``, most square first
    (wider preferred on ties, since atlases should stay near-square)."""
    shapes = []
    width = min_width
    while area // width >= min_height:
        height = area // width
        shapes.append((max(width, height) / min(width, height),
                       -width, (width, height)))
        width *= 2
    return [shape for _, _, shape in sorted(shapes)]


def _pack_maxrects(sizes, order, sheet_width, sheet_height):
    """MaxRects best-area-fit into a fixed sheet; ``None`` if it won't fit.

    ``free`` holds maximal free rectangles (they may overlap). Each
    placement carves every free rectangle it intersects into the up-to-four
    maximal remainders, then drops any rectangle contained in another.
    """
    free = [(0, 0, sheet_width, sheet_height)]
    offsets = [None] * len(sizes)
    for index in order:
        width, height = sizes[index]
        best = best_score = None
        for fx, fy, fwidth, fheight in free:
            if width > fwidth or height > fheight:
                continue
            score = (fwidth * fheight - width * height,
                     min(fwidth - width, fheight - height), fy, fx)
            if best_score is None or score < best_score:
                best_score, best = score, (fx, fy)
        if best is None:
            return None
        x, y = best
        offsets[index] = (x, y)

        placed = (x, y, x + width, y + height)
        next_free = []
        for fx, fy, fwidth, fheight in free:
            if (fx >= placed[2] or fx + fwidth <= placed[0]
                    or fy >= placed[3] or fy + fheight <= placed[1]):
                next_free.append((fx, fy, fwidth, fheight))
                continue
            if placed[0] > fx:
                next_free.append((fx, fy, placed[0] - fx, fheight))
            if placed[2] < fx + fwidth:
                next_free.append((placed[2], fy, fx + fwidth - placed[2], fheight))
            if placed[1] > fy:
                next_free.append((fx, fy, fwidth, placed[1] - fy))
            if placed[3] < fy + fheight:
                next_free.append((fx, placed[3], fwidth, fy + fheight - placed[3]))
        unique = sorted(set(next_free))
        free = [rect for rect in unique
                if not any(other != rect and _contains(other, rect)
                           for other in unique)]
    return offsets


def _contains(outer, inner):
    ox, oy, owidth, oheight = outer
    ix, iy, iwidth, iheight = inner
    return (ox <= ix and oy <= iy
            and ix + iwidth <= ox + owidth and iy + iheight <= oy + oheight)


def _pack_shelf(sizes):
    """First-Fit Decreasing Height shelf packing. Always succeeds, so it
    backstops :func:`pack_rects` when MaxRects keeps missing."""
    total_area = sum(width * height for width, height in sizes)
    sheet_width = max(
        next_power_of_two(math.isqrt(total_area)),
        next_power_of_two(max(width for width, _ in sizes)),
    )

    offsets = [None] * len(sizes)
    shelf_x = shelf_y = shelf_height = 0
    for index in sorted(range(len(sizes)),
                        key=lambda i: sizes[i][1], reverse=True):
        width, height = sizes[index]
        if shelf_x + width > sheet_width:  # start a new shelf
            shelf_y += shelf_height
            shelf_x = shelf_height = 0
        offsets[index] = (shelf_x, shelf_y)
        shelf_x += width
        shelf_height = max(shelf_height, height)

    sheet_height = next_power_of_two(shelf_y + shelf_height)
    return sheet_width, sheet_height, offsets


def resize_bilinear(pixels, width, height):
    """Resample an ``(H, W, C)`` float array to ``(height, width, C)``."""
    source_height, source_width = pixels.shape[:2]
    if (source_width, source_height) == (width, height):
        return pixels

    xs = np.linspace(0.0, source_width - 1.0, width, dtype=np.float32)
    ys = np.linspace(0.0, source_height - 1.0, height, dtype=np.float32)
    x0 = np.floor(xs).astype(np.int32)
    y0 = np.floor(ys).astype(np.int32)
    x1 = np.minimum(x0 + 1, source_width - 1)
    y1 = np.minimum(y0 + 1, source_height - 1)
    weight_x = (xs - x0)[None, :, None]
    weight_y = (ys - y0)[:, None, None]

    top = (pixels[y0[:, None], x0[None, :]] * (1.0 - weight_x)
           + pixels[y0[:, None], x1[None, :]] * weight_x)
    bottom = (pixels[y1[:, None], x0[None, :]] * (1.0 - weight_x)
              + pixels[y1[:, None], x1[None, :]] * weight_x)
    return top * (1.0 - weight_y) + bottom * weight_y
