"""Zip the onedir desktop build so the server can hand it over as ONE file.

The build is `pyinstaller AssyManagerClient.spec`, which now emits a DIRECTORY
(`client/dist/AssyManagerClient/`) rather than a single exe -- measured 2026-08-25: onefile
never opened a window in four minutes because the bootloader was still unpacking, onedir
opened in five seconds. A directory cannot be downloaded, so this runs after the build and
packs it.

    python client/package_client.py

The zip's single top-level entry is `AssyManagerClient/`, so unzipping produces one folder
rather than 5,818 loose files in whatever directory the operator happened to be in.

Written as a script rather than done by hand because the next build would need it again, and a
forgotten step ships the PREVIOUS zip -- the download would silently be one release behind.
"""
import os
import shutil
import sys
import zipfile

CLIENT_DIR = os.path.dirname(os.path.abspath(__file__))
DIST_DIR = os.path.join(CLIENT_DIR, "dist")
BUILD_DIR = os.path.join(DIST_DIR, "AssyManagerClient")
TARGET = os.path.join(DIST_DIR, "AssyManagerClient.zip")

MB = 1024.0 * 1024.0


def _tree_size(root):
    files = 0
    total = 0
    for base, _dirs, names in os.walk(root):
        for name in names:
            files += 1
            try:
                total += os.path.getsize(os.path.join(base, name))
            except OSError:
                pass
    return files, total


def main():
    if not os.path.isdir(BUILD_DIR):
        print("no build at %s" % BUILD_DIR)
        print("run `pyinstaller AssyManagerClient.spec` from client/ first")
        return 1

    files, raw = _tree_size(BUILD_DIR)
    print("packing %d files (%.1f MB) from %s" % (files, raw / MB, BUILD_DIR))

    # Built beside the target and moved into place: a zip that dies halfway through must not
    # replace a good one, because the route serves whatever file is sitting at TARGET.
    staging = os.path.join(DIST_DIR, "AssyManagerClient.partial")
    if os.path.exists(staging + ".zip"):
        os.remove(staging + ".zip")
    made = shutil.make_archive(staging, "zip", root_dir=DIST_DIR, base_dir="AssyManagerClient")
    os.replace(made, TARGET)

    with zipfile.ZipFile(TARGET) as zf:
        entries = zf.namelist()
        tops = sorted({name.split("/")[0] for name in entries})
    packed = os.path.getsize(TARGET)
    print("wrote   %s" % TARGET)
    print("        %d entries · %.1f MB (%.0f%% of the tree)"
          % (len(entries), packed / MB, 100.0 * packed / raw if raw else 0))
    print("        top level: %s" % ", ".join(tops))
    if tops != ["AssyManagerClient"]:
        print("REFUSED: the zip must hold ONE top-level folder named AssyManagerClient")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
