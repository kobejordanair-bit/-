"""Regression tests for the entity matchers.

Every case here is one that was decided by looking at real archive data, and
several encode a bug that was actually shipped. They exist so the scoring can
be changed without silently undoing that reasoning.

    python3 -m pytest test_resolver.py -q
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from resolver import (ClubResolver, CompetitionResolver, IdentityResolver, club_key,
                      competition_category, competition_keys, is_truncated, league_key,
                      normalise, sheet_league, similarity, start_year, strip_stage, syllables,
                      tier_signature, to_trad, token_similarity)

DB = Path(__file__).parent / "data" / "fm24.sqlite"
needs_db = pytest.mark.skipif(not DB.exists(), reason="run etl.py first")


# --------------------------------------------------------------- conversion --

class TestScriptConversion:
    """OpenCC's s2t is not idempotent; to_trad has to converge anyway."""

    @pytest.mark.parametrize("text", [
        "里尔足球俱乐部", "里爾足球俱樂部", "维克托·奥斯姆亨", "維克托·奧斯姆亨",
        "卡利亚里", "卡利亞里", "杰里米·弗林蓬",
    ])
    def test_idempotent(self, text):
        assert to_trad(text) == to_trad(to_trad(text))

    @pytest.mark.parametrize("simplified,traditional", [
        ("里尔足球俱乐部", "里爾足球俱樂部"),   # 里 -> 裏 on the second pass
        ("维克托·奥斯姆亨", "維克托·奧斯姆亨"),  # 托 -> 託 on the second pass
        ("卡利亚里", "卡利亞里"),
        ("莱斯特城", "萊斯特城"),
    ])
    def test_scripts_converge(self, simplified, traditional):
        assert normalise(simplified) == normalise(traditional)

    def test_separators_are_stripped(self):
        assert normalise("馬克-安德烈·特爾施特根") == normalise("馬克 安德烈 特爾施特根")


# ------------------------------------------------------------- similarity ---

class TestSimilarity:
    def test_identical_is_one(self):
        assert similarity("abc", "abc") == 1.0

    def test_empty_is_zero(self):
        assert similarity("", "abc") == 0.0

    def test_single_character_difference_scores_high(self):
        """Bigrams alone gave this 0.78; it is plainly one person."""
        a, b = normalise("马克·安德雷·特尔·施特根"), normalise("馬克-安德烈·特爾施特根")
        assert similarity(a, b) >= 0.88

    def test_unrelated_names_score_low(self):
        assert similarity(normalise("路易斯·迪亚斯"), normalise("鲁本·迪亚斯")) < 0.6


class TestSurnameGate:
    """A transliterated given name repeats too often to carry a match."""

    @pytest.mark.parametrize("a,b", [
        ("亚历山德罗·布翁乔尔诺", "亚历山德罗·希尔卡迪"),
        ("多米尼克·索朗克", "多米尼克·利瓦科維奇"),
    ])
    def test_shared_given_name_is_rejected(self, a, b):
        assert token_similarity(syllables(a), syllables(b)) == 0.0

    @pytest.mark.parametrize("a,b", [
        ("路易斯·迪亚斯", "鲁本·迪亚斯"),          # both Díaz
        ("利桑德罗·马丁内斯", "安東尼·馬丁內斯"),      # both Martínez
    ])
    def test_shared_surname_is_weak_not_confident(self, a, b):
        """An identical surname passes the gate by design; the given name then
        has to carry it, and it cannot. These belong in the review queue."""
        score = token_similarity(syllables(a), syllables(b))
        assert 0.0 < score < 0.80

    def test_known_limit_diaz_suarez(self):
        """A documented limitation, pinned so a scoring change has to face it.

        '迪亞斯' against '蘇亞雷斯' is two edits over four characters, landing
        the surname on exactly the gate, so the pair is not rejected outright.
        The same threshold is what admits de Ligt below, so it stands — but the
        pair must never reach the confident band, because it is two people.
        """
        score = token_similarity(syllables("路易斯·迪亚斯"), syllables("路易斯·蘇亞雷斯"))
        assert score > 0.0, "if this rejects again, de Ligt probably broke too"
        assert score < 0.80, "must stay out of the strong band"

    def test_de_ligt_survives_the_same_threshold(self):
        """The true match that the Díaz/Suárez threshold pays for."""
        score = similarity(normalise("马泰斯·德·莱特"), normalise("馬泰斯·德里赫特"))
        assert score >= 0.65

    @pytest.mark.parametrize("a,b", [
        ("古格列莫·维卡里奥", "古格列奧·維卡里奧"),
        ("马克·安德雷·特尔·施特根", "馬克-安德烈·特爾施特根"),
        ("维尼修斯·儒尼奥尔", "維尼休斯·儒尼奧爾"),
    ])
    def test_same_person_survives(self, a, b):
        assert token_similarity(syllables(a), syllables(b)) >= 0.80

    def test_brothers_are_not_merged(self):
        """Lucas and Theo Hernández share a surname exactly but are two people."""
        score = token_similarity(syllables("卢卡斯·埃尔南德斯-卡斯坎特"),
                                 syllables("西奥·埃尔南德斯-卡斯坎特"))
        assert score < 0.82  # below the clustering threshold


# ------------------------------------------------------------------ clubs ---

class TestClubKey:
    @pytest.mark.parametrize("name,expected_same_as", [
        ("里爾足球俱樂部", "里爾"),
        ("VfB斯图加特", "斯圖加特"),
        ("奥格斯堡足球俱乐部", "奧格斯堡"),
        ("梅斯FC", "梅斯"),
        ("FC波尔图二队", "波尔图二队"),
    ])
    def test_affixes_are_stripped(self, name, expected_same_as):
        assert club_key(name) == club_key(expected_same_as)

    def test_distinct_clubs_stay_distinct(self):
        assert club_key("曼彻斯特城") != club_key("曼彻斯特联")

    @pytest.mark.parametrize("name,truncated", [
        ("多特蒙德足球俱...", True), ("多特蒙德足球俱樂部", False), ("里昂", False),
    ])
    def test_truncation_detected(self, name, truncated):
        assert is_truncated(name) is truncated


# ----------------------------------------------------------------- leagues --

class TestLeagueKeys:
    @pytest.mark.parametrize("text,key", [
        ("LaLiga EA Sports", "LALIGA"), ("LaLiga", "LALIGA"),
        ("Serie A TIM", "SERIEA"), ("Ligue 1 Uber Eats", "LIGUE1"),
        ("Premier League", "PL"), ("Bundesliga", "BUNDESLIGA"),
        ("Eredivisie", None), (None, None),
    ])
    def test_sponsored_names_fold(self, text, key):
        assert league_key(text) == key

    @pytest.mark.parametrize("sheet,key", [
        ("Bundesliga_Elf_des_Jahres", "BUNDESLIGA"), ("PL_PFA_Team_of_Year", "PL"),
        ("Golden_Shoe", None), ("Ballon_dOr", None),  # cross-league: no signal
    ])
    def test_sheet_league(self, sheet, key):
        assert sheet_league(sheet) == key

    @pytest.mark.parametrize("season,year", [
        ("2033-2034", 2033), ("2033/34", 2033), ("2033-34", 2033), (None, None),
    ])
    def test_season_start_year(self, season, year):
        assert start_year(season) == year


# ----------------------------------------------------- against the archive --

@pytest.fixture(scope="module")
def con():
    return sqlite3.connect(DB)


@needs_db
class TestPlayerResolution:
    def test_exact_alias_resolves(self, con):
        r = IdentityResolver(con)
        best = r.candidates("Kim Min-Jae")[0]
        assert best["id"] == "P-0002" and best["score"] == 1.0

    def test_transliteration_variant_resolves(self, con):
        r = IdentityResolver(con)
        best = r.candidates("维尼修斯·儒尼奥尔")[0]
        assert "儒尼奧爾" in best["name"] and best["score"] >= 0.85

    def test_strong_name_survives_league_mismatch(self, con):
        """ter Stegen's award sits on a Ligue 1 club; the archive knows him in LaLiga."""
        r = IdentityResolver(con)
        best = r.candidates("马克·安德雷·特尔·施特根", league="LIGUE1")[0]
        assert best["score"] >= 0.85
        assert any("轉會" in x for x in best["reasons"])

    def test_weak_name_is_demoted_by_league_mismatch(self, con):
        r = IdentityResolver(con)
        plain = r.candidates("贡萨洛·拉莫斯")
        with_league = r.candidates("贡萨洛·拉莫斯", league="LIGUE1")
        top_plain = plain[0]["score"] if plain else 0
        top_league = with_league[0]["score"] if with_league else 0
        assert top_league < top_plain

    def test_corroboration_never_manufactures_an_exact_match(self, con):
        r = IdentityResolver(con)
        for item in r.candidates("拉斯马斯·温特·霍兰德", club_id="C-0042", league="PL"):
            if item["baseScore"] < 1.0:
                assert item["score"] <= 0.98

    def test_clustering_is_conservative(self, con):
        r = IdentityResolver(con)
        names = [x[0] for x in con.execute(
            "SELECT DISTINCT Player_Raw FROM Award_Resolution_Status "
            "WHERE Resolution_Status='UNRESOLVED_IDENTITY'")]
        merges = [g for g in r.cluster_backlog(names) if len(g) > 1]
        assert len(merges) <= 5, f"clustering got loose: {merges}"


@needs_db
class TestClubResolution:
    def test_script_variant_resolves_after_idempotency_fix(self, con):
        assert ClubResolver(con).resolve("里尔足球俱乐部") == "C-0100"

    def test_affix_variant_is_a_candidate(self, con):
        best = ClubResolver(con).candidates("VfB斯图加特")[0]
        assert best["name"] == "斯圖加特" and best["score"] >= 0.9

    def test_truncated_source_matches_by_prefix(self, con):
        best = ClubResolver(con).candidates("多特蒙德足球俱...")[0]
        assert best["id"] == "C-0125"
        assert any("截斷" in x for x in best["reasons"])

    def test_unregistered_club_has_no_candidate(self, con):
        assert ClubResolver(con).candidates("水晶宫") == []

    def test_duplicates_are_found(self, con):
        dupes = ClubResolver(con).duplicates()
        pairs = {tuple(d["ids"]) for d in dupes}
        assert ("C-0119", "C-0195") in pairs   # Southampton, both carry data
        assert ("C-0068", "C-0100") in pairs   # Lille, with and without the affix


# ----------------------------------------------------------- competitions --

class TestCompetitionKeys:
    @pytest.mark.parametrize("a,b", [
        ("LaLiga EA Sports", "LaLiga"),
        ("Serie A TIM", "Serie A"),
        ("Ligue 1 Uber Eats", "Ligue 1"),
        ("Trendyol Süper Lig", "Süper Lig"),
    ])
    def test_sponsor_is_not_part_of_identity(self, a, b):
        assert competition_keys(a) & competition_keys(b)

    @pytest.mark.parametrize("bilingual,half", [
        ("西甲 LaLiga", "LaLiga"),
        ("英超 Premier League", "Premier League"),
        ("英格蘭足總盃 FA Cup", "FA Cup"),
        ("德甲 Bundesliga", "Bundesliga"),
    ])
    def test_bilingual_form_reaches_either_half(self, bilingual, half):
        assert competition_keys(bilingual) & competition_keys(half)

    @pytest.mark.parametrize("name,expected", [
        ("Copa del Rey决赛", "Copa del Rey"),
        ("Copa del Rey半决赛第1回合", "Copa del Rey"),
        ("FIFA Club World Cup1/4决赛", "FIFA Club World Cup"),
        ("Premier League", "Premier League"),
    ])
    def test_knockout_round_is_stripped(self, name, expected):
        assert strip_stage(name) == expected


class TestTierGuard:
    """A division number is the whole difference between two competitions."""

    @pytest.mark.parametrize("top,second", [
        ("LaLiga", "LaLiga 2"), ("Bundesliga", "2. Bundesliga"),
        ("Ligue 1", "Ligue 2"), ("Liga Portugal", "Liga Portugal 2"),
    ])
    def test_divisions_have_different_signatures(self, top, second):
        assert tier_signature(top) != tier_signature(second)

    @pytest.mark.parametrize("a,b", [
        ("LaLiga", "LaLiga EA Sports"), ("Premier League", "英超 Premier League"),
    ])
    def test_spelling_variants_share_a_signature(self, a, b):
        assert tier_signature(a) == tier_signature(b)


class TestCompetitionCategories:
    @pytest.mark.parametrize("name,category", [
        ("联赛", "LEAGUE"), ("聯賽", "LEAGUE"), ("League", "LEAGUE"),
        ("杯赛", "CUP"), ("Cup", "CUP"),
        ("洲际级别", "CONTINENTAL"), ("Continental", "CONTINENTAL"),
        ("非正式比赛", "OTHER"),
        ("LaLiga EA Sports", None), ("Premier League", None),
    ])
    def test_categories_are_recognised_in_both_languages(self, name, category):
        assert competition_category(name) == category


@needs_db
class TestCompetitionResolution:
    def test_a_category_never_matches_a_competition(self, con):
        r = CompetitionResolver(con)
        assert r.candidates("联赛") == []
        assert r.candidates("League") == []

    def test_script_variant_resolves(self, con):
        assert CompetitionResolver(con).resolve("欧洲冠军联赛") == "COMP-0005"

    def test_clustering_merges_spellings_not_divisions(self, con):
        r = CompetitionResolver(con)
        names = ["LaLiga", "LaLiga EA Sports", "西甲 LaLiga", "LaLiga 2",
                 "Bundesliga", "德甲 Bundesliga", "2. Bundesliga",
                 "Copa del Rey决赛", "Copa del Rey半决赛第1回合", "Supercopa决赛"]
        groups = {frozenset(g) for g in r.cluster(names)}
        assert frozenset({"LaLiga", "LaLiga EA Sports", "西甲 LaLiga"}) in groups
        assert frozenset({"LaLiga 2"}) in groups
        assert frozenset({"Bundesliga", "德甲 Bundesliga"}) in groups
        assert frozenset({"2. Bundesliga"}) in groups
        assert frozenset({"Copa del Rey决赛", "Copa del Rey半决赛第1回合"}) in groups
        assert frozenset({"Supercopa决赛"}) in groups


# --------------------------------------------------------- query integrity --

@needs_db
class TestColumnGuard:
    def test_sqlite_resolves_an_unknown_quoted_identifier_as_a_literal(self, con):
        """The quirk the Archive.has() guard exists for.

        A survey built without it invents a column's worth of data that looks
        completely real: this returns the text 'Competition_Raw', not an error.
        """
        value = con.execute('SELECT "Competition_Raw" FROM UCL_Knockout_Results LIMIT 1').fetchone()[0]
        assert value == "Competition_Raw"

    def test_archive_guard_rejects_missing_columns(self):
        from build_site import Archive
        archive = Archive(DB)
        assert archive.has("UCL_Knockout_Results", "Season")
        assert not archive.has("UCL_Knockout_Results", "Competition_Raw")
        assert not archive.has("No_Such_Table", "Season")
