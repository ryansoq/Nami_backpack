"""
編譯 Cython 模組

用法:
    python setup_cython.py build_ext --inplace
"""

from setuptools import setup
from Cython.Build import cythonize
import numpy as np

setup(
    name="kaspa_pow",
    ext_modules=cythonize(
        "kaspa_pow.pyx",
        compiler_directives={
            'language_level': 3,
            'boundscheck': False,
            'wraparound': False,
            'cdivision': True,
        }
    ),
    include_dirs=[np.get_include()],
)
