#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BREP Geometry Traversal & Computation
======================================
Traverses the BREP face/edge/loop graph to compute:
  - Bounding box, surface area, blank area
  - Outer profile cutting length, perimeter
  - Hole inventory (diameter grouping)
  - Pierce count, bend count, thickness
  - 2D contour extraction

All linear units are millimeters (mm); areas in mm².
"""

import math
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional, Any

from .parser import EntityStore


# ═══════════════════════════════════════════════════════════════
# Vector Math Utilities
# ═══════════════════════════════════════════════════════════════

def vec_sub(a: Tuple[float, float, float],
            b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_add(a: Tuple[float, float, float],
            b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_dot(a: Tuple[float, float, float],
            b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a: Tuple[float, float, float],
              b: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0]
    )


def vec_len(v: Tuple[float, float, float]) -> float:
    return math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])


def vec_norm(v: Tuple[float, float, float]) -> Tuple[float, float, float]:
    length = vec_len(v)
    if length < 1e-12:
        return (0.0, 0.0, 0.0)
    return (v[0] / length, v[1] / length, v[2] / length)


def angle_between(a: Tuple[float, float, float],
                  b: Tuple[float, float, float]) -> float:
    """Return angle between two vectors in degrees."""
    dot = vec_dot(vec_norm(a), vec_norm(b))
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(math.acos(dot))


# ═══════════════════════════════════════════════════════════════
# Point & Direction Extraction
# ═══════════════════════════════════════════════════════════════

def _extract_point_coords(store: EntityStore, point_id: int) -> Optional[Tuple[float, float, float]]:
    """Extract (x, y, z) from a CARTESIAN_POINT."""
    args = store.get_args(point_id)
    if len(args) >= 2 and isinstance(args[1], list) and len(args[1]) >= 3:
        return (float(args[1][0]), float(args[1][1]), float(args[1][2]))
    return None


def _extract_direction(store: EntityStore, dir_id: int) -> Optional[Tuple[float, float, float]]:
    """Extract (dx, dy, dz) from a DIRECTION."""
    args = store.get_args(dir_id)
    if len(args) >= 2 and isinstance(args[1], list) and len(args[1]) >= 3:
        return (float(args[1][0]), float(args[1][1]), float(args[1][2]))
    return None


def _get_axis2_placement(store: EntityStore, ax2_id: int) -> Optional[Dict]:
    """Extract origin, z_axis, x_axis from AXIS2_PLACEMENT_3D."""
    args = store.get_args(ax2_id)
    if len(args) < 4:
        return None
    origin_id = store.get_ref(args[1])
    axis_id = store.get_ref(args[2])
    ref_dir_id = store.get_ref(args[3])

    origin = _extract_point_coords(store, origin_id) if origin_id else None
    z_axis = _extract_direction(store, axis_id) if axis_id else None
    x_axis = _extract_direction(store, ref_dir_id) if ref_dir_id else None

    if origin and z_axis:
        return {'origin': origin, 'z_axis': z_axis, 'x_axis': x_axis}
    return None


# ═══════════════════════════════════════════════════════════════
# BREP Data Collection
# ═══════════════════════════════════════════════════════════════

def collect_shell_geometry(store: EntityStore, shell_id: int) -> Dict:
    """Collect all geometry data reachable from a CLOSED_SHELL.

    Returns:
        {shell_id, face_ids, reachable_ids, points}
    """
    shell_args = store.get_args(shell_id)
    if len(shell_args) < 2 or not isinstance(shell_args[1], list):
        return {'face_ids': [], 'faces': [], 'points': set()}

    face_id_list = [store.get_ref(item) for item in shell_args[1]]
    face_id_list = [fid for fid in face_id_list if fid is not None]

    reachable = store.collect_reachable(face_id_list)

    points = set()
    for eid in reachable:
        if store.get_type(eid) == 'CARTESIAN_POINT':
            coords = _extract_point_coords(store, eid)
            if coords:
                points.add(coords)

    return {
        'shell_id': shell_id,
        'face_ids': face_id_list,
        'reachable_ids': reachable,
        'points': points
    }


def classify_faces(store: EntityStore, face_ids: List[int]) -> List[Dict]:
    """Classify ADVANCED_FACE entities and extract surface info.

    Returns a list of face dicts with:
        face_id, surface_type, surface_id, radius, ax2,
        outer_loop_id, inner_loop_ids, bounds_ids
    """
    faces = []

    for face_id in face_ids:
        face_args = store.get_args(face_id)
        if len(face_args) < 3:
            continue

        bounds_list_raw = face_args[1]
        bounds_ids = []
        if isinstance(bounds_list_raw, list):
            bounds_ids = [store.get_ref(b) for b in bounds_list_raw]
            bounds_ids = [b for b in bounds_ids if b is not None]

        surface_id = store.get_ref(face_args[2])
        if not surface_id:
            continue

        surface_type = store.get_type(surface_id)
        radius = None
        ax2_id = None

        if surface_type == 'CYLINDRICAL_SURFACE':
            surf_args = store.get_args(surface_id)
            if len(surf_args) >= 3:
                ax2_id = store.get_ref(surf_args[1])
                radius = float(surf_args[2]) if not isinstance(surf_args[2], tuple) and surf_args[2] is not None else 0

        elif surface_type == 'PLANE':
            surf_args = store.get_args(surface_id)
            if len(surf_args) >= 2:
                ax2_id = store.get_ref(surf_args[1])

        ax2 = _get_axis2_placement(store, ax2_id) if ax2_id else None

        # Classify bounds: outer vs inner loops
        outer_loop_id = None
        inner_loop_ids = []

        for bid in bounds_ids:
            btype = store.get_type(bid)
            bargs = store.get_args(bid)
            loop_id = store.get_ref(bargs[1]) if len(bargs) > 1 else None
            if not loop_id:
                continue
            if btype == 'FACE_OUTER_BOUND':
                outer_loop_id = loop_id
            elif btype == 'FACE_BOUND':
                inner_loop_ids.append(loop_id)

        faces.append({
            'face_id': face_id,
            'surface_type': surface_type,
            'surface_id': surface_id,
            'radius': radius,
            'ax2': ax2,
            'outer_loop_id': outer_loop_id,
            'inner_loop_ids': inner_loop_ids,
            'bounds_ids': bounds_ids
        })

    return faces


# ═══════════════════════════════════════════════════════════════
# Loop & Edge Extraction
# ═══════════════════════════════════════════════════════════════

def get_loop_edges(store: EntityStore, loop_id: int) -> List[Dict]:
    """Get all edges in an EDGE_LOOP (in order).

    Each edge dict contains:
        oe_id, ec_id, orientation, same_sense,
        start_pt, end_pt, geom_type, geom_radius, geom_ax2
    """
    loop_args = store.get_args(loop_id)
    if len(loop_args) < 2 or not isinstance(loop_args[1], list):
        return []

    edges = []
    for item in loop_args[1]:
        oe_id = store.get_ref(item)
        if not oe_id:
            continue
        oe_args = store.get_args(oe_id)
        if len(oe_args) < 5:
            continue
        ec_id = store.get_ref(oe_args[3])
        orientation = oe_args[4]
        orient_val = orientation[1] if isinstance(orientation, tuple) and orientation[0] == 'enum' else 'T'
        if not ec_id:
            continue

        ec_args = store.get_args(ec_id)
        if len(ec_args) < 5:
            continue
        start_vp_id = store.get_ref(ec_args[1])
        end_vp_id = store.get_ref(ec_args[2])
        geom_id = store.get_ref(ec_args[3])
        same_sense = ec_args[4]
        same_sense_val = same_sense[1] if isinstance(same_sense, tuple) and same_sense[0] == 'enum' else 'T'

        # Extract start/end points
        start_pt = None
        end_pt = None
        if start_vp_id:
            vp_args = store.get_args(start_vp_id)
            pt_id = store.get_ref(vp_args[1]) if len(vp_args) > 1 else None
            if pt_id:
                start_pt = _extract_point_coords(store, pt_id)
        if end_vp_id:
            vp_args = store.get_args(end_vp_id)
            pt_id = store.get_ref(vp_args[1]) if len(vp_args) > 1 else None
            if pt_id:
                end_pt = _extract_point_coords(store, pt_id)

        # Extract geometry type and params
        geom_type = None
        geom_radius = None
        geom_ax2 = None
        if geom_id:
            geom_type = store.get_type(geom_id)
            gargs = store.get_args(geom_id)
            if geom_type == 'CIRCLE':
                if len(gargs) >= 3:
                    geom_ax2_id = store.get_ref(gargs[1])
                    geom_radius = float(gargs[2]) if gargs[2] is not None else 0
                    geom_ax2 = _get_axis2_placement(store, geom_ax2_id) if geom_ax2_id else None

        edges.append({
            'oe_id': oe_id,
            'ec_id': ec_id,
            'orientation': orient_val,
            'same_sense': same_sense_val,
            'start_pt': start_pt,
            'end_pt': end_pt,
            'geom_type': geom_type,
            'geom_radius': geom_radius,
            'geom_ax2': geom_ax2
        })

    return edges


def get_loop_vertices(edges: List[Dict]) -> List[Tuple[float, float, float]]:
    """Extract ordered vertices from edges (following ORIENTED_EDGE direction)."""
    verts = []
    for e in edges:
        if e['orientation'] == 'T':
            pt = e['start_pt']
        else:
            pt = e['end_pt']
        if pt:
            verts.append(pt)
    return verts


def get_loop_vertices_sampled(edges: List[Dict],
                               segments_per_circle: int = 16) -> List[Tuple[float, float, float]]:
    """Extract vertices, sampling CIRCLE edges into multiple points."""
    verts = []
    for e in edges:
        if e['geom_type'] == 'CIRCLE' and e.get('geom_radius') and e.get('geom_ax2'):
            sampled = _sample_circle_edge(e, segments_per_circle)
            verts.extend(sampled)
        else:
            if e['orientation'] == 'T':
                pt = e['start_pt']
            else:
                pt = e['end_pt']
            if pt:
                verts.append(pt)
    return verts


def _sample_circle_edge(edge: dict, n: int = 16) -> list:
    """Sample a CIRCLE edge into n 3D points along the arc."""
    start = edge['start_pt']
    end = edge['end_pt']
    ax2 = edge['geom_ax2']
    r = edge['geom_radius']
    if not start or not end or not ax2 or r <= 0:
        return []

    o = ax2['origin']
    x_axis = vec_norm(ax2.get('x_axis', (1, 0, 0)))
    z_axis = vec_norm(ax2.get('z_axis', (0, 0, 1)))
    y_axis = vec_cross(z_axis, x_axis)

    def _to_local(pt):
        v = (pt[0] - o[0], pt[1] - o[1], pt[2] - o[2])
        return (vec_dot(v, x_axis), vec_dot(v, y_axis))

    def _to_world(lx, ly):
        return (
            o[0] + lx * x_axis[0] + ly * y_axis[0],
            o[1] + lx * x_axis[1] + ly * y_axis[1],
            o[2] + lx * x_axis[2] + ly * y_axis[2],
        )

    s = _to_local(start)
    e = _to_local(end)
    a1 = math.atan2(s[1], s[0])
    a2 = math.atan2(e[1], e[0])

    if a2 < a1:
        a2 += 2 * math.pi
    arc_angle = a2 - a1

    if arc_angle > math.pi:
        a1, a2 = a2 - 2 * math.pi, a1
        arc_angle = a2 - a1

    if arc_angle < 0:
        arc_angle += 2 * math.pi

    points = []
    for i in range(n):
        angle = a1 + arc_angle * i / n
        lx = r * math.cos(angle)
        ly = r * math.sin(angle)
        points.append(_to_world(lx, ly))

    return points


# ═══════════════════════════════════════════════════════════════
# Geometric Computations
# ═══════════════════════════════════════════════════════════════

def compute_bbox(points: Set[Tuple[float, float, float]]) -> Dict[str, float]:
    """Compute axis-aligned bounding box in mm."""
    if not points:
        return {'x': 0, 'y': 0, 'z': 0, 'dx': 0, 'dy': 0, 'dz': 0}
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return {
        'x': min(xs), 'y': min(ys), 'z': min(zs),
        'dx': max(xs) - min(xs),
        'dy': max(ys) - min(ys),
        'dz': max(zs) - min(zs),
        'max_x': max(xs), 'max_y': max(ys), 'max_z': max(zs)
    }


def compute_face_area(store: EntityStore, face: Dict) -> float:
    """Compute area of a single face (mm²)."""
    surface_type = face['surface_type']
    outer_loop_id = face['outer_loop_id']
    inner_loop_ids = face['inner_loop_ids']

    if not outer_loop_id:
        return 0.0

    outer_edges = get_loop_edges(store, outer_loop_id)
    outer_verts = get_loop_vertices(outer_edges)

    if surface_type == 'PLANE':
        ax2 = face['ax2']
        if not ax2 or not ax2['z_axis'] or not ax2['x_axis'] or len(outer_verts) < 3:
            return 0.0

        o = ax2['origin']
        x_axis = vec_norm(ax2['x_axis'])
        z_axis = vec_norm(ax2['z_axis'])
        y_axis = vec_cross(z_axis, x_axis)

        def to_2d(pt):
            v = vec_sub(pt, o)
            return (vec_dot(v, x_axis), vec_dot(v, y_axis))

        poly2d = [to_2d(v) for v in outer_verts]
        area = abs(_shoe_lace(poly2d))

        for inner_loop_id in inner_loop_ids:
            inner_edges = get_loop_edges(store, inner_loop_id)
            inner_verts = get_loop_vertices(inner_edges)
            if len(inner_verts) >= 3:
                inner2d = [to_2d(v) for v in inner_verts]
                area -= abs(_shoe_lace(inner2d))

        return max(0.0, area)

    elif surface_type == 'CYLINDRICAL_SURFACE':
        radius = face['radius']
        if not radius or radius <= 0:
            return 0.0

        if len(outer_edges) >= 2:
            circ_edges = [e for e in outer_edges if e['geom_type'] == 'CIRCLE']
            if len(circ_edges) == 2 and len(outer_edges) == 2:
                c1 = circ_edges[0].get('geom_ax2')
                c2 = circ_edges[1].get('geom_ax2')
                if c1 and c2:
                    h = vec_len(vec_sub(c1['origin'], c2['origin']))
                    return 2.0 * math.pi * radius * h
            elif len(circ_edges) == 2 and len(outer_edges) == 4:
                c1, c2 = circ_edges[0], circ_edges[1]
                h = 0
                for e in outer_edges:
                    if e['geom_type'] == 'LINE' and e['start_pt'] and e['end_pt']:
                        h = vec_len(vec_sub(e['end_pt'], e['start_pt']))
                        break
                if c1['start_pt'] and c1['end_pt'] and circ_edges[0].get('geom_ax2'):
                    ax2 = circ_edges[0]['geom_ax2']
                    angle = _compute_arc_angle(c1['start_pt'], c1['end_pt'], ax2)
                    return radius * angle * h
            else:
                outer_verts = get_loop_vertices(outer_edges)
                if len(outer_verts) >= 3:
                    heights = []
                    for i in range(len(outer_verts)):
                        v1 = outer_verts[i]
                        v2 = outer_verts[(i + 1) % len(outer_verts)]
                        heights.append(vec_len(vec_sub(v2, v1)))
                    if heights:
                        return 2.0 * math.pi * radius * max(heights)
        return 0.0

    return 0.0


def _shoe_lace(poly: List[Tuple[float, float]]) -> float:
    """2D polygon area via the Shoelace formula."""
    n = len(poly)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return area / 2.0


def _compute_arc_angle(start_pt, end_pt, ax2) -> float:
    """Compute arc angle in radians from start/end points and axis placement."""
    if not start_pt or not end_pt or not ax2:
        return math.pi
    o = ax2['origin']
    x_axis = vec_norm(ax2.get('x_axis', (1, 0, 0)))
    z_axis = vec_norm(ax2.get('z_axis', (0, 0, 1)))
    y_axis = vec_cross(z_axis, x_axis)

    def project(pt):
        v = vec_sub(pt, o)
        return (vec_dot(v, x_axis), vec_dot(v, y_axis))

    p1 = project(start_pt)
    p2 = project(end_pt)
    a1 = math.atan2(p1[1], p1[0])
    a2 = math.atan2(p2[1], p2[0])
    diff = abs(a2 - a1)
    return min(diff, 2 * math.pi - diff)


def compute_outer_profile(store: EntityStore, faces: List[Dict]) -> float:
    """Compute outer profile cutting length = perimeter of largest plane face (mm)."""
    plane_faces = [f for f in faces if f['surface_type'] == 'PLANE' and f['outer_loop_id']]
    if not plane_faces:
        return 0.0

    main_face = max(plane_faces, key=lambda f: f.get('_area') or compute_face_area(store, f))
    if not main_face:
        return 0.0

    edges = get_loop_edges(store, main_face['outer_loop_id'])
    return compute_perimeter(edges)


def compute_perimeter(edges: List[Dict]) -> float:
    """Compute total perimeter length of a list of edges (mm)."""
    total = 0.0
    for e in edges:
        if e['start_pt'] and e['end_pt']:
            chord = vec_len(vec_sub(e['end_pt'], e['start_pt']))
            if e['geom_type'] == 'CIRCLE' and e.get('geom_radius'):
                r = e['geom_radius']
                if chord > 0 and r > 0:
                    half_angle = math.asin(min(1.0, chord / (2 * r)))
                    total += 2 * r * half_angle
                else:
                    total += math.pi * r
            else:
                total += chord
    return total


def compute_hole_inventory(faces: List[Dict]) -> List[Dict]:
    """Group cylindrical faces by diameter, return sorted list.

    Returns [{diameter_mm, radius_mm, count}, ...].
    """
    diameter_counts = defaultdict(int)
    for f in faces:
        if f['surface_type'] == 'CYLINDRICAL_SURFACE' and f['radius']:
            d = round(2.0 * f['radius'], 2)
            diameter_counts[d] += 1

    result = []
    for d in sorted(diameter_counts.keys()):
        result.append({
            'diameter_mm': d,
            'radius_mm': round(d / 2.0, 2),
            'count': diameter_counts[d]
        })
    return result


def compute_pierce_count(store: EntityStore, faces: List[Dict]) -> int:
    """Count pierce holes = inner loops (FACE_BOUND) on the largest plane face."""
    plane_faces = [f for f in faces if f['surface_type'] == 'PLANE' and f['outer_loop_id']]
    if not plane_faces:
        return 0
    main_face = max(plane_faces, key=lambda f: f.get('_area') or compute_face_area(store, f))
    return len(main_face.get('inner_loop_ids', []))


def compute_bend_count(store: EntityStore, faces: List[Dict]) -> int:
    """Detect bend features in sheet metal.

    A bend in STEP BREP is:
      - A CYLINDRICAL_SURFACE (bend radius zone)
      - Between two PLANE faces whose normals are ~90° apart
      - Radius ≤ 10 mm (excludes large holes)
    """
    plane_faces = {f['face_id']: f for f in faces if f['surface_type'] == 'PLANE'}
    cyl_faces = [f for f in faces if f['surface_type'] == 'CYLINDRICAL_SURFACE']

    if not plane_faces or not cyl_faces:
        return 0

    # Build edge → plane mapping
    edge_to_plane = defaultdict(set)
    for pid, pf in plane_faces.items():
        if pf['outer_loop_id']:
            for e in get_loop_edges(store, pf['outer_loop_id']):
                if e['ec_id']:
                    edge_to_plane[e['ec_id']].add(pid)
        for il_id in pf.get('inner_loop_ids', []):
            for e in get_loop_edges(store, il_id):
                if e['ec_id']:
                    edge_to_plane[e['ec_id']].add(pid)

    bends = 0
    for cf in cyl_faces:
        radius = cf.get('radius')
        if not radius or radius <= 0 or radius > 10.0:
            continue

        if not cf['outer_loop_id']:
            continue
        cyl_edges = get_loop_edges(store, cf['outer_loop_id'])
        adjacent_planes = set()
        for e in cyl_edges:
            if e['ec_id'] and e['ec_id'] in edge_to_plane:
                adjacent_planes |= edge_to_plane[e['ec_id']]

        if len(adjacent_planes) >= 2:
            plane_list = [plane_faces[pid] for pid in adjacent_planes if pid in plane_faces]
            if len(plane_list) >= 2:
                found = False
                for i in range(len(plane_list)):
                    for j in range(i + 1, len(plane_list)):
                        if plane_list[i]['ax2'] and plane_list[j]['ax2']:
                            n1 = vec_norm(plane_list[i]['ax2']['z_axis'])
                            n2 = vec_norm(plane_list[j]['ax2']['z_axis'])
                            angle = angle_between(n1, n2)
                            if 85.0 <= angle <= 95.0:
                                bends += 1
                                found = True
                                break
                    if found:
                        break

    return bends


def compute_thickness(faces: List[Dict]) -> float:
    """Estimate sheet thickness from parallel plane distances (mm).

    Method: find all parallel plane pairs, compute origin-to-origin distance
    along the normal, take the minimum non-zero value.
    Falls back to bbox min dimension for flat parts.
    """
    plane_faces = [f for f in faces if f['surface_type'] == 'PLANE' and f['ax2']]
    if len(plane_faces) < 2:
        return 0.0

    distances = []
    for i in range(len(plane_faces)):
        for j in range(i + 1, len(plane_faces)):
            n1 = vec_norm(plane_faces[i]['ax2']['z_axis'])
            n2 = vec_norm(plane_faces[j]['ax2']['z_axis'])
            dot = abs(vec_dot(n1, n2))
            if dot > 0.999:  # parallel (same or opposite direction)
                o1 = plane_faces[i]['ax2']['origin']
                o2 = plane_faces[j]['ax2']['origin']
                dist = abs(vec_dot(vec_sub(o2, o1), n1))
                distances.append(dist)

    if not distances:
        return 0.0

    valid = [d for d in distances if d > 0.01]
    return min(valid) if valid else 0.0


# ═══════════════════════════════════════════════════════════════
# 2D Contour Extraction
# ═══════════════════════════════════════════════════════════════

def _project_loop_to_2d(store, loop_id, origin, u, v):
    """Project 3D loop vertices to a 2D local coordinate system."""
    edges = get_loop_edges(store, loop_id)
    if not edges:
        return []
    pts_3d = get_loop_vertices_sampled(edges)
    if len(pts_3d) < 3:
        return []
    result = []
    for pt in pts_3d:
        dx = pt[0] - origin[0]
        dy = pt[1] - origin[1]
        dz = pt[2] - origin[2]
        x = dx * u[0] + dy * u[1] + dz * u[2]
        y = dx * v[0] + dy * v[1] + dz * v[2]
        result.append((round(x, 3), round(y, 3)))
    return result


def _build_face_uv(pts_3d, normal_hint=None):
    """Build a 2D local coordinate system (origin, u, v) from 3D vertices."""
    if len(pts_3d) < 3:
        return None, None, None

    normal = normal_hint
    if not normal or all(abs(c) < 1e-9 for c in normal):
        p0, p1, p2 = pts_3d[:3]
        v1 = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        v2 = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
        normal = (
            v1[1] * v2[2] - v1[2] * v2[1],
            v1[2] * v2[0] - v1[0] * v2[2],
            v1[0] * v2[1] - v1[1] * v2[0]
        )
        n_len = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2)
        if n_len < 1e-9:
            return None, None, None
        normal = (normal[0] / n_len, normal[1] / n_len, normal[2] / n_len)

    if abs(normal[0]) < 0.9:
        ref = (1, 0, 0)
    else:
        ref = (0, 1, 0)
    u = (
        normal[1] * ref[2] - normal[2] * ref[1],
        normal[2] * ref[0] - normal[0] * ref[2],
        normal[0] * ref[1] - normal[1] * ref[0]
    )
    u_len = math.sqrt(u[0] ** 2 + u[1] ** 2 + u[2] ** 2)
    u = (u[0] / u_len, u[1] / u_len, u[2] / u_len)
    v = (
        normal[1] * u[2] - normal[2] * u[1],
        normal[2] * u[0] - normal[0] * u[2],
        normal[0] * u[1] - normal[1] * u[0]
    )
    origin = pts_3d[0]
    return origin, u, v


def extract_contour_2d(store: EntityStore, faces: List[Dict]) -> dict | None:
    """Extract 2D contour (outer + holes) from the largest plane face.

    Returns:
        {'outer': [(x,y), ...], 'holes': [[(x,y), ...], ...]} or None
    """
    plane_faces = [f for f in faces
                   if f['surface_type'] == 'PLANE' and f.get('outer_loop_id')]
    if not plane_faces:
        return None

    def _face_area(face):
        if '_area' not in face:
            face['_area'] = compute_face_area(store, face)
        return face['_area']

    main_face = max(plane_faces, key=_face_area)

    outer_edges = get_loop_edges(store, main_face['outer_loop_id'])
    if not outer_edges:
        return None
    outer_pts = get_loop_vertices(outer_edges)
    if len(outer_pts) < 3:
        return None

    origin, u, v = _build_face_uv(outer_pts, main_face.get('normal'))
    if origin is None:
        return None

    outer_2d = _project_loop_to_2d(store, main_face['outer_loop_id'], origin, u, v)
    if len(outer_2d) < 3:
        return None

    holes = []
    for il_id in main_face.get('inner_loop_ids', []):
        hole_pts = _project_loop_to_2d(store, il_id, origin, u, v)
        if len(hole_pts) >= 3:
            holes.append(hole_pts)

    return {'outer': outer_2d, 'holes': holes}
