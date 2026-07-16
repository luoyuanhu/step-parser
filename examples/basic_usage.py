#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Basic usage example for step-parser.

Usage:
    python examples/basic_usage.py path/to/file.stp
"""

import sys
import os

# Allow running from repo root without installing
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from step_parser import parse, validate, analyze


def main():
    if len(sys.argv) < 2:
        print("Usage: python basic_usage.py <path/to/file.stp>")
        sys.exit(1)

    filepath = sys.argv[1]

    # ── Step 1: Validate ──
    print("=" * 70)
    print("  STEP File Validation")
    print("=" * 70)
    report = validate(filepath)
    status_icon = {'ok': '✅', 'warn': '⚠️', 'fail': '❌'}[report['status']]
    print(f"  Status: {status_icon} {report['status'].upper()}")

    for info in report['info']:
        print(f"    {info}")

    if report['status'] == 'fail':
        print("\n  Errors:")
        for e in report['errors']:
            print(f"    ❌ {e}")
        sys.exit(1)

    if report['warnings']:
        print("\n  Warnings:")
        for w in report['warnings']:
            print(f"    ⚠️  {w}")

    # ── Step 2: Parse ──
    print(f"\n{'=' * 70}")
    print("  Parsing STEP File")
    print("=" * 70)
    store = parse(filepath)
    print(f"  Parsed {len(store._entities)} entities")

    # ── Step 3: Extract assembly ──
    from step_parser import extract_assembly, print_report

    print(f"\n{'=' * 70}")
    print("  Extracting Assembly Structure")
    print("=" * 70)
    assembly = extract_assembly(store)
    print(f"  Assembly: {assembly['assembly_name']}")
    print(f"  Part types: {len(assembly['parts'])}")
    print(f"  Total instances: {assembly['total_instances']}")

    # ── Step 4: Analyze each part ──
    print(f"\n{'=' * 70}")
    print("  Analyzing Part Geometry")
    print("=" * 70)

    results = {'file': os.path.basename(filepath),
               'assembly': assembly['assembly_name'],
               'total_instances': assembly['total_instances'],
               'parts': []}

    for part in assembly['parts']:
        result = analyze(store, part)
        results['parts'].append(result)

    # ── Step 5: Print report ──
    print_report(results)


if __name__ == '__main__':
    main()
