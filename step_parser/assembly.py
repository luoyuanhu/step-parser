#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assembly Structure Extraction
==============================
Extracts the assembly tree from a STEP file: part list, instance counts,
and the PRODUCT → CLOSED_SHELL reference chain.
"""

from collections import defaultdict
from typing import Dict, List, Optional, Any

from .parser import EntityStore


def extract_assembly(store: EntityStore) -> Dict[str, Any]:
    """Extract assembly structure: part list, instance counts, geometry refs.

    Returns a dict with:
        assembly_name: str — root assembly name
        parts: list of {product_id, name, description, shell_id, instances}
        total_instances: int — sum of all part instances
    """
    # Step 1: Find "detail" / "part" category PRODUCTs
    detail_products = []
    for eid, e in store._entities.items():
        if e['type'] == 'PRODUCT_RELATED_PRODUCT_CATEGORY':
            args = store.get_args(eid)
            # Variants:
            #   Creo: ('detail', '', (product_refs...))
            #   OCC:  ('part', $, (product_refs...))
            if len(args) >= 3:
                cat_name = str(args[0]) if args[0] else ''
                refs_list = args[2] if isinstance(args[2], list) else [args[2]]
                if cat_name in ('detail', 'part'):
                    for item in refs_list:
                        pid = store.get_ref(item)
                        if pid and store.has(pid) and store.get_type(pid) == 'PRODUCT':
                            detail_products.append(pid)

    detail_products = list(dict.fromkeys(detail_products))

    # Fallback: if no category found, infer from NAUO children
    if not detail_products:
        all_nauo_children = set()
        for eid, e in store._entities.items():
            if e['type'] == 'NEXT_ASSEMBLY_USAGE_OCCURRENCE':
                args = store.get_args(eid)
                if len(args) >= 5:
                    child_id = store.get_ref(args[4])
                    if child_id:
                        all_nauo_children.add(child_id)

        for def_id in all_nauo_children:
            product_id = _resolve_definition_to_product(store, def_id)
            if product_id and store.get_type(product_id) == 'PRODUCT':
                detail_products.append(product_id)

    # Step 2: Trace PRODUCT → CLOSED_SHELL for each part
    parts = []
    for product_id in detail_products:
        product_args = store.get_args(product_id)
        part_name = product_args[0] if len(product_args) > 0 else '?'
        part_desc = product_args[1] if len(product_args) > 1 else ''

        shell_id = _trace_to_shell(store, product_id)

        parts.append({
            'product_id': product_id,
            'name': str(part_name),
            'description': str(part_desc) if part_desc else str(part_name),
            'shell_id': shell_id
        })

    # Step 3: Count instances via NAUO
    instance_count = defaultdict(int)
    for eid, e in store._entities.items():
        if e['type'] == 'NEXT_ASSEMBLY_USAGE_OCCURRENCE':
            args = store.get_args(eid)
            if len(args) >= 5:
                child_def_id = store.get_ref(args[4])
                if child_def_id:
                    product_id = _resolve_definition_to_product(store, child_def_id)
                    if product_id:
                        instance_count[product_id] += 1

    for part in parts:
        part['instances'] = instance_count.get(part['product_id'], 0)

    # Step 4: Find root assembly name
    root_candidates = _find_root_assembly(store)

    assembly_name = 'UNKNOWN'
    if root_candidates:
        root_id = next(iter(root_candidates))
        if store.has(root_id):
            p_args = store.get_args(root_id)
            assembly_name = str(p_args[0]) if p_args else 'UNKNOWN'

    if assembly_name == 'UNKNOWN' and len(detail_products) == 1:
        p_args = store.get_args(detail_products[0])
        assembly_name = str(p_args[0]) if p_args else 'UNKNOWN'

    # Filter out root assembly PRODUCT from parts list
    nauo_parents, nauo_children = _get_nauo_relations(store)
    if nauo_parents and nauo_children:
        root_ids = nauo_parents - nauo_children
        parts = [p for p in parts if p['product_id'] not in root_ids]

    parts.sort(key=lambda p: p['name'])

    # Single-part with no NAUO → instance = 1
    for part in parts:
        if part['instances'] == 0:
            part['instances'] = 1

    return {
        'assembly_name': assembly_name,
        'parts': parts,
        'total_instances': sum(p['instances'] for p in parts)
    }


def _trace_to_shell(store: EntityStore, product_id: int) -> Optional[int]:
    """Trace PRODUCT → CLOSED_SHELL through the STEP reference chain.

    Chain: PRODUCT → PRODUCT_DEFINITION_FORMATION →
           PRODUCT_DEFINITION → PRODUCT_DEFINITION_SHAPE →
           SHAPE_DEFINITION_REPRESENTATION →
           ADVANCED_BREP_SHAPE_REPRESENTATION →
           MANIFOLD_SOLID_BREP → CLOSED_SHELL
    """
    # 1. PRODUCT → PRODUCT_DEFINITION_FORMATION
    formation_id = None
    for rid in store._refd_by.get(product_id, set()):
        etype = store.get_type(rid)
        if 'PRODUCT_DEFINITION_FORMATION' in etype:
            formation_id = rid
            break
    if not formation_id:
        return None

    # 2. PRODUCT_DEFINITION_FORMATION → PRODUCT_DEFINITION
    definition_id = None
    for rid in store._refd_by.get(formation_id, set()):
        if store.get_type(rid) == 'PRODUCT_DEFINITION':
            definition_id = rid
            break
    if not definition_id:
        return None

    # 3. PRODUCT_DEFINITION → PRODUCT_DEFINITION_SHAPE
    shape_id = None
    for rid in store._refd_by.get(definition_id, set()):
        if store.get_type(rid) == 'PRODUCT_DEFINITION_SHAPE':
            shape_id = rid
            break
    if not shape_id:
        return None

    # 4. PRODUCT_DEFINITION_SHAPE → SHAPE_DEFINITION_REPRESENTATION
    sdr_id = None
    for rid in store._refd_by.get(shape_id, set()):
        if store.get_type(rid) == 'SHAPE_DEFINITION_REPRESENTATION':
            sdr_id = rid
            break
    if not sdr_id:
        return None

    # 5. SHAPE_DEFINITION_REPRESENTATION → ADVANCED_BREP_SHAPE_REPRESENTATION
    sdr_args = store.get_args(sdr_id)
    rep_id = store.get_ref(sdr_args[1]) if len(sdr_args) > 1 else None
    if not rep_id or store.get_type(rep_id) != 'ADVANCED_BREP_SHAPE_REPRESENTATION':
        return None

    # 6. ADVANCED_BREP_SHAPE_REPRESENTATION → MANIFOLD_SOLID_BREP → CLOSED_SHELL
    absr_args = store.get_args(rep_id)
    items = absr_args[1] if len(absr_args) > 1 and isinstance(absr_args[1], list) else []
    for item in items:
        item_id = store.get_ref(item)
        if item_id and store.get_type(item_id) == 'MANIFOLD_SOLID_BREP':
            msb_args = store.get_args(item_id)
            shell_id = store.get_ref(msb_args[1]) if len(msb_args) > 1 else None
            if shell_id and store.get_type(shell_id) == 'CLOSED_SHELL':
                return shell_id

    return None


def _resolve_definition_to_product(store: EntityStore, definition_id: int) -> Optional[int]:
    """PRODUCT_DEFINITION → PRODUCT_DEFINITION_FORMATION → PRODUCT.

    Compatible with:
      - PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE (Creo)
      - PRODUCT_DEFINITION_FORMATION (Open CASCADE / FreeCAD / Fusion 360)
    """
    def_args = store.get_args(definition_id)
    if len(def_args) >= 3:
        formation_id = store.get_ref(def_args[2])
        if formation_id:
            form_args = store.get_args(formation_id)
            if len(form_args) >= 3:
                return store.get_ref(form_args[2])
    return None


def _find_root_assembly(store: EntityStore) -> set:
    """Find root assembly: parents that are never children in NAUO."""
    nauo_parents, nauo_children = _get_nauo_relations(store)
    return nauo_parents - nauo_children


def _get_nauo_relations(store: EntityStore):
    """Return (parents_set, children_set) from NAUO entities."""
    parents = set()
    children = set()
    for eid, e in store._entities.items():
        if e['type'] == 'NEXT_ASSEMBLY_USAGE_OCCURRENCE':
            args = store.get_args(eid)
            if len(args) >= 5:
                parent_def_id = store.get_ref(args[3])
                child_def_id = store.get_ref(args[4])
                if parent_def_id:
                    p_prod = _resolve_definition_to_product(store, parent_def_id)
                    if p_prod:
                        parents.add(p_prod)
                if child_def_id:
                    c_prod = _resolve_definition_to_product(store, child_def_id)
                    if c_prod:
                        children.add(c_prod)
    return parents, children
