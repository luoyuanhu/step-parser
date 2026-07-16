#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Part Analysis & Reporting
==========================
Per-part geometry analysis, console report generation.
"""

import sys
from typing import Dict, List, Optional, Any

from .parser import EntityStore
from .geometry import (
    collect_shell_geometry,
    classify_faces,
    compute_bbox,
    compute_face_area,
    compute_outer_profile,
    compute_hole_inventory,
    compute_pierce_count,
    compute_bend_count,
    compute_thickness,
    extract_contour_2d,
)

# Material density (kg/m³) — STEP files don't include material info.
# Default is SPCC (common cold-rolled steel for sheet metal).
MATERIAL_DENSITY = {
    'SPCC': 7850,
    'SPHC': 7850,
    'SUS304': 7930,
}


def analyze_part(store: EntityStore, part_info: Dict) -> Dict:
    """Run full geometry analysis on a single part.

    Args:
        store: EntityStore with parsed STEP entities.
        part_info: Dict from extract_assembly() with keys:
                   product_id, name, description, shell_id, instances.

    Returns:
        Dict with all computed geometry properties plus original part_info fields.
    """
    shell_id = part_info.get('shell_id')
    if not shell_id:
        return {**part_info, 'error': 'CLOSED_SHELL not found'}

    # Collect geometry
    geom = collect_shell_geometry(store, shell_id)
    faces = classify_faces(store, geom['face_ids'])

    # Bounding box
    bbox = compute_bbox(geom['points'])

    # Face area cache
    def face_area(f):
        if '_area' not in f:
            f['_area'] = compute_face_area(store, f)
        return f['_area']

    # Surface area
    total_surface_area = sum(face_area(f) for f in faces)

    # Outer profile cutting length
    outer_profile = compute_outer_profile(store, faces)

    # Hole inventory
    holes = compute_hole_inventory(faces)

    # Pierce count
    pierce_count = compute_pierce_count(store, faces)

    # Bend count
    bends = compute_bend_count(store, faces)

    # Thickness
    thickness = compute_thickness(faces)
    if thickness < 0.1:
        bbox_dims = sorted([bbox['dx'], bbox['dy'], bbox['dz']])
        thickness = bbox_dims[0]

    # Blank area estimation
    plane_areas = [face_area(f) for f in faces
                   if f['surface_type'] == 'PLANE' and f['outer_loop_id']]
    plane_areas.sort(reverse=True)

    if bends == 0 and plane_areas:
        if len(plane_areas) >= 2 and abs(plane_areas[0] - plane_areas[1]) / plane_areas[0] < 0.1:
            blank_area = (plane_areas[0] + plane_areas[1]) / 2
        else:
            blank_area = plane_areas[0]
    else:
        blank_area = sum(plane_areas)

    # Part type
    part_type = 'bend' if bends > 0 else 'flat'

    # Weight (default SPCC)
    density = MATERIAL_DENSITY.get('SPCC', 7850)
    weight_single = blank_area / 1e6 * (thickness / 1000) * density
    weight_total = weight_single * part_info.get('instances', 1)

    return {
        **part_info,
        'type': part_type,
        'bbox_mm': {
            'width': round(bbox['dx'], 1),
            'depth': round(bbox['dy'], 1),
            'height': round(bbox['dz'], 1),
            'label': f"{round(bbox['dx'])}×{round(bbox['dy'])}×{round(bbox['dz'])}"
        },
        'surface_area_m2': round(total_surface_area / 1e6, 6),
        'outer_profile_m': round(outer_profile / 1000, 4),
        'blank_area_m2': round(blank_area / 1e6, 6),
        'thickness_mm': round(thickness, 1),
        'bend_count': bends,
        'pierce_count': pierce_count,
        'holes': holes,
        'face_count': len(faces),
        'contour_2d': extract_contour_2d(store, faces),
        'plane_face_count': sum(1 for f in faces if f['surface_type'] == 'PLANE'),
        'cylindrical_face_count': sum(1 for f in faces if f['surface_type'] == 'CYLINDRICAL_SURFACE'),
        'weight_single_kg': round(weight_single, 2),
        'weight_total_kg': round(weight_total, 2),
        'error': None
    }


def print_report(results: Dict):
    """Print a formatted Chinese-language console report."""
    parts = results['parts']
    print()
    print("=" * 80)
    print(f"  STEP File: {results.get('file', '?')}")
    print(f"  Assembly: {results.get('assembly', '?')}  |  "
          f"Part types: {len(parts)}  |  Total instances: {results.get('total_instances', 0)}")
    print(f"  Unit: mm")
    print("=" * 80)

    for i, part in enumerate(parts):
        print(f"\n{'─' * 60}")
        print(f"  [{i + 1}] {part['name']}  (PRODUCT #{part['product_id']})")
        print(f"      Instances: {part['instances']}  |  "
              f"Type: {'Bend part' if part.get('type') == 'bend' else 'Flat part'}")
        if part.get('error'):
            print(f"      ERROR: {part['error']}")
            continue

        bbox = part.get('bbox_mm', {})
        print(f"      Bounding box: {bbox.get('label', '?')} mm")
        print(f"      Thickness: {part.get('thickness_mm', '?')} mm")
        print(f"      Weight (single): {part.get('weight_single_kg', 0):.2f} kg  |  "
              f"Total: {part.get('weight_total_kg', 0):.2f} kg")
        print(f"      Surface area: {part.get('surface_area_m2', 0):.4f} m²")
        print(f"      Blank area: {part.get('blank_area_m2', 0):.4f} m²")
        print(f"      Outer profile: {part.get('outer_profile_m', 0):.4f} m")
        print(f"      Bends: {part.get('bend_count', 0)}")
        print(f"      Pierce holes: {part.get('pierce_count', 0)}")
        print(f"      Total faces: {part.get('face_count', 0)}  "
              f"(planes: {part.get('plane_face_count', 0)}, "
              f"cylindrical: {part.get('cylindrical_face_count', 0)})")

        holes = part.get('holes', [])
        if holes:
            print(f"      Holes (by diameter):")
            for h in holes:
                d = h['diameter_mm']
                cnt = h['count']
                tag = _guess_hole_type(d)
                print(f"        Ø{d:.1f}mm × {cnt}  {tag}")
        else:
            print(f"      Holes: none")

    # Summary
    print(f"\n{'=' * 80}")
    print(f"  Summary")
    total_surface = sum(p.get('surface_area_m2', 0) * p.get('instances', 1) for p in parts)
    total_cut = sum(p.get('outer_profile_m', 0) * p.get('instances', 1) for p in parts)
    total_pierce = sum(p.get('pierce_count', 0) * p.get('instances', 1) for p in parts)
    total_bends = sum(p.get('bend_count', 0) * p.get('instances', 1) for p in parts)
    total_blank = sum(p.get('blank_area_m2', 0) * p.get('instances', 1) for p in parts)
    print(f"  Total surface area: {total_surface:.4f} m²")
    print(f"  Total cutting length: {total_cut:.4f} m")
    print(f"  Total pierce holes: {total_pierce}")
    print(f"  Total bends: {total_bends}")
    print(f"  Total blank area: {total_blank:.4f} m²")
    total_weight = sum(p.get('weight_total_kg', 0) for p in parts)
    print(f"  Total net weight: {total_weight:.2f} kg")
    print("=" * 80)


def _guess_hole_type(diameter_mm: float) -> str:
    """Guess the likely manufacturing process for a given hole diameter.

    Based on common sheet metal tap drill and PEM nut hole sizes.
    This is a heuristic — always verify against actual specifications.
    """
    MAP = {
        2.5: '→ possibly: M3 tap drill',
        3.2: '→ possibly: M4 tap drill',
        3.3: '→ possibly: M4 tap drill',
        4.2: '→ possibly: M5 tap / M3 PEM nut',
        5.0: '→ possibly: M6 tap drill',
        5.5: '→ possibly: M4 PEM nut',
        6.0: '→ possibly: M5 PEM nut',
        6.8: '→ possibly: M8 tap drill',
        7.0: '→ possibly: M8 tap drill',
        8.5: '→ possibly: M10 tap drill',
        10.0: '→ clearance hole',
        11.0: '→ possibly: M8 PEM nut',
        14.0: '→ clearance hole',
        28.0: '→ clearance hole (Ø28)',
        29.0: '→ clearance hole (Ø29)',
    }
    best = None
    best_diff = 999
    for k, v in MAP.items():
        diff = abs(diameter_mm - k)
        if diff < best_diff:
            best_diff = diff
            best = v
    if best_diff < 0.5:
        return best
    return '(unclassified)'
