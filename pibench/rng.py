"""RNG discipline: independent per-subsystem streams plus stable entity-keyed draws.

Two access patterns:
- ``hub.stream(name)``: a persistent Generator for a subsystem whose draw order is
  fixed by the simulator's tick structure (e.g. the field hotness trajectory).
- ``hub.keyed(*key)``: a fresh Generator deterministically derived from
  (world_seed, *key). Used for draws attached to entities/months so that outcomes do
  not depend on the interleaving of unrelated agent actions.
"""
from __future__ import annotations

import hashlib

import numpy as np


class RngHub:
    def __init__(self, seed: int):
        self.seed = int(seed)
        self._streams: dict[str, np.random.Generator] = {}

    def stream(self, name: str) -> np.random.Generator:
        if name not in self._streams:
            self._streams[name] = self.keyed("stream", name)
        return self._streams[name]

    def keyed(self, *key) -> np.random.Generator:
        material = f"{self.seed}|" + "|".join(str(k) for k in key)
        digest = hashlib.sha256(material.encode()).digest()
        entropy = int.from_bytes(digest[:16], "little")
        return np.random.default_rng(np.random.SeedSequence(entropy))
