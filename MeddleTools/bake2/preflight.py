import logging
import math
from array import array
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# game UVs sit right on the 0-1 border a lot, don't flag those
UV_EPS = 1e-4

# UVs closer than 1/_WELD_QUANT count as the same point
_WELD_QUANT = 100000

# Islands whose bounding boxes match at this resolution count as stacked.
_STACK_QUANT = 2  # decimal places


@dataclass
class IslandInfo:
    min_u: float
    min_v: float
    max_u: float
    max_v: float
    polygons: int

    @property
    def span_u(self):
        return self.max_u - self.min_u

    @property
    def span_v(self):
        return self.max_v - self.min_v

    @property
    def max_span(self):
        return max(self.span_u, self.span_v)

    @property
    def out_of_unit(self):
        """True when any part of the island falls outside 0-1 (would clip)."""
        return (
            self.min_u < -UV_EPS or self.min_v < -UV_EPS
            or self.max_u > 1.0 + UV_EPS or self.max_v > 1.0 + UV_EPS
        )

    @property
    def fits_tile(self):
        """True when a pure translation could bring the island into 0-1."""
        return self.span_u <= 1.0 + UV_EPS and self.span_v <= 1.0 + UV_EPS


@dataclass
class MeshUVReport:
    islands: list = field(default_factory=list)
    out_of_bounds_count: int = 0
    stacked_count: int = 0
    max_span: float = 0.0

    @property
    def has_problems(self):
        # stacked islands don't count here, summarize() warns about those
        return self.out_of_bounds_count > 0


def _poly_island_roots(loop_starts, loop_totals, loop_vertex_indices, loop_uvs):
    """Union-find: island root index for each polygon.

    Polygons are joined when they share a mesh vertex at the same (quantized)
    UV position, i.e. connected geometry not split by a UV seam.
    """
    poly_count = len(loop_starts)
    parent = list(range(poly_count))

    def find(index):
        root = index
        while parent[root] != root:
            root = parent[root]
        while parent[index] != root:  # path compression
            parent[index], index = root, parent[index]
        return root

    point_owner = {}
    for poly in range(poly_count):
        start = loop_starts[poly]
        for loop in range(start, start + loop_totals[poly]):
            key = (
                loop_vertex_indices[loop],
                int(round(loop_uvs[2 * loop] * _WELD_QUANT)),
                int(round(loop_uvs[2 * loop + 1] * _WELD_QUANT)),
            )
            owner = point_owner.setdefault(key, poly)
            if owner != poly:
                parent[find(poly)] = find(owner)

    return [find(poly) for poly in range(poly_count)]


def _island_bounds(loop_starts, loop_totals, loop_uvs, roots):
    """root -> [min_u, min_v, max_u, max_v, poly_count] for each island."""
    bounds = {}
    for poly, root in enumerate(roots):
        entry = bounds.get(root)
        if entry is None:
            entry = bounds[root] = [float('inf'), float('inf'),
                                    float('-inf'), float('-inf'), 0]
        entry[4] += 1
        start = loop_starts[poly]
        for loop in range(start, start + loop_totals[poly]):
            u = loop_uvs[2 * loop]
            v = loop_uvs[2 * loop + 1]
            entry[0] = min(entry[0], u)
            entry[1] = min(entry[1], v)
            entry[2] = max(entry[2], u)
            entry[3] = max(entry[3], v)
    return bounds


def build_islands(loop_starts, loop_totals, loop_vertex_indices, loop_uvs):
    """Group polygons into UV islands and return their metrics."""
    roots = _poly_island_roots(loop_starts, loop_totals, loop_vertex_indices, loop_uvs)
    bounds = _island_bounds(loop_starts, loop_totals, loop_uvs, roots)
    return [
        IslandInfo(min_u=e[0], min_v=e[1], max_u=e[2], max_v=e[3], polygons=e[4])
        for e in bounds.values()
    ]


def normalize_into_tile(loop_starts, loop_totals, loop_vertex_indices, loop_uvs,
                        margin=0.002):
    """Return a copy of ``loop_uvs`` with every island inside the 0-1 tile.

    Islands already inside are untouched. Ones that fit get shifted a whole
    tile. Anything bigger than one tile gets scaled down. Stacked islands
    stay stacked; the packer separates those later.
    """
    roots = _poly_island_roots(loop_starts, loop_totals, loop_vertex_indices, loop_uvs)
    bounds = _island_bounds(loop_starts, loop_totals, loop_uvs, roots)

    limit = 1.0 - 2.0 * margin
    transforms = {}  # root -> (scale, du, dv): uv' = uv * scale + d
    for root, (min_u, min_v, max_u, max_v, _count) in bounds.items():
        if (min_u >= -UV_EPS and min_v >= -UV_EPS
                and max_u <= 1.0 + UV_EPS and max_v <= 1.0 + UV_EPS):
            transforms[root] = (1.0, 0.0, 0.0)
            continue

        span_u = max_u - min_u
        span_v = max_v - min_v
        if max(span_u, span_v) <= limit:
            tile_u = math.floor(min_u)
            tile_v = math.floor(min_v)
            frac_u = min_u - tile_u
            frac_v = min_v - tile_v
            if frac_u + span_u <= 1.0 - margin and frac_v + span_v <= 1.0 - margin:
                transforms[root] = (1.0, -tile_u, -tile_v)
            else:
                # Fits a tile but straddles an edge: anchor at the origin.
                transforms[root] = (1.0, margin - min_u, margin - min_v)
            continue

        scale = limit / max(span_u, span_v)
        transforms[root] = (scale, margin - min_u * scale, margin - min_v * scale)

    out = list(loop_uvs)
    for poly, root in enumerate(roots):
        scale, du, dv = transforms[root]
        if scale == 1.0 and du == 0.0 and dv == 0.0:
            continue
        start = loop_starts[poly]
        for loop in range(start, start + loop_totals[poly]):
            out[2 * loop] = loop_uvs[2 * loop] * scale + du
            out[2 * loop + 1] = loop_uvs[2 * loop + 1] * scale + dv
    return out


def fit_layout_into_tile(loop_uvs):
    """Uniformly transform the whole UV layout into the 0-1 tile.

    Layout-preserving alternative to :func:`normalize_into_tile`: one
    scale + translation for the whole mesh instead of per-island, so
    density drops if the layout spanned more than one tile.

    Returns ``(new_uvs, size_multiplier)`` to grow the bake image by.
    """
    out = list(loop_uvs)
    if not out:
        return out, 1.0

    min_u = min(out[0::2])
    max_u = max(out[0::2])
    min_v = min(out[1::2])
    max_v = max(out[1::2])
    if (min_u >= -UV_EPS and min_v >= -UV_EPS
            and max_u <= 1.0 + UV_EPS and max_v <= 1.0 + UV_EPS):
        return out, 1.0

    span = max(max_u - min_u, max_v - min_v)
    if span > 1.0:
        scale = 1.0 / span
        multiplier = span
    else:
        scale = 1.0
        multiplier = 1.0

    du = -min_u * scale
    dv = -min_v * scale
    for index in range(0, len(out), 2):
        out[index] = out[index] * scale + du
        out[index + 1] = out[index + 1] * scale + dv
    return out, multiplier


def count_stacked(islands):
    """Number of islands sharing a (quantized) bounding box with another.
    Checks near-identical boxes, not exact overlap, so tightly packed
    islands don't false-positive.
    """
    groups = {}
    for island in islands:
        key = (
            round(island.min_u, _STACK_QUANT), round(island.min_v, _STACK_QUANT),
            round(island.max_u, _STACK_QUANT), round(island.max_v, _STACK_QUANT),
        )
        groups.setdefault(key, []).append(island)
    return sum(len(group) for group in groups.values() if len(group) > 1)


def analyze_uv_layout(loop_starts, loop_totals, loop_vertex_indices, loop_uvs):
    islands = build_islands(loop_starts, loop_totals, loop_vertex_indices, loop_uvs)
    return MeshUVReport(
        islands=islands,
        out_of_bounds_count=sum(1 for island in islands if island.out_of_unit),
        stacked_count=count_stacked(islands),
        max_span=max((island.max_span for island in islands), default=0.0),
    )


def uses_iris_material(obj):
    """True when any material on the mesh is an FFXIV iris shader."""
    return any(
        mat is not None and 'iris.shpk' in mat.name.lower()
        for mat in obj.data.materials
    )


def summarize(report, obj=None):
    """(status, text, fix_hint) for the UI.

    Status is 'OK' | 'WARNING' | 'PROBLEM'; ``fix_hint`` is a short advisory
    ("" when there is none). ``obj`` is the analyzed mesh object (optional);
    passing it enables material-aware findings.
    """
    clips = report.out_of_bounds_count > 0
    tiles = report.max_span > 1.0 + UV_EPS
    stacked = report.stacked_count > 0

    if clips or tiles:
        findings = []
        if clips:
            findings.append(
                f"{report.out_of_bounds_count} island(s) outside 0-1 (will clip)")
        if tiles:
            findings.append(f"tiles up to {report.max_span:.1f}x")
        if stacked:
            findings.append(f"{report.stacked_count} stacked")
        if tiles:
            hint = "UVs span 0-1 boundaries: repack, or keep layout at a larger size"
        else:
            hint = "UVs outside 0-1 will not bake correctly"
        return 'PROBLEM', "; ".join(findings), hint

    # stacked islands are usually fine, mirrored copies just bake the same
    # pixels twice. iris stacks the UVs but uses vertex color to tell left
    # and right eye apart, so baking needs to unstack it first or you lose
    # heterochromia
    if stacked:
        text = f"{report.stacked_count} stacked island(s)"
        hint = ""
        if obj is not None and uses_iris_material(obj):
            hint = "Heterochromia will be lost"
        return 'WARNING', text, hint

    return 'OK', "OK", ""


def extract_mesh_arrays(mesh, uv_layer_name):
    """Pull loop/polygon/UV arrays out of a mesh, or None if the layer is missing."""
    layer = mesh.uv_layers.get(uv_layer_name)
    if layer is None:
        return None

    poly_count = len(mesh.polygons)
    loop_count = len(mesh.loops)
    loop_starts = array('i', [0]) * poly_count
    loop_totals = array('i', [0]) * poly_count
    vertex_indices = array('i', [0]) * loop_count
    uvs = array('f', [0.0]) * (2 * loop_count)

    mesh.polygons.foreach_get('loop_start', loop_starts)
    mesh.polygons.foreach_get('loop_total', loop_totals)
    mesh.loops.foreach_get('vertex_index', vertex_indices)
    layer.data.foreach_get('uv', uvs)
    return loop_starts, loop_totals, vertex_indices, uvs


def analyze_object(obj, uv_layer_name):
    """Analyze one mesh object's UV layer. None if the layer doesn't exist."""
    arrays = extract_mesh_arrays(obj.data, uv_layer_name)
    if arrays is None:
        return None
    return analyze_uv_layout(*arrays)


def safe_analyze_object(obj, uv_layer_name):
    """analyze_object that never raises; analysis must not block a bake."""
    try:
        return analyze_object(obj, uv_layer_name)
    except Exception:
        logger.exception("UV preflight failed for %s", getattr(obj, 'name', obj))
        return None
