#!/usr/bin/env python3
"""Install Scrapling library.

Run: python install_scrapling.py
"""

import subprocess
import sys


def main():
    print("Installing Scrapling...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "scrapling"],
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
        sys.exit(result.returncode)
    print("Scrapling installed successfully.")


if __name__ == "__main__":
    main()
