"""Fix chromedriver installation for Selenium.

This script finds the actual chromedriver binary, or downloads it if missing.
Run it once:  python setup_chromedriver.py
"""

import os
import sys
import shutil
import zipfile
import subprocess
import urllib.request
import json


def is_valid_chromedriver(path):
    """Check if path is an actual chromedriver binary."""
    if not path or not os.path.isfile(path):
        return False
    basename = os.path.basename(path).lower()
    if "third_party" in basename or "license" in basename or "notice" in basename:
        return False
    if "chromedriver" not in basename:
        return False
    # Check binary magic
    try:
        with open(path, "rb") as f:
            header = f.read(4)
        if header in (b"\x7fELF", b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf",
                      b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"):
            return True
        with open(path, "rb") as f:
            data = f.read(1024)
        return b"\x00" in data
    except OSError:
        return False


def find_existing_chromedriver():
    """Search common locations for a working chromedriver."""
    # Check PATH
    found = shutil.which("chromedriver")
    if found and is_valid_chromedriver(found):
        return found

    # Check common locations
    for loc in ["/usr/local/bin/chromedriver", "/opt/homebrew/bin/chromedriver",
                "/usr/bin/chromedriver"]:
        if is_valid_chromedriver(loc):
            return loc

    # Search ~/.wdm recursively
    wdm_root = os.path.expanduser("~/.wdm")
    if os.path.isdir(wdm_root):
        for root, dirs, files in os.walk(wdm_root):
            for f in files:
                full = os.path.join(root, f)
                if is_valid_chromedriver(full):
                    return full

    # Search ~/.cache/selenium
    cache_root = os.path.expanduser("~/.cache/selenium")
    if os.path.isdir(cache_root):
        for root, dirs, files in os.walk(cache_root):
            for f in files:
                full = os.path.join(root, f)
                if is_valid_chromedriver(full):
                    return full

    return None


def get_chrome_version():
    """Get the installed Google Chrome version."""
    # macOS
    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    if os.path.exists(chrome_path):
        try:
            result = subprocess.run(
                [chrome_path, "--version"],
                capture_output=True, text=True, timeout=5
            )
            version = result.stdout.strip().split()[-1]
            print(f"Chrome version: {version}")
            return version
        except Exception as e:
            print(f"Could not get Chrome version: {e}")

    # Linux
    try:
        result = subprocess.run(["google-chrome", "--version"],
                                capture_output=True, text=True, timeout=5)
        version = result.stdout.strip().split()[-1]
        print(f"Chrome version: {version}")
        return version
    except Exception:
        pass

    print("WARNING: Could not find Google Chrome installed.")
    return None


def download_chromedriver(version=None):
    """Download the correct chromedriver for the installed Chrome."""
    if not version:
        version = get_chrome_version()
        if not version:
            print("Cannot determine Chrome version. Please install Chrome first.")
            return None

    # Get major version
    major = version.split(".")[0]
    print(f"Downloading chromedriver for Chrome {version}...")

    # Try Chrome for Testing JSON
    try:
        req = urllib.request.urlopen(
            "https://googlechromelabs.github.io/chrome-for-testing/known-good-versions-with-downloads.json"
        )
        data = json.loads(req.read())
        for item in data["versions"]:
            if item["version"] == version:
                for dl in item["downloads"].get("chromedriver", []):
                    if dl["platform"] == "mac-arm64":
                        url = dl["url"]
                        print(f"Found download: {url}")
                        return _download_and_install(url)
        print(f"Exact version {version} not found. Trying latest for major {major}...")
    except Exception as e:
        print(f"Error querying Chrome for Testing: {e}")

    # Fallback: use webdriver_manager to download
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        path = ChromeDriverManager().install()
        if is_valid_chromedriver(path):
            return path
        # Search for the actual binary in the cache
        cache_root = os.path.expanduser("~/.wdm/drivers/chromedriver")
        if os.path.isdir(cache_root):
            for root, dirs, files in os.walk(cache_root):
                for f in files:
                    full = os.path.join(root, f)
                    if is_valid_chromedriver(full):
                        return full
    except Exception as e:
        print(f"webdriver_manager failed: {e}")

    return None


def _download_and_install(url):
    """Download chromedriver zip, extract, and make executable."""
    import zipfile
    import tempfile

    print(f"Downloading from {url}...")
    tmp = tempfile.mkdtemp()
    zip_path = os.path.join(tmp, "chromedriver.zip")

    try:
        urllib.request.urlretrieve(url, zip_path)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(tmp)

        # Find the chromedriver binary
        for root, dirs, files in os.walk(tmp):
            for f in files:
                if f == "chromedriver" and not f.endswith(".md"):
                    full = os.path.join(root, f)
                    # Make executable
                    os.chmod(full, os.stat(full).st_mode | 0o111)
                    # Install to ~/.wdm/bin
                    install_dir = os.path.expanduser("~/.wdm/bin")
                    os.makedirs(install_dir, exist_ok=True)
                    dest = os.path.join(install_dir, "chromedriver")
                    shutil.copy2(full, dest)
                    os.chmod(dest, os.stat(dest).st_mode | 0o111)
                    print(f"Installed chromedriver to {dest}")
                    return dest
    except Exception as e:
        print(f"Download failed: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return None


def main():
    print("=" * 60)
    print("Chromedriver Fixer")
    print("=" * 60)

    # 1. Check if chromedriver already exists
    existing = find_existing_chromedriver()
    if existing:
        print(f"\
✓ Found working chromedriver at: {existing}")
        print("  Your system should work now.")
        return

    print("\
No working chromedriver found. Attempting to download...")

    # 2. Check Chrome
    chrome_version = get_chrome_version()
    if not chrome_version:
        print("\
ERROR: Google Chrome is not installed.")
        print("Please install Google Chrome first, then run this script again.")
        print("Download: https://www.google.com/chrome/")
        sys.exit(1)

    # 3. Download chromedriver
    driver_path = download_chromedriver(chrome_version)
    if driver_path:
        print(f"\
✓ Successfully installed chromedriver at: {driver_path}")
        print("  Restart your Flask app and try scraping again.")
    else:
        print("\
✗ Failed to download chromedriver automatically.")
        print("  Please install manually:")
        print("    brew install chromedriver")
        print("  Or download from: https://googlechromelabs.github.io/chrome-for-testing/")


if __name__ == "__main__":
    main()
