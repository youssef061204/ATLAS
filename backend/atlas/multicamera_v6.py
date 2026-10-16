"""Ground-truth-blind offline association for a bounded CityFlow research pilot."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AppearanceTracklet:
    camera: str
    identity: int
    start_s: float
    end_s: float
    embedding: np.ndarray


def associate(tracklets, minimum_cosine=0.85, maximum_gap_s=30):
    if not -1 <= minimum_cosine <= 1 or maximum_gap_s < 0:
        raise ValueError("Invalid association limits")
    vectors, keys = [], set()
    for track in tracklets:
        key = track.camera, track.identity
        if (
            key in keys
            or not np.isfinite([track.start_s, track.end_s]).all()
            or track.end_s < track.start_s
        ):
            raise ValueError("Duplicate identity or invalid observation interval")
        keys.add(key)
        vector = np.asarray(track.embedding, dtype=float)
        if vector.ndim != 1 or not np.isfinite(vector).all() or np.linalg.norm(vector) < 1e-10:
            raise ValueError("Invalid appearance embedding")
        vectors.append(vector / np.linalg.norm(vector))
    if vectors and len({len(vector) for vector in vectors}) != 1:
        raise ValueError("Incompatible appearance embeddings")
    parent = list(range(len(tracklets)))
    cameras = [{track.camera} for track in tracklets]

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    candidates = []
    for i, a in enumerate(tracklets):
        for j in range(i + 1, len(tracklets)):
            b = tracklets[j]
            if a.camera == b.camera:
                continue
            gap = max(0, max(a.start_s, b.start_s) - min(a.end_s, b.end_s))
            similarity = float(vectors[i] @ vectors[j])
            if gap <= maximum_gap_s and similarity >= minimum_cosine:
                candidates.append((-similarity, i, j))
    accepted = []
    for negative_similarity, i, j in sorted(candidates):
        left, right = find(i), find(j)
        if left == right or cameras[left].intersection(cameras[right]):
            continue
        parent[right] = left
        cameras[left] |= cameras[right]
        accepted.append(
            {
                "left": [tracklets[i].camera, tracklets[i].identity],
                "right": [tracklets[j].camera, tracklets[j].identity],
                "cosine": -negative_similarity,
            }
        )
    components = {}
    mapping = {}
    for i, track in enumerate(tracklets):
        root = find(i)
        components.setdefault(root, len(components) + 1)
        mapping[(track.camera, track.identity)] = components[root]
    return mapping, accepted
