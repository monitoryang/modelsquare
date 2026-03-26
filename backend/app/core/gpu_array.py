"""
GPU array backend with automatic NumPy fallback.

Provides a unified `xp` namespace that is either CuPy (GPU) or NumPy (CPU),
along with utility functions for transferring arrays between CPU and GPU.

Usage:
    from app.core.gpu_array import xp, to_gpu, to_cpu, ensure_numpy

    arr = xp.array([1, 2, 3], dtype=xp.float32)  # GPU if CuPy available
    np_arr = ensure_numpy(arr)                      # Always NumPy
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

GPU_ARRAY_AVAILABLE = False
cp = None

try:
    import cupy as _cp

    cp = _cp
    GPU_ARRAY_AVAILABLE = True
    logger.info("CuPy %s available, GPU array acceleration enabled", cp.__version__)
except ImportError:
    logger.info("CuPy not available, falling back to NumPy")

# Unified array namespace: CuPy when available, otherwise NumPy.
xp = cp if GPU_ARRAY_AVAILABLE else np


def to_gpu(arr: np.ndarray):
    """Transfer a NumPy array to GPU (CuPy). No-op if CuPy is unavailable."""
    if GPU_ARRAY_AVAILABLE:
        return cp.asarray(arr)
    return arr


def to_cpu(arr) -> np.ndarray:
    """Transfer a GPU array back to CPU (NumPy). No-op if already NumPy."""
    if GPU_ARRAY_AVAILABLE and isinstance(arr, cp.ndarray):
        return cp.asnumpy(arr)
    return np.asarray(arr)


def ensure_numpy(arr) -> np.ndarray:
    """Ensure the array is a NumPy ndarray (required by Triton client)."""
    return to_cpu(arr)


def get_array_module(arr):
    """Return the array module (cupy or numpy) for the given array."""
    if GPU_ARRAY_AVAILABLE:
        return cp.get_array_module(arr)
    return np


def warmup():
    """Trigger CuPy kernel JIT compilation to avoid first-call latency."""
    if not GPU_ARRAY_AVAILABLE:
        return
    try:
        a = cp.random.randn(100, 512).astype(cp.float32)
        b = cp.random.randn(10, 512).astype(cp.float32)
        _ = a @ b.T
        _ = cp.linalg.norm(a, axis=-1)
        _ = 1.0 / (1.0 + cp.exp(-a[:, :10]))
        cp.cuda.Stream.null.synchronize()
        logger.info("CuPy warmup completed")
    except Exception as e:
        logger.warning("CuPy warmup failed: %s", e)
