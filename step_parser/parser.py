#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STEP P21 File Parser & Validator
=================================
Pure-Python ISO 10303-21 (STEP Physical File) parser with recursive-descent
parameter parsing, entity store with reference graph, and pre-parse validation.

Supports AP203, AP214, AP242 schemas from all major CAD systems.
Zero external dependencies — standard library only.
"""

import os
import re
import sys
from collections import defaultdict
from typing import Dict, List, Set, Tuple, Optional, Any, Union

# ═══════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════

REQUIRED_ENTITIES = [
    'PRODUCT',
    'CLOSED_SHELL',
    'MANIFOLD_SOLID_BREP',
    'ADVANCED_FACE',
    'CARTESIAN_POINT',
]

RECOMMENDED_ENTITIES = [
    'CYLINDRICAL_SURFACE',
    'PLANE',
    'EDGE_CURVE',
    'DIRECTION',
    'AXIS2_PLACEMENT_3D',
]

WARNING_ENTITIES = {
    'FACETED_BREP': 'Faceted model (inexact surfaces) — area/perimeter precision may be poor',
    'TRIANGULATED_FACE': 'Triangulated faces — hole type detection unavailable',
    'POLY_LOOP': 'Poly loop (possibly from STL conversion)',
    'SHELL_BASED_SURFACE_MODEL': 'Non-solid model — volume calculation unavailable',
}

CAD_SIGNATURES = {
    'CREO PARAMETRIC BY PTC': 'Creo Parametric (PTC)',
    'SOLIDWORKS': 'SolidWorks (Dassault)',
    'NX': 'NX (Siemens)',
    'CATIA': 'CATIA (Dassault)',
    'AUTODESK INVENTOR': 'Inventor (Autodesk)',
    'FREECAD': 'FreeCAD',
    'SOLID EDGE': 'Solid Edge (Siemens)',
    'FUSION': 'Fusion 360 (Autodesk)',
    'ONSHAPE': 'Onshape (PTC)',
}


def validate_step_file(filepath: str) -> dict:
    """Validate a STEP file before full parsing.

    Checks format, required entities, CAD source, schema, units, and
    potential issues. Returns a report dict with status, errors, warnings,
    info messages, and entity statistics.

    Args:
        filepath: Path to the .stp / .step file.

    Returns:
        dict with keys: status ('ok'|'warn'|'fail'), errors, warnings,
        info, stats.
    """
    report = {
        'status': 'ok',
        'errors': [],
        'warnings': [],
        'info': [],
        'stats': {},
    }

    # ── 1. File existence & size ──
    if not os.path.exists(filepath):
        report['status'] = 'fail'
        report['errors'].append(f'File not found: {filepath}')
        return report

    file_size = os.path.getsize(filepath)
    if file_size == 0:
        report['status'] = 'fail'
        report['errors'].append('File is empty')
        return report

    report['stats']['file_size_kb'] = round(file_size / 1024, 1)

    with open(filepath, 'r', encoding='utf-8-sig', errors='replace') as f:
        text = f.read()

    # ── 2. ISO-10303-21 format ──
    if not text.startswith('ISO-10303-21'):
        report['status'] = 'fail'
        report['errors'].append('Not an ISO-10303-21 (STEP P21) file')
        return report

    # ── 3. Section check ──
    for section in ['HEADER', 'DATA', 'ENDSEC']:
        if section not in text:
            report['status'] = 'fail'
            report['errors'].append(f'Missing {section} section')
            return report

    # ── 4. Header info ──
    hdr_match = re.search(r"FILE_NAME\('([^']*)','([^']*)',", text)
    if hdr_match:
        report['info'].append(f"File name: {hdr_match.group(1)}")
        report['info'].append(f"Export date: {hdr_match.group(2)}")

    # CAD source detection
    cad_found = 'Unknown'
    for sig, name in CAD_SIGNATURES.items():
        if sig in text.upper():
            cad_found = name
            break

    org_match = re.search(r"FILE_NAME\('[^']*','[^']*',\('[^']*'\),\('([^']*)'", text)
    if org_match:
        org = org_match.group(1)
        if cad_found == 'Unknown' and org.strip():
            for sig, name in CAD_SIGNATURES.items():
                if sig in org.upper():
                    cad_found = name
                    break

    report['info'].append(f"CAD source: {cad_found}")

    # Schema
    schema_match = re.search(r"FILE_SCHEMA\(\('([^']*)'\)\)", text)
    if schema_match:
        schema = schema_match.group(1)
        report['info'].append(f"Schema: {schema}")
        if 'CONFIG_CONTROL_DESIGN' in schema:
            report['info'].append('Protocol: AP203 (configuration control)')
        elif 'AUTOMOTIVE_DESIGN' in schema:
            report['info'].append('Protocol: AP214 (automotive design)')
        elif 'MANAGED_MODEL_BASED' in schema:
            report['info'].append('Protocol: AP242 (model-based definition)')

    # ── 5. Quick entity count (regex) ──
    entity_counts = {}
    for match in re.finditer(r'#\d+\s*=\s*(\w+)\(', text):
        etype = match.group(1)
        entity_counts[etype] = entity_counts.get(etype, 0) + 1

    report['stats']['total_entities'] = sum(entity_counts.values())
    report['stats']['unique_types'] = len(entity_counts)

    # ── 6. Required entity check ──
    for ent in REQUIRED_ENTITIES:
        count = entity_counts.get(ent, 0)
        if count == 0:
            report['errors'].append(f'Missing required entity: {ent}')
            report['status'] = 'fail'
        else:
            report['stats'][ent] = count

    for ent in RECOMMENDED_ENTITIES:
        count = entity_counts.get(ent, 0)
        report['stats'][ent] = count

    # ── 7. Problem entity detection ──
    for ent, desc in WARNING_ENTITIES.items():
        if ent in entity_counts:
            report['warnings'].append(f'{desc} ({entity_counts[ent]} {ent})')
            if report['status'] == 'ok':
                report['status'] = 'warn'

    # ── 8. Assembly structure check ──
    nauo_count = entity_counts.get('NEXT_ASSEMBLY_USAGE_OCCURRENCE', 0)
    product_count = entity_counts.get('PRODUCT', 0)

    if product_count == 0:
        report['errors'].append('No PRODUCT entities — cannot identify parts')
        report['status'] = 'fail'
    elif product_count == 1:
        report['info'].append('Single-part file (not an assembly)')

    if product_count > 1 and nauo_count == 0:
        report['warnings'].append(
            f'{product_count} PRODUCTs but no NEXT_ASSEMBLY_USAGE_OCCURRENCE'
            ' — will attempt to infer parts from PRODUCT definition chain'
        )
        if report['status'] == 'ok':
            report['status'] = 'warn'

    report['stats']['NAUO'] = nauo_count
    report['stats']['PRODUCT'] = product_count

    # ── 9. Sheet metal feature check ──
    cyl_count = entity_counts.get('CYLINDRICAL_SURFACE', 0)
    plane_count = entity_counts.get('PLANE', 0)
    shell_count = entity_counts.get('CLOSED_SHELL', 0)

    if shell_count == 0:
        report['errors'].append('No CLOSED_SHELL — cannot extract geometry')
        report['status'] = 'fail'

    report['info'].append(
        f"BREP shells: {shell_count} | "
        f"Planes: {plane_count} | Cylindrical surfaces (holes): {cyl_count}"
    )

    if cyl_count == 0:
        report['info'].append('No cylindrical surfaces — part may have no drilled holes')
    if plane_count < shell_count * 2:
        report['warnings'].append('Low plane count — may not be a sheet metal part')

    # ── 10. Unit check ──
    unit_match = re.search(r'SI_UNIT\(\.(\w+)\.\s*,\s*\.(\w+)\.\)', text)
    if unit_match:
        prefix, base = unit_match.group(1), unit_match.group(2)
        unit_map = {
            ('MILLI', 'METRE'): 'mm',
            ('CENTI', 'METRE'): 'cm',
            ('METRE', 'METRE'): 'm',
            ('INCH', 'INCH'): 'inch',
        }
        unit = unit_map.get((prefix, base), f'{prefix}.{base}')
        report['info'].append(f"Unit: {unit}")
        if unit not in ('mm',):
            report['warnings'].append(f'Non-millimeter unit ({unit}) — values may need conversion')

    # ── 11. Summary ──
    if report['status'] == 'ok':
        report['info'].append('File is suitable for sheet metal geometry analysis')
    elif report['status'] == 'warn':
        report['info'].append('File can be analyzed but has noteworthy issues')
    else:
        report['info'].append('File does not meet minimum requirements')

    return report


# ═══════════════════════════════════════════════════════════════
# STEP P21 Parser
# ═══════════════════════════════════════════════════════════════

def parse_step_file(filepath: str) -> Dict[int, dict]:
    """Parse a STEP P21 file and return an entity index.

    Reads the DATA section, extracts every entity instance, and returns
    a dict mapping entity_id → {type, raw, _parsed}.

    Args:
        filepath: Path to the .stp / .step file.

    Returns:
        Dict[int, dict]: {entity_id: {type, raw, _parsed}}
    """
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        text = f.read()

    # Locate DATA section
    data_start = text.find('DATA;')
    if data_start == -1:
        raise ValueError('DATA section not found')
    data_end = text.find('ENDSEC;', data_start)
    if data_end == -1:
        raise ValueError('ENDSEC not found')
    data = text[data_start + 5:data_end]

    entities = {}
    i = 0
    n = len(data)
    entity_count = 0

    while i < n:
        # Skip whitespace
        while i < n and data[i] in ' \t\r\n':
            i += 1
        if i >= n or data[i:i + 6] == 'ENDSEC':
            break

        # Entity must start with #
        if data[i] != '#':
            i += 1
            continue

        i += 1  # skip #

        # Read entity ID
        id_start = i
        while i < n and data[i].isdigit():
            i += 1
        entity_id = int(data[id_start:i])

        # Skip whitespace and =
        while i < n and data[i] in ' \t\r\n':
            i += 1
        if i >= n or data[i] != '=':
            continue
        i += 1  # skip =

        # Read type name
        while i < n and data[i] in ' \t\r\n':
            i += 1
        type_start = i
        while i < n and (data[i].isalnum() or data[i] == '_'):
            i += 1
        type_name = data[type_start:i]

        # Skip whitespace to (
        while i < n and data[i] in ' \t\r\n':
            i += 1
        if i >= n or data[i] != '(':
            continue

        # Read parameters (track bracket nesting)
        depth = 1
        args_start = i + 1
        i += 1

        while i < n and depth > 0:
            c = data[i]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            elif c == "'":
                # Skip quoted string (handle '' escaping)
                i += 1
                while i < n:
                    if data[i] == "'":
                        if i + 1 < n and data[i + 1] == "'":
                            i += 2
                            continue
                        break
                    i += 1
            i += 1

        args_raw = data[args_start:i - 1]

        # Skip ; and trailing whitespace
        while i < n and data[i] in ' \t\r\n;':
            i += 1

        entities[entity_id] = {
            'type': type_name,
            'raw': args_raw,
            '_parsed': None
        }
        entity_count += 1

    return entities


# ── Recursive-descent argument parser ──────────────────────────

def _parse_args(raw: str) -> List[Any]:
    """Recursive-descent parser for STEP entity parameter lists.

    Returns a list where each item may be:
      - str: string value
      - int: integer
      - float: float
      - None: $ (null)
      - ('ref', int): entity reference #N
      - ('enum', str): enumeration .VALUE.
      - ('wildcard',): wildcard *
      - ('compound', type_name, [args]): embedded compound type
      - list: nested list
    """
    results = []
    i = 0
    n = len(raw)

    while i < n:
        while i < n and raw[i] in ' \t\r\n,':
            i += 1
        if i >= n:
            break

        c = raw[i]

        if c == "'":
            i += 1
            s = []
            while i < n:
                if raw[i] == "'":
                    if i + 1 < n and raw[i + 1] == "'":
                        s.append("'")
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    s.append(raw[i])
                    i += 1
            results.append(''.join(s))

        elif c == '#':
            i += 1
            num_start = i
            while i < n and raw[i].isdigit():
                i += 1
            results.append(('ref', int(raw[num_start:i])))

        elif c == '.':
            i += 1
            enum_start = i
            while i < n and raw[i] != '.':
                i += 1
            enum_val = raw[enum_start:i]
            i += 1
            results.append(('enum', enum_val))

        elif c == '$':
            results.append(None)
            i += 1

        elif c == '*':
            results.append(('wildcard',))
            i += 1

        elif c == '(':
            i += 1
            depth = 1
            list_start = i
            while i < n and depth > 0:
                if raw[i] == "'":
                    i += 1
                    while i < n:
                        if raw[i] == "'":
                            if i + 1 < n and raw[i + 1] == "'":
                                i += 2
                                continue
                            break
                        i += 1
                elif raw[i] == '(':
                    depth += 1
                elif raw[i] == ')':
                    depth -= 1
                i += 1
            results.append(_parse_args(raw[list_start:i - 1]))

        elif c == '-' or c == '+' or c.isdigit():
            num_start = i
            i += 1
            while i < n and raw[i] in '0123456789.+-Ee':
                i += 1
            num_str = raw[num_start:i]
            try:
                if '.' in num_str or 'E' in num_str or 'e' in num_str:
                    results.append(float(num_str))
                else:
                    results.append(int(num_str))
            except ValueError:
                results.append(num_str)

        elif c.isalpha() or c == '_':
            # Identifier or compound type like LENGTH_MEASURE(2.0181E-1)
            token_start = i
            while i < n and (raw[i].isalnum() or raw[i] == '_'):
                i += 1
            token = raw[token_start:i]
            # Skip whitespace
            while i < n and raw[i] in ' \t\r\n':
                i += 1
            if i < n and raw[i] == '(':
                i += 1
                depth = 1
                inner_start = i
                while i < n and depth > 0:
                    if raw[i] == "'":
                        i += 1
                        while i < n:
                            if raw[i] == "'":
                                if i + 1 < n and raw[i + 1] == "'":
                                    i += 2
                                    continue
                                break
                            i += 1
                    elif raw[i] == '(':
                        depth += 1
                    elif raw[i] == ')':
                        depth -= 1
                    i += 1
                inner_args = _parse_args(raw[inner_start:i - 1])
                results.append(('compound', token, inner_args))
            else:
                results.append(token)

        else:
            # Unknown character, skip
            i += 1

    return results


# ═══════════════════════════════════════════════════════════════
# Entity Store
# ═══════════════════════════════════════════════════════════════

class EntityStore:
    """Entity storage with lazy parsing and reference-graph queries.

    Provides:
    - Lazy argument parsing (only parses when accessed)
    - get_type(), get_args(), get_type_and_args() accessors
    - resolve() — recursively dereference entity references
    - collect_reachable() — BFS from starting IDs
    - Reference graph: _refs (outgoing), _refd_by (incoming)

    Attributes:
        _entities: Raw entity dict from parse_step_file().
        _refs: {entity_id: set of referenced entity IDs}.
        _refd_by: {entity_id: set of referrer entity IDs}.
    """

    def __init__(self, entities: Dict[int, dict]):
        self._entities = entities
        self._refs: Dict[int, Set[int]] = defaultdict(set)
        self._refd_by: Dict[int, Set[int]] = defaultdict(set)
        self._build_ref_graph()

    def _build_ref_graph(self):
        """Scan all entity raw texts for #N references, build the graph."""
        ref_pattern = re.compile(r'#(\d+)')
        for eid, e in self._entities.items():
            refs = [int(m) for m in ref_pattern.findall(e['raw'])]
            self._refs[eid] = set(refs)
            for rid in refs:
                self._refd_by[rid].add(eid)

    def get_type(self, eid: int) -> str:
        """Return the entity type name for the given ID."""
        return self._entities[eid]['type']

    def get_args(self, eid: int) -> List[Any]:
        """Lazy-parse and return the entity's argument list."""
        e = self._entities[eid]
        if e['_parsed'] is None:
            e['_parsed'] = _parse_args(e['raw'])
        return e['_parsed']

    def get_type_and_args(self, eid: int) -> Tuple[str, List[Any]]:
        """Return (type_name, parsed_args) for the given entity ID."""
        return (self.get_type(eid), self.get_args(eid))

    def resolve(self, value) -> Any:
        """Recursively dereference: ('ref', N) → parsed args of entity N."""
        if isinstance(value, tuple) and value[0] == 'ref':
            return self.get_args(value[1])
        return value

    def get_ref(self, value) -> Optional[int]:
        """If value is a reference tuple, return the entity ID, else None."""
        if isinstance(value, tuple) and value[0] == 'ref':
            return value[1]
        return None

    def collect_reachable(self, start_ids: List[int]) -> Set[int]:
        """BFS from start_ids to collect all reachable entity IDs."""
        reachable = set()
        queue = list(start_ids)
        while queue:
            eid = queue.pop()
            if eid in reachable or eid not in self._entities:
                continue
            reachable.add(eid)
            for rid in self._refs.get(eid, set()):
                if rid not in reachable:
                    queue.append(rid)
        return reachable

    def has(self, eid: int) -> bool:
        """Check if an entity ID exists in the store."""
        return eid in self._entities

    def __contains__(self, eid: int) -> bool:
        return eid in self._entities
