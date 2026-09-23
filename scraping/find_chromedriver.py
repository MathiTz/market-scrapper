"""Find the actual chromedriver binary on this system."""

import os
import glob
import stat

print("=== Searching for chromedriver binaries ===")

# Search ~/.wdm
wdm_root = os.path.expanduser("~/.wdm")
if os.path.exists(wdm_root):
    print(f"\
--- {wdm_root} ---")
    for root, dirs, files in os.walk(wdm_root):
        for f in files:
            full = os.path.join(root, f)
            size = os.path.getsize(full)
            is_exec = os.access(full, os.X_OK)
            print(f"  {full} (size={size}, exec={is_exec})")
else:
    print("~/.wdm does not exist")

# Search PATH
print("\
--- PATH search ---")
for path in os.environ.get("PATH", "").split(":"):
    for f in glob.glob(os.path.join(path, "chromedriver*")):
        if os.path.isfile(f):
            size = os.path.getsize(f)
            is_exec = os.access(f, os.X_OK)
            print(f"  {f} (size={size}, exec={is_exec})")

# Search common locations
print("\
--- Common locations ---")
for loc in ["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/usr/local/bin/chromedriver"]:
    for f in glob.glob(os.path.join(loc, "chromedriver*")):
        if os.path.isfile(f):
            size = os.path.getsize(f)
            is_exec = os.access(f, os.X_OK)
            print(f"  {f} (size={size}, exec={is_exec})")

# Check if Google Chrome is installed
print("\
--- Chrome installation ---")
chrome_paths = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]
for p in chrome_paths:
    if os.path.exists(p):
        print(f"  Found: {p}")
    else:
        print(f"  Not found: {p}")

# Check Selenium Manager cache
print("\
--- Selenium Manager cache ---")
selenium_cache = os.path.expanduser("~/.cache/selenium")
if os.path.exists(selenium_cache):
    for root, dirs, files in os.walk(selenium_cache):
        for f in files:
            full = os.path.join(root, f)
            size = os.path.getsize(full)
            is_exec = os.access(full, os.X_OK)
            print(f"  {full} (size={size}, exec={is_exec})")
else:
    print("  ~/.cache/selenium does not exist")

print("\
=== Done ===")
"}]