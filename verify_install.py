#!/usr/bin/env python3
"""
Verification script for InterLog installation.
Run this to check if everything is set up correctly.
"""

import sys
import os
from pathlib import Path

def check_python_version():
    """Check Python version is 3.7+"""
    version = sys.version_info
    if version.major >= 3 and version.minor >= 7:
        print(f"[OK] Python {version.major}.{version.minor}.{version.micro}")
        return True
    else:
        print(f"[FAIL] Python {version.major}.{version.minor}.{version.micro} (Need 3.7+)")
        return False

def check_files():
    """Check required files exist"""
    required = [
        'interlog.py',
        'analyzer.py',
        'requirements.txt',
        'README.md',
        'QUICKSTART.md',
        'LICENSE'
    ]

    all_good = True
    for filename in required:
        if Path(filename).exists():
            print(f"[OK] {filename}")
        else:
            print(f"[MISSING] {filename}")
            all_good = False

    return all_good

def check_pynput():
    """Check if pynput is installed"""
    try:
        import pynput
        print(f"[OK] pynput is installed (version {pynput.__version__})")
        return True
    except ImportError:
        print("[FAIL] pynput is NOT installed")
        print("  Run: pip install -r requirements.txt")
        return False

def main():
    print("InterLog Installation Verification")
    print("=" * 40)
    print()

    print("1. Python Version")
    python_ok = check_python_version()
    print()

    print("2. Required Files")
    files_ok = check_files()
    print()

    print("3. Dependencies")
    deps_ok = check_pynput()
    print()

    print("=" * 40)
    if python_ok and files_ok and deps_ok:
        print("ALL CHECKS PASSED!")
        print()
        print("You're ready to use InterLog:")
        print("  python interlog.py")
        print()
        print("For help:")
        print("  python interlog.py --help")
    else:
        print("SOME CHECKS FAILED")
        print()
        if not deps_ok:
            print("Install dependencies:")
            print("  pip install -r requirements.txt")
        print()
        print("See QUICKSTART.md for setup instructions")

    print("=" * 40)

if __name__ == '__main__':
    main()
