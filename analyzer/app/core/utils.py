import numpy as np


def safe_float(value):
    """Безопасно преобразует numpy значение в Python float"""
    if isinstance(value, np.ndarray):
        if value.size == 1:
            return float(value.item())
        else:
            return float(np.mean(value))
    return float(value)


def safe_int(value):
    """Безопасно преобразует numpy значение в Python int"""
    if isinstance(value, np.ndarray):
        if value.size == 1:
            return int(value.item())
        else:
            return int(np.mean(value))
    return int(value)
