"""Closed registry; definitions select data layouts, never executable plugins."""
from .levels import DeclaredLevelAdapter


def adapter_for(kind,raw,definition,source_sha256):
    if kind!='levels':raise ValueError('no built-in game-format adapter is registered for this kind')
    return DeclaredLevelAdapter(raw,definition,source_sha256)
