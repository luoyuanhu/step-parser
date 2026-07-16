#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI entry point for step-parser.

Usage:
    python -m step_parser <path/to/file.stp>
"""

import sys
import os

from .parser import parse_step_file, validate_step_file, EntityStore
from .assembly import extract_assembly
from .report import analyze_part, print_report


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m step_parser <path/to/file.stp>")
        print("       step-parser <path/to/file.stp>")
        sys.exit(1)

    filepath = sys.argv[1]

    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    # Validate
    validation = validate_step_file(filepath)
    status_icon = {'ok': '✅', 'warn': '⚠️', 'fail': '❌'}[validation['status']]
    print(f"  Status: {status_icon} {validation['status'].upper()}")
    for info in validation['info']:
        print(f"    {info}")

    if validation['status'] == 'fail':
        print("\n  Errors:")
        for e in validation['errors']:
            print(f"    ❌ {e}")
        sys.exit(1)

    if validation['warnings']:
        print("  Warnings:")
        for w in validation['warnings']:
            print(f"    ⚠️  {w}")

    # Parse
    entities = parse_step_file(filepath)
    store = EntityStore(entities)

    # Extract assembly
    assembly = extract_assembly(store)

    # Analyze each part
    analyzed_parts = []
    for part in assembly['parts']:
        result = analyze_part(store, part)
        analyzed_parts.append(result)

    results = {
        'file': os.path.basename(filepath),
        'assembly': assembly['assembly_name'],
        'total_instances': assembly['total_instances'],
        'parts': analyzed_parts
    }

    print_report(results)


if __name__ == '__main__':
    main()
