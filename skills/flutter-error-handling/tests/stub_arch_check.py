#!/usr/bin/env python3
"""Test stub for ../flutter-architecture/scripts/arch_check.py: prints <root>/arch_files.json."""
import os
import sys

with open(os.path.join(sys.argv[1], 'arch_files.json')) as fh:
    sys.stdout.write(fh.read())
