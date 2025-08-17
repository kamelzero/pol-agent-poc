import os
import sys


def _ensure_paths_on_sys_path() -> None:
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    packages_dir = os.path.join(repo_root, "packages")
    # Ensure both the repo root (for imports like `packages.agents...`) and
    # the `packages/` directory itself (for imports like `common...`) are importable.
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    if packages_dir not in sys.path:
        sys.path.insert(0, packages_dir)


_ensure_paths_on_sys_path()
