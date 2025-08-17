import os
import sys


def _ensure_packages_on_path() -> None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    packages_dir = os.path.join(repo_root, "packages")
    if packages_dir not in sys.path:
        sys.path.insert(0, packages_dir)


_ensure_packages_on_path()
