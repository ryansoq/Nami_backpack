"""
編譯 Cython v2 模組

用法:
    python setup_v2.py build_ext --inplace
"""

from setuptools import setup
from Cython.Build import cythonize
import numpy as np

setup(
    name="kaspa_pow_v2",
    ext_modules=cythonize(
        "kaspa_pow_v2.pyx",
        compiler_directives={
            'language_level': 3,
            'boundscheck': False,
            'wraparound': False,
            'cdivision': True,
        }
    ),
    include_dirs=[np.get_include()],
)
