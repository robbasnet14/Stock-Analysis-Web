from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


def _sha1(text: str) -> str:
    return hashlib.sha1((text or "").encode("utf-8", "ignore")).hexdigest()


def normalize_title(title: str) -> str:
    t = re.sub(r"https?://\S+", "", (title or "").lower())
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _shingles(text: str, k: int = 3) -> set[str]:
    tokens = normalize_title(text).split()
    if len(tokens) <= k:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[i : i + k]) for i in range(0, len(tokens) - k + 1)}


def _minhash_signature(shingles: set[str], num_perm: int = 64) -> tuple[int, ...]:
    if not shingles:
        return tuple([0] * num_perm)
    sig: list[int] = []
    for i in range(num_perm):
        minimum = None
        salt = f"s{i:02d}"
        for sh in shingles:
            hv = int(_sha1(f"{salt}:{sh}"), 16)
            minimum = hv if minimum is None else min(minimum, hv)
        sig.append(int(minimum or 0))
    return tuple(sig)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a.intersection(b))
    union = len(a.union(b))
    return float(inter / union) if union else 0.0


@dataclass
class DedupResult:
    is_duplicate: bool
    url_hash: str
    title_hash: str


class Deduper:
    """Three stage dedupe: URL hash -> title hash -> MinHash/Jaccard."""

    def __init__(self) -> None:
        self._recent_signatures: list[tuple[tuple[int, ...], set[str]]] = []

    async def check(self, redis_client, *, url: str, title: str) -> DedupResult:
        url_hash = _sha1((url or "").strip().lower())
        title_norm = normalize_title(title)
        title_hash = _sha1(title_norm)

        # Stage 1: URL hash, 7 days.
        if redis_client is not None and url_hash:
            ok = await redis_client.set(f"news:dedup:url:{url_hash}", "1", nx=True, ex=604800)
            if not ok:
                return DedupResult(True, url_hash, title_hash)

        # Stage 2: normalized title hash, 24h.
        if redis_client is not None and title_hash:
            ok = await redis_client.set(f"news:dedup:title:{title_hash}", "1", nx=True, ex=86400)
            if not ok:
                return DedupResult(True, url_hash, title_hash)

        # Stage 3: MinHash-like + Jaccard >= 0.8
        shingles = _shingles(title_norm, 3)
        sig = _minhash_signature(shingles, 64)
        for _, prev_sh in self._recent_signatures[-300:]:
            if _jaccard(shingles, prev_sh) >= 0.8:
                return DedupResult(True, url_hash, title_hash)

        self._recent_signatures.append((sig, shingles))
        if len(self._recent_signatures) > 500:
            self._recent_signatures = self._recent_signatures[-500:]
        return DedupResult(False, url_hash, title_hash)

