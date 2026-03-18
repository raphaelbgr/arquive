"""GPU initialization helper — ensures CUDA/cuDNN DLLs are loaded."""

import logging
import sys

log = logging.getLogger(__name__)

_initialized = False


def init_gpu():
    """Preload CUDA/cuDNN DLLs for onnxruntime-gpu on Windows."""
    global _initialized
    if _initialized:
        return

    try:
        import onnxruntime
        if sys.platform == "win32" and hasattr(onnxruntime, "preload_dlls"):
            onnxruntime.preload_dlls(cuda=True)
            log.debug("CUDA DLLs preloaded via onnxruntime")
    except Exception as e:
        log.warning("Could not preload CUDA DLLs: %s", e)

    _initialized = True


def get_providers() -> list:
    """Get the best available ONNX execution providers."""
    init_gpu()
    try:
        import onnxruntime
        available = onnxruntime.get_available_providers()
        # Prefer CUDA, then CoreML (Mac), then CPU
        providers = []
        for p in ["CUDAExecutionProvider", "CoreMLExecutionProvider"]:
            if p in available:
                providers.append(p)
        providers.append("CPUExecutionProvider")
        return providers
    except ImportError:
        return ["CPUExecutionProvider"]
