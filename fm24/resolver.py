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
    _convert = _S2T.convert
except Exception:  # pragma: no cover - resolver still works, just less well
    def _convert(text: str) -> str:
        return text


def to_trad(text: str) -> str:
    """Convert to Traditional and keep converting until it stops changing.

    OpenCC's s2t is not idempotent: it reads an already-Traditional 里 as the
    Simplified form and rewrites it to 裏 (likewise 托 -> 託). One pass therefore
    sends a Simplified source and its Traditional counterpart to DIFFERENT
    strings — '里尔足球俱乐部' became 里爾足球俱樂部 while the dimension's own
    '里爾足球俱樂部' became 裏爾足球俱樂部, so the two never matched.

    Iterating to the fixed point lands both on the same form without needing a
    hand-kept table of variant characters. This is a comparison key only; no
    source value is ever rewritten with it.
    """
    for _ in range(4):
        nxt = _convert(text)
        if nxt == text:
            return text
        text = nxt
    return text

SEPARATORS = re.compile(r"[·・.·‧•\s\-_]+")

LEAGUE_PATTERNS = [
    ("PL", ("premier league", "premierleague")),
    ("LALIGA", ("laliga", "la liga", "primera")),
    ("SERIEA", ("serie a", "seriea")),
    ("LIGUE1", ("ligue 1", "ligue1")),
    ("BUNDESLIGA", ("bundesliga",)),
]

LEAGUE_LABELS = {
    "PL": "Premier League", "LALIGA": "LaLiga", "SERIEA": "Serie A",
    "LIGUE1": "Ligue 1", "BUNDESLIGA": "Bundesliga",
}

# Award sheets whose name pins the competition. Cross-league awards
# (European Golden Shoe, Ballon d'Or, UCL) are deliberately absent: their
# winners come from anywhere, so the sheet name carries no league signal.
SHEET_LEAGUES = [
    ("bundesliga", "BUNDESLIGA"),
    ("serie_a", "SERIEA"),
    ("ligue1", "LIGUE1"),
    ("pl_", "PL"),
    ("premier_league", "PL"),
    ("laliga", "LALIGA"),
    ("pichichi", "LALIGA"),
]


def league_key(text: str | None) -> str | None:
    """Fold a competition string to a stable key.

    The same league is spelled differently per table — 'LaLiga EA Sports' in the
    standings, 'LaLiga' in the career rows — so neither can be joined directly.
    """
    if not text:
        return None
    low = str(text).strip().lower()
    for key, needles in LEAGUE_PATTERNS:
        if any(n in low for n in needles):
            return key
    return None


def sheet_league(sheet: str | None) -> str | None:
    if not sheet:
        return None
    low = str(sheet).strip().lower()
    for prefix, key in SHEET_LEAGUES:
        if low.startswith(prefix):
            return key
    return None


def start_year(season: str | None) -> int | None:
    """'2033-2034', '2033/34' and '2033-34' all start in 2033."""
    if not season:
        return None
    m = re.search(r"(20\d\d)", str(season))
    return int(m.group(1)) if m else None



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


def edit_distance(a: str, b: str) -> int:
    """Plain Levenshtein. Names are short, so the simple DP row is enough."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def similarity(a: str, b: str) -> float:
    """How alike two normalised names are, on the most generous of three views.

    Bigrams and character overlap both under-score a long name that differs by a
    single character — '馬克安德雷特爾施特根' against '馬克安德烈特爾施特根' scores
    0.78 on bigrams though it is plainly one transliteration of one person — so
    edit distance carries those, and the set measures carry reorderings.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ba, bb = bigrams(a), bigrams(b)
    dice = (2 * len(ba & bb)) / (len(ba) + len(bb)) if (ba or bb) else 0.0
    ca, cb = set(a), set(b)
    chars = (2 * len(ca & cb)) / (len(ca) + len(cb))
    edits = 1.0 - edit_distance(a, b) / max(len(a), len(b))
    return max(dice, chars * 0.85, edits)


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
        self.club_leagues: dict[str, set[str]] = defaultdict(set)
        self.player_leagues: dict[str, set[str]] = defaultdict(set)
        self.player_seasons: dict[str, set[int]] = defaultdict(set)
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
        # --- league and season context -----------------------------------
        # Which league a club plays in, keyed by Club_ID. The standings sheet
        # names clubs in Simplified and carries no Club_ID at all, so the join
        # runs through the same normalisation the player names use.
        club_key_to_id: dict[str, str] = {}
        for r in q("SELECT Club_ID, Canonical_Display_Name, Alias_Name FROM Club_Dim WHERE Club_ID IS NOT NULL"):
            for name in (r["Canonical_Display_Name"], r["Alias_Name"]):
                key = normalise(name)
                if key:
                    club_key_to_id.setdefault(key, r["Club_ID"])

        for r in q("SELECT DISTINCT Club_Raw, Competition_Raw FROM Domestic_League_Standings"):
            league = league_key(r["Competition_Raw"])
            club_id = club_key_to_id.get(normalise(r["Club_Raw"]))
            if league and club_id:
                self.club_leagues[club_id].add(league)

        for r in q("SELECT Club_ID, League_Raw FROM Player_League_Career WHERE Club_ID IS NOT NULL"):
            league = league_key(r["League_Raw"])
            if league:
                self.club_leagues[r["Club_ID"]].add(league)

        # A player's leagues: stated directly where the archive knows them,
        # otherwise inferred from the clubs they appear with.
        for r in q("SELECT Player_ID, League_Raw, Season_Display FROM Player_League_Career"):
            pid = r["Player_ID"]
            if not pid:
                continue
            league = league_key(r["League_Raw"])
            if league:
                self.player_leagues[pid].add(league)
            year = start_year(r["Season_Display"])
            if year:
                self.player_seasons[pid].add(year)

        for pid, clubs in self.player_clubs.items():
            for club_id in clubs:
                self.player_leagues[pid] |= self.club_leagues.get(club_id, set())

        for table, column in (("Player_Club_Season_Totals", "Season_Display"),
                              ("Canonical_Award_Facts", "Season")):
            try:
                for r in q(f'SELECT Player_ID, "{column}" s FROM "{table}" WHERE Player_ID IS NOT NULL'):
                    year = start_year(r["s"])
                    if year:
                        self.player_seasons[r["Player_ID"]].add(year)
            except sqlite3.OperationalError:
                continue


    # ------------------------------------------------------------------ match
    def candidates(self, raw_name: str, club_id: str | None = None, limit: int = 5,
                   league: str | None = None, season_year: int | None = None) -> list[dict]:
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
                boosted = min(0.98, boosted + 0.18)
                note.append("俱樂部吻合")

            known_leagues = self.player_leagues.get(pid, set())
            if league and known_leagues:
                if league in known_leagues:
                    boosted = min(0.98, boosted + 0.10)
                    note.append(f"{LEAGUE_LABELS.get(league, league)} 相符")
                else:
                    other = "、".join(sorted(LEAGUE_LABELS.get(k, k) for k in known_leagues))
                    # League disagreement only decides marginal cases. When the
                    # name evidence is already strong the likelier story is a
                    # transfer the archive has not recorded, so the mismatch is
                    # reported without moving the score.
                    if score >= 0.90:
                        note.append(f"聯賽不符（{other}），但姓名證據強，可能為轉會")
                    else:
                        boosted = max(0.0, boosted - 0.14)
                        note.append("聯賽不符：" + other)

            known_years = self.player_seasons.get(pid, set())
            if season_year and known_years:
                gap = min(abs(season_year - y) for y in known_years)
                if gap == 0:
                    boosted = min(0.98, boosted + 0.06)
                    note.append("該賽季在檔")
                elif gap > 3:
                    boosted = max(0.0, boosted - 0.10)
                    note.append(f"生涯紀錄相距 {gap} 季")

            if boosted < 0.55:
                continue
            results.append({
                "id": pid,
                "name": self.canonical.get(pid, pid),
                "score": round(boosted, 3),
                "baseScore": round(score, 3),
                "reasons": note,
                "evidence": dict(self.evidence[pid]),
                "leagues": sorted(LEAGUE_LABELS.get(k, k) for k in known_leagues),
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


# ---------------------------------------------------------------------------
# Clubs
# ---------------------------------------------------------------------------

# Club names carry corporate affixes that the same club is written with or
# without across tables — '里爾' and '里爾足球俱樂部' are one club with two
# Club_IDs. Stripping them gives a second, looser key for matching and for
# spotting duplicate identities.
CLUB_SUFFIX = re.compile(
    r"(足球俱樂部|足球俱乐部|競賽俱樂部|竞赛俱乐部|體育俱樂部|体育俱乐部"
    r"|俱樂部|俱乐部|足球會|足球会|足球隊|足球队)$")
CLUB_PREFIX = re.compile(
    r"^(?:1\.\s*)?(?:FC|CF|AC|AS|RC|SC|SV|SS|SSC|US|VfB|VfL|TSG|BSC|RB|OGC|OL|AFC|CD|UD|RCD)\s*",
    re.IGNORECASE)
CLUB_TRAIL = re.compile(r"\s*(?:FC|CF|AC|AS|RC|SC|AFC|CD|UD)\.?$", re.IGNORECASE)

# The source truncates long club names with an ellipsis ('多特蒙德足球俱...'),
# which no exact key can match but a prefix comparison still can.
TRUNCATED = re.compile(r"(\.{2,}|…)\s*$")


def is_truncated(name: str | None) -> bool:
    return bool(name and TRUNCATED.search(str(name)))


def club_key(name: str | None) -> str:
    """A club's identity key with corporate affixes removed."""
    if not name:
        return ""
    text = TRUNCATED.sub("", to_trad(str(name).strip())).strip()
    previous = None
    while previous != text:
        previous = text
        text = CLUB_SUFFIX.sub("", text)
        text = CLUB_PREFIX.sub("", text)
        text = CLUB_TRAIL.sub("", text)
    return normalise(text)


# Columns that genuinely name a CLUB. Kept as an explicit list rather than a
# pattern because a regex over column names also catches nation columns —
# Intl_Tournament_Results.Winner holds 葡萄牙, not a club — which inflates the
# backlog with entities that were never meant to have a Club_ID.
CLUB_REFERENCE_COLUMNS = [
    ("Domestic_League_Standings", "Club_Raw"), ("Barcelona_Transfers", "Counterparty_Club"),
    ("Player_League_Career", "Club_Raw"), ("Player_Club_Competition_Stats", "Club_Raw"),
    ("Player_Club_Season_Totals", "Club_Raw"), ("Canonical_Award_Facts", "Club_Raw"),
    ("National_Tournaments", "Club"), ("Canonical_Competition_Results", "Club_Raw"),
    ("Canonical_Competition_Results", "Opponent_Raw"), ("Domestic_Leagues", "Club"),
    ("Competition_History", "Winner_Raw"), ("Competition_History", "Runner_Up_Raw"),
    ("UCL_Season_Leaders", "Club"), ("Youth_Awards", "Club"), ("Golden_Shoe", "Club_Raw"),
    ("FIFA_FIFPro_World_XI", "Club"), ("Retirement_Career_History", "Club_Raw"),
    ("El_Clasico_Match_History", "Home_Club_Raw"), ("El_Clasico_Match_History", "Away_Club_Raw"),
    ("Club_Cup_History", "Club_Raw"), ("UCL", "Winner"), ("UCL", "Runner_Up"),
    ("Ballon_dOr", "Club"), ("LaLiga_2034_35_Table_RAW", "Club_Raw"),
    ("PL_2034_35_Table_RAW", "Club_Raw"),
]


class ClubResolver:
    """Resolves club references and finds club identities that were split in two."""

    def __init__(self, con: sqlite3.Connection):
        self.con = con
        con.row_factory = sqlite3.Row
        self.canonical: dict[str, str] = {}
        self.exact: dict[str, str] = {}
        self.stripped: dict[str, set[str]] = defaultdict(set)
        self.club_leagues: dict[str, set[str]] = defaultdict(set)
        self.full_keys: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        for r in self.con.execute(
            "SELECT Club_ID, Canonical_Display_Name, Alias_Name FROM Club_Dim WHERE Club_ID IS NOT NULL"
        ):
            cid = r["Club_ID"]
            name = r["Canonical_Display_Name"] or r["Alias_Name"]
            if name:
                self.canonical.setdefault(cid, name)
            for value in (r["Canonical_Display_Name"], r["Alias_Name"]):
                if not value:
                    continue
                key = normalise(value)
                if key:
                    self.exact.setdefault(key, cid)
                loose = club_key(value)
                if loose:
                    self.stripped[loose].add(cid)
                if key:
                    self.full_keys.setdefault(key, cid)

        # which league each club plays in, for the same corroboration the player
        # resolver uses; the standings name clubs without any Club_ID at all
        for r in self.con.execute("SELECT DISTINCT Club_Raw, Competition_Raw FROM Domestic_League_Standings"):
            key = league_key(r["Competition_Raw"])
            cid = self.exact.get(normalise(r["Club_Raw"])) or next(
                iter(self.stripped.get(club_key(r["Club_Raw"]), ())), None)
            if key and cid:
                self.club_leagues[cid].add(key)
        try:
            for r in self.con.execute("SELECT Club_ID, League_Raw FROM Player_League_Career WHERE Club_ID IS NOT NULL"):
                key = league_key(r["League_Raw"])
                if key:
                    self.club_leagues[r["Club_ID"]].add(key)
        except sqlite3.OperationalError:
            pass

    def resolve(self, raw: str | None) -> str | None:
        """The Club_ID this string already maps to, if any."""
        key = normalise(raw)
        return self.exact.get(key) if key else None

    def candidates(self, raw: str, league: str | None = None, limit: int = 5) -> list[dict]:
        key = normalise(raw)
        loose = club_key(raw)
        scored: dict[str, float] = {}
        reasons: dict[str, list[str]] = defaultdict(list)

        if key and key in self.exact:
            cid = self.exact[key]
            scored[cid] = 1.0
            reasons[cid].append("正規化後完全相同")

        for cid in self.stripped.get(loose, ()):  # same club, different corporate affix
            if scored.get(cid, 0) < 0.95:
                scored[cid] = 0.95
                reasons[cid] = ["去除俱樂部綴詞後相同"]

        if is_truncated(raw):
            # '多特蒙德足球俱...' is a prefix of the club's full name, so compare
            # against the unstripped keys — the stripped ones are shorter than
            # the fragment itself and can never contain it.
            stem = normalise(TRUNCATED.sub("", to_trad(str(raw).strip())))
            if stem:
                for full, cid in self.full_keys.items():
                    if full.startswith(stem) and scored.get(cid, 0) < 0.92:
                        scored[cid] = 0.92
                        reasons[cid] = ["來源字串被截斷，前綴相符"]

        for other, cids in self.stripped.items():
            if other == loose:
                continue
            score = similarity(loose, other)
            if score < 0.70:
                continue
            for cid in cids:
                if score > scored.get(cid, 0):
                    scored[cid] = score
                    reasons[cid] = [f"字面相似 {score:.0%}"]

        results = []
        for cid, score in scored.items():
            boosted = score
            note = list(dict.fromkeys(reasons[cid]))
            known = self.club_leagues.get(cid, set())
            if league and known:
                if league in known:
                    boosted = min(0.98, boosted + 0.08) if score < 1.0 else score
                    note.append(f"{LEAGUE_LABELS.get(league, league)} 相符")
                else:
                    if score < 0.90:
                        boosted = max(0.0, boosted - 0.12)
                    note.append("聯賽不符：" + "、".join(
                        sorted(LEAGUE_LABELS.get(k, k) for k in known)))
            if boosted < 0.62:
                continue
            results.append({
                "id": cid,
                "name": self.canonical.get(cid, cid),
                "score": round(boosted, 3),
                "reasons": note,
                "leagues": sorted(LEAGUE_LABELS.get(k, k) for k in known),
            })
        results.sort(key=lambda r: -r["score"])
        return results[:limit]

    def duplicates(self) -> list[dict]:
        """Club_IDs that share an affix-stripped key: one club recorded twice."""
        out = []
        for key, cids in self.stripped.items():
            if len(cids) < 2:
                continue
            members = sorted(cids)
            out.append({
                "key": key,
                "ids": members,
                "names": [self.canonical.get(c, c) for c in members],
            })
        return sorted(out, key=lambda d: d["ids"])
