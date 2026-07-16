#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
step-parser: Pure Python STEP File Parser for Sheet Metal Geometry
===================================================================

Parse ISO 10303-21 (STEP P21) CAD files and extract BREP geometry data:
bounding box, surface area, hole inventory, bend detection, thickness,
and more — with zero external dependencies.

Quick Start
-----------
    from step_parser import parse, analyze

    # Parse and validate
    store = parse('part.stp')

    # Extract assembly structure
    assembly = store.extract_assembly()

    # Analyze geometry for each part
    for part in assembly['parts']:
        result = analyze(store, part)
        print(result['name'], result['bbox_mm']['label'])

See the README and examples/ directory for more.
"""

from .parser import (
    parse_step_file,
    validate_step_file,
    EntityStore,
    CAD_SIGNATURES,
    REQUIRED_ENTITIES,
    RECOMMENDED_ENTITIES,
)

from .assembly import extract_assembly

from .geometry import (
    # Vector math
    vec_sub, vec_add, vec_dot, vec_cross, vec_len, vec_norm, angle_between,
    # BREP collection
    collect_shell_geometry, classify_faces,
    # Loop & edge
    get_loop_edges, get_loop_vertices, get_loop_vertices_sampled,
    # Computations
    compute_bbox, compute_face_area, compute_outer_profile, compute_perimeter,
    compute_hole_inventory, compute_pierce_count, compute_bend_count,
    compute_thickness, extract_contour_2d,
)

from .report import analyze_part, print_report, MATERIAL_DENSITY

# Convenience wrappers


def parse(filepath: str) -> EntityStore:
    """Parse a STEP file and return an EntityStore.

    This is the main entry point. It reads the file, parses all entities,
    and builds the reference graph.

    Args:
        filepath: Path to .stp or .step file.

    Returns:
        EntityStore with lazy-parsed entities and reference graph.

    Example:
        store = parse('part.stp')
        print(f"Parsed {len(store._entities)} entities")
    """
    entities = parse_step_file(filepath)
    return EntityStore(entities)


def validate(filepath: str) -> dict:
    """Validate a STEP file before full parsing.

    Args:
        filepath: Path to .stp or .step file.

    Returns:
        Validation report dict with status, errors, warnings, info, stats.

    Example:
        report = validate('part.stp')
        if report['status'] == 'fail':
            print(report['errors'])
    """
    return validate_step_file(filepath)


def analyze(store: EntityStore, part_info: dict) -> dict:
    """Analyze a single part's geometry.

    Args:
        store: EntityStore from parse().
        part_info: Part dict from extract_assembly()['parts'].

    Returns:
        Dict with all geometry properties (bbox, area, holes, bends, etc.).
    """
    return analyze_part(store, part_info)


# Version
__version__ = '1.0.0'
__all__ = [
    # Main API
    'parse', 'validate', 'analyze',
    # Core classes
    'EntityStore',
    # Parsing
    'parse_step_file', 'validate_step_file',
    # Assembly
    'extract_assembly',
    # Analysis
    'analyze_part', 'print_report',
    # Geometry
    'collect_shell_geometry', 'classify_faces',
    'get_loop_edges', 'get_loop_vertices', 'get_loop_vertices_sampled',
    'compute_bbox', 'compute_face_area', 'compute_outer_profile',
    'compute_perimeter', 'compute_hole_inventory', 'compute_pierce_count',
    'compute_bend_count', 'compute_thickness', 'extract_contour_2d',
    # Vector math
    'vec_sub', 'vec_add', 'vec_dot', 'vec_cross', 'vec_len', 'vec_norm',
    'angle_between',
    # Constants
    'CAD_SIGNATURES', 'REQUIRED_ENTITIES', 'RECOMMENDED_ENTITIES',
    'MATERIAL_DENSITY',
    # Version
    '__version__',
]
