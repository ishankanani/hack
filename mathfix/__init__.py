"""MathFix AI.

Numeric libraries (OpenBLAS/MKL via numpy) reserve memory for every CPU core in every process.
With several sandbox worker processes that can fail on Windows ("OpenBLAS error: Memory
allocation still failed"), and we don't need multithreaded linear algebra anyway. These must be
set before numpy is first imported; worker processes inherit them.
"""
import os

for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_var, "1")
