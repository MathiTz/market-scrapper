"""Diagnose chromedriver installation."""
import os
import sys

# Look in the webdriver_manager cache
cache_root = os.path.expanduser("~/.wdm/drivers/chromedriver")
print(f"Cache root: {cache_root}")
if os.path.isdir(cache_root):
    for root, dirs, files in os.walk(cache_root):
        for f in files:
            full = os.path.join(root, f)
            size = os.path.getsize(full)
            print(f"  {full} ({size} bytes)")
else:
    print("  Cache root does not exist")

# Also check ~/.wdm/bin
bin_dir = os.path.expanduser("~/.wdm/bin")
print(f"\nBin dir: {bin_dir}")
if os.path.isdir(bin_dir):
    for f in os.listdir(bin_dir):
        full = os.path.join(bin_dir, f)
        size = os.path.getsize(full)
        print(f"  {full} ({size} bytes)")
else:
    print("  Bin dir does not exist")

# Check PATH
import shutil
which = shutil.which("chromedriver")
print(f"\nwhich chromedriver: {which}")

# Check common locations
for loc in ["/usr/local/bin/chromedriver", "/opt/homebrew/bin/chromedriver", "/usr/bin/chromedriver"]:
    if os.path.exists(loc):
        print(f"  Found: {loc}")

# Check Chrome version
chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if os.path.exists(chrome_path):
    import subprocess
    result = subprocess.run([chrome_path, "--version"], capture_output=True, text=True, timeout=5)
    print(f"Chrome version: {result.stdout.strip()}")
else:
    print("Chrome not found at standard path")
