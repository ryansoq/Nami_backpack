"""
編譯 Cython v3 模組 (nogil + 純 C 陣列)

用法:
    python setup_v3.py build_ext --inplace
"""

from setuptools import setup
from Cython.Build import cythonize
import numpy as np

setup(
    name="kaspa_pow_v3",
    ext_modules=cythonize(
        "kaspa_pow_v3.pyx",
        compiler_directives={
            'language_level': 3,
            'boundscheck': False,
            'wraparound': False,
            'cdivision': True,
            'initializedcheck': False,
        }
    ),
    include_dirs=[np.get_include()],
)
