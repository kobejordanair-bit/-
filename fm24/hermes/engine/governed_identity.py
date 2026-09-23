"""Deterministic existing-identity lookup using a pinned Han character table.

ICU74-derived T->S single-character mappings plus two governed middle dots.
Raw names remain unchanged; normalized collisions fail closed. This performs
neither phonetic conversion nor edit-distance matching. Production needs only
standard-library JSON, not an ICU/OpenCC installation.
"""
from __future__ import annotations

from collections import defaultdict

from generic_importer import ImportFailure, headers

# The versioned table is immutable and SHA-verified at import.
import hashlib
import json
from pathlib import Path
_TABLE_BYTES = Path(__file__).with_name('t2s_icu74.json').read_bytes()
_TABLE_SHA = 'b4be18c13eb88d10cd249d37c332efe44a51bb0c768fd198c1b1755f35718f83'
if hashlib.sha256(_TABLE_BYTES).hexdigest() != _TABLE_SHA:
    raise RuntimeError('NORMALIZATION_TABLE_HASH_MISMATCH')
_TRADITIONAL_SIMPLIFIED = json.loads(_TABLE_BYTES)['mapping']
_MIDDLE_DOTS = {"·": "·", "・": "·"}
RULE = "pinned_icu74_han_t2s_and_middle_dot_v2"


def normalized_candidate_form(token: str) -> str:
    """Return a deterministic lookup key without changing the supplied token."""
    return "".join(_MIDDLE_DOTS.get(ch, _TRADITIONAL_SIMPLIFIED.get(ch, ch)) for ch in str(token))


def verified_dobs(wb, player_id: str) -> set[str]:
    ws = wb["Player_Profile_Snapshots"]
    h = headers(ws)
    dob_field = "DOB" if "DOB" in h else "Date_of_Birth"
    return {str(r[h[dob_field]-1]) for r in ws.iter_rows(min_row=2, values_only=True)
            if str(r[h["Player_ID"]-1]) == str(player_id) and r[h[dob_field]-1] not in (None, "")}


def normalized_existing_candidates(wb, raw_token: str) -> set[str]:
    """Search only existing Player_Dim spellings by finite normalized form."""
    target = normalized_candidate_form(raw_token)
    ws = wb["Player_Dim"]
    h = headers(ws)
    candidates = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        pid = str(row[h["Player_ID"]-1])
        for name_field in ("Canonical_Display_Name", "Alias_Name"):
            token = row[h[name_field]-1]
            if token not in (None, "") and normalized_candidate_form(str(token)) == target:
                candidates.add(pid)
    return candidates


def resolve_secondary_existing_player(wb, raw_token: str, submitted_dob: str | None) -> dict:
    """Resolve one governed existing candidate; DOB only rejects an actual mismatch.

    A missing DOB on either side is recorded as unverified evidence—not silently
    upgraded to a DOB match and not misclassified as a conflict.
    """
    candidates = normalized_existing_candidates(wb, raw_token)
    if len(candidates) != 1:
        raise ImportFailure("PLAYER_IDENTITY_AMBIGUOUS")
    player_id = next(iter(candidates))
    dobs = verified_dobs(wb, player_id)
    if submitted_dob and dobs and dobs != {str(submitted_dob)}:
        raise ImportFailure("PLAYER_IDENTITY_AMBIGUOUS")
    dob_evidence = (str(submitted_dob) if submitted_dob and dobs == {str(submitted_dob)}
                    else "DOB_UNVERIFIED_MISSING_ON_ONE_OR_BOTH_SIDES")
    return {"player_id": player_id, "normalized_candidate_form": normalized_candidate_form(raw_token),
            "rule": RULE, "dob_evidence": dob_evidence}
