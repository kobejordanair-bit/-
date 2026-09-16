#!/usr/bin/env python3
"""Candidate generation for the archive's unresolved player identities.

445 award rows across 212 distinct raw names carry no Player_ID. Most are a
script or transliteration variant of a name the archive already controls —
'拉斯马斯·温特·霍兰德' against '拉斯馬斯·溫特·霍蘭德' — so matching has to
normalise Simplified/Traditional before it compares anything.

Matching runs here, at build time, not in the browser: OpenCC is not available
to the page, and the evidence (every raw->ID pair the archive already accepted)
is easier to marshal against SQLite. The page receives ranked candidates with
their evidence and a human makes the call.
"""

from __future__ import annotations

import re
import sqlite3
from collections import Counter, defaultdict

try:
    from opencc import OpenCC
    _S2T = OpenCC("s2t")
    to_trad = _S2T.convert
except Exception:  # pragma: no cover - resolver still works, just less well
    def to_trad(text: str) -> str:
        return text

SEPARATORS = re.compile(r"[·・.·‧•\s\-_]+")


def normalise(name: str | None) -> str:
    """Fold script, separators and case so variants of one name collide."""
    if not name:
        return ""
    return SEPARATORS.sub("", to_trad(str(name).strip())).lower()


def syllables(name: str | None) -> list[str]:
    """Split a transliterated name on its separators: ['拉斯馬斯','溫特','霍蘭德']."""
    if not name:
        return []
    parts = SEPARATORS.split(to_trad(str(name).strip()))
    return [p.lower() for p in parts if p]


def bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} or ({text} if text else set())


def similarity(a: str, b: str) -> float:
    """Dice coefficient over character bigrams, with a floor from raw char overlap."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ba, bb = bigrams(a), bigrams(b)
    dice = (2 * len(ba & bb)) / (len(ba) + len(bb)) if (ba or bb) else 0.0
    ca, cb = set(a), set(b)
    chars = (2 * len(ca & cb)) / (len(ca) + len(cb))
    return max(dice, chars * 0.85)


SURNAME_GATE = 0.50


def token_similarity(a_parts: list[str], b_parts: list[str]) -> float:
    """Score two transliterated names, weighting the surname.

    Transliterated given names repeat constantly — 路易斯, 多米尼克, 亞歷山德羅
    are shared by dozens of unrelated players — so the given name cannot carry
    a match. The surname is the discriminator, and a surname that does not
    agree vetoes the pair outright: without the gate, '路易斯·迪亞斯' and
    '路易斯·蘇亞雷斯' score as the same person.

    Everything after the first part is treated as one surname, because a
    transliteration splits it inconsistently ('德·萊特' against '德里赫特').
    """
    if not a_parts or not b_parts:
        return 0.0
    a_first, b_first = a_parts[0], b_parts[0]
    a_last = "".join(a_parts[1:]) or a_first
    b_last = "".join(b_parts[1:]) or b_first

    surname = similarity(a_last, b_last)
    if surname < SURNAME_GATE:
        return 0.0
    given = similarity(a_first, b_first)
    return min(1.0, surname * 0.7 + given * 0.3)


class IdentityResolver:
    """Builds a name index from every raw->ID association the archive accepted."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        con.row_factory = sqlite3.Row
        self.canonical: dict[str, str] = {}
        self.index: dict[str, set[str]] = defaultdict(set)
        self.evidence: dict[str, Counter] = defaultdict(Counter)
        self.player_clubs: dict[str, set[str]] = defaultdict(set)
        self.parts: dict[str, list[str]] = {}
        self.spellings: dict[str, str] = {}
        self._build()
        self.parts = {key: syllables(self.spellings.get(key, key)) for key in self.index}

    def _add(self, name: str | None, player_id: str | None, source: str) -> None:
        key = normalise(name)
        if not key or not player_id:
            return
        self.index[key].add(player_id)
        self.evidence[player_id][source] += 1
        # normalise() strips the separators that syllables() needs, so remember
        # the first spelling we saw for this key
        self.spellings.setdefault(key, str(name))

    def _build(self) -> None:
        q = self.con.execute

        for r in q("SELECT Player_ID, Canonical_Display_Name, Alias_Name FROM Player_Dim"):
            pid = r["Player_ID"]
            if not pid:
                continue
            name = r["Canonical_Display_Name"] or r["Alias_Name"]
            if name and pid not in self.canonical:
                self.canonical[pid] = name
            self._add(r["Canonical_Display_Name"], pid, "Player_Dim")
            self._add(r["Alias_Name"], pid, "Player_Dim")

        # every association a human already accepted is training data
        for r in q("""SELECT Raw_Display_Name, Entity_ID FROM Record_Identity_Map
                      WHERE Entity_Role='Player' AND Entity_ID IS NOT NULL"""):
            self._add(r["Raw_Display_Name"], r["Entity_ID"], "Record_Identity_Map")

        for r in q("""SELECT Player_Raw, Player_ID, Club_ID FROM Canonical_Award_Facts
                      WHERE Player_ID IS NOT NULL"""):
            self._add(r["Player_Raw"], r["Player_ID"], "Canonical_Award_Facts")
            if r["Club_ID"]:
                self.player_clubs[r["Player_ID"]].add(r["Club_ID"])

        for table in ("Player_Club_Season_Totals", "Player_League_Career", "Player_Club_Competition_Stats"):
            try:
                for r in q(f'SELECT Player_ID, Club_ID FROM "{table}" WHERE Club_ID IS NOT NULL'):
                    if r["Player_ID"]:
                        self.player_clubs[r["Player_ID"]].add(r["Club_ID"])
            except sqlite3.OperationalError:
                continue

    # ------------------------------------------------------------------ match
    def candidates(self, raw_name: str, club_id: str | None = None, limit: int = 5) -> list[dict]:
        key = normalise(raw_name)
        if not key:
            return []

        exact = self.index.get(key)
        scored: dict[str, float] = {}
        reasons: dict[str, list[str]] = defaultdict(list)

        if exact:
            for pid in exact:
                scored[pid] = 1.0
                reasons[pid].append("正規化後完全相同")

        raw_parts = syllables(raw_name)
        for other_key, pids in self.index.items():
            if other_key == key:
                continue
            other_parts = self.parts.get(other_key, [])
            tokens = token_similarity(raw_parts, other_parts)
            # a flat string match still needs the surname to agree
            flat = similarity(key, other_key) if tokens > 0 else 0.0
            score = max(flat, tokens)
            if score < 0.60:
                continue
            why = [f"姓氏與名相符 {tokens:.0%}"] if tokens >= flat else [f"字面相似 {flat:.0%}"]
            if len(raw_parts) > 1 and len(other_parts) > 1:
                a_last = "".join(raw_parts[1:])
                b_last = "".join(other_parts[1:])
                if a_last == b_last:
                    why.append("姓氏完全相同")
                elif similarity(a_last, b_last) >= 0.85:
                    why.append("姓氏高度相近")
            for pid in pids:
                if score > scored.get(pid, 0):
                    scored[pid] = score
                    reasons[pid] = why

        results = []
        for pid, score in scored.items():
            boosted = score
            note = list(dict.fromkeys(reasons[pid]))
            if club_id and club_id in self.player_clubs.get(pid, ()):  # same club is strong corroboration
                # corroboration can raise confidence but must never manufacture an
                # exact match: 1.0 is reserved for names that normalise identically
                boosted = min(0.98, score + 0.18)
                note.append("俱樂部吻合")
            results.append({
                "id": pid,
                "name": self.canonical.get(pid, pid),
                "score": round(boosted, 3),
                "baseScore": round(score, 3),
                "reasons": note,
                "evidence": dict(self.evidence[pid]),
            })

        results.sort(key=lambda r: -r["score"])
        return results[:limit]

    @staticmethod
    def verdict(candidates: list[dict]) -> str:
        """How the queue should present this name to the person deciding."""
        if not candidates:
            return "no_candidate"
        top = candidates[0]
        runner = candidates[1]["score"] if len(candidates) > 1 else 0.0
        if top["score"] >= 0.995:
            return "exact"
        if top["score"] >= 0.80 and (top["score"] - runner) >= 0.10:
            return "strong"
        if top["score"] >= 0.65:
            return "weak"
        return "no_candidate"


    # -------------------------------------------------------------- clustering
    def cluster_backlog(self, names: list[str], threshold: float = 0.82) -> list[list[str]]:
        """Group unresolved names that are probably the same uncontrolled person.

        Most of the backlog is players the archive never controlled at all, so
        before minting IDs the variants among THEMSELVES have to be merged —
        otherwise one player leaves with three Player_IDs.
        """
        keys = {name: normalise(name) for name in names}
        parts = {name: syllables(name) for name in names}
        parent = {name: name for name in names}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        ordered = sorted(names)
        for i, a in enumerate(ordered):
            for b in ordered[i + 1:]:
                tokens = token_similarity(parts[a], parts[b])
                score = max(similarity(keys[a], keys[b]) if tokens > 0 else 0.0, tokens)
                if score >= threshold:
                    union(a, b)

        groups = defaultdict(list)
        for name in ordered:
            groups[find(name)].append(name)
        return [sorted(v) for v in groups.values()]
