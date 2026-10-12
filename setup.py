"""Build-time shim only; everything else is in pyproject.toml.

A wheel carries the user's starter files (aos.toml, agents/, skills/, docs/, examples/, ...) in aos/_shipped so that
`aos setup` can copy them into the user's folder. The list lives in aos/shipped.py.
"""

import importlib.util
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

ROOT = Path(__file__).resolve().parent


def _shipped():
    # loaded by path on purpose: the `aos` package itself is not importable (or needed) while building
    spec = importlib.util.spec_from_file_location("_aos_shipped", ROOT / "aos" / "shipped.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class build_py(_build_py):
    def run(self):
        super().run()
        if getattr(self, "editable_mode", False):
            return  # an editable install runs from the checkout: the files are right there
        dst = Path(self.build_lib) / "aos" / "_shipped"
        shutil.rmtree(dst, ignore_errors=True)  # a stale build/lib must not leak removed files into the wheel
        _shipped().copy(ROOT, dst, overwrite=True)


setup(cmdclass={"build_py": build_py})
