# Transcription contract

Each TXT starts exactly with `FORMAT=FM_WORLD_IMPORT_V1_1` (underscore, not `V1.1`).
Blank lines separate sections. Values are literal source observations; `NULL` or `-` means unknown.
Do not include Markdown fences, explanatory prose, or `EXTRACTION_ISSUES` in the TXT. Put ambiguities
in the batch review instead. Reject rather than silently strip unknown sections.

```
FORMAT=FM_WORLD_IMPORT_V1_1

PLAYER
Name=<visible player name>
Snapshot=<game date YYYY-MM-DD>

CLUB_TOTALS
Season|Club|Apps_Raw|Goals|Assists|Rating
<visible season>|<visible club>|<exact starts(subs) token>|<visible goals>|<visible assists>|<visible rating>
```

The above is syntax, not data. Never send angle-bracket placeholders to the importer.
`Snapshot` is the date visible in the game or explicitly supplied by the user, never today's computer date.
Use the current ACTIVE Master for exact identity lookup; uncertain players/clubs remain unresolved.
If source Name/Raw_Name point to different players, stop that document.

PLAYER permits Name, Raw_Name, Nationality, Date_of_Birth, Current_Club, Shirt_Number, Position,
International_Caps, International_Goals, U21_Caps, U21_Goals, Snapshot. Omit unknown fields.
New players require a source-confirmed birth date; matching birth dates alone do not establish identity.

## Statistical scopes

| Section | Required identity columns | Numeric/source columns |
|---|---|---|
| LEAGUE_CAREER | Season, Club | League, Apps, Goals, Assists, POTM, Rating |
| CLUB_COMPETITION_STATS | Season, Club, Competition | Apps_Raw, Goals, Penalties, Assists, POTM, Yellow, Red, TacklesWon90, PassPct, Dribbles90, ShotsOnTargetPct, Fouls, Fouled, Rating, Goals_Conceded, Clean_Sheets |
| CLUB_TOTALS | Season, Club | Same metrics as competition rows, without Competition |
| NATIONAL_TEAM_COMPETITION_STATS | Season, National_Team_Raw, Team_Level, Context_Club, Apps_Raw | Same metrics as competition rows, without Competition |

Use pipe-delimited tables. Header names must match; row lengths must match headers.
Apps_Raw `10(3)` means 10 starts + 3 substitute appearances = 13 appearances.
League career Apps is already a total; do not reinterpret it as starts. Do not put country-team rows in club totals.
Do not calculate all-competition totals by adding the displayed total to its component rows.
Preserve League/Cup/Continental/Friendly distinctions. Do not label a source 'league' merely because the club
plays in a league. National Team_Level is `Senior` or `U21`, only when explicitly established.
If the screenshot merely says national-team games, retain it pending rather than infer the team/level.

`LEAGUE_CAREER_TOTAL` is key=value with Apps, Goals, Assists, POTM, Rating, Career_Transfer_Fees.
Use it only for a source-declared career total; do not manufacture one by adding partial seasons.

Fee / Move_Type / Nation in historical career tables are not materialized by this adapter. Non-null values
are rejected, not silently dropped. Preserve such pages for the relevant future adapter and report the limitation.

## Attributes

PLAYER_ATTRIBUTES is optional. When present, it must contain `Snapshot=` equal to PLAYER Snapshot,
`Attribute_Schema=OUTFIELD` or `GOALKEEPER`, and all 36 or 38 exact attribute names with source values 1–20.
Read the installed runtime's `hermes/engine/full_player_import_v11_attributes.py` for the exact names.
Never fill missing values from an older snapshot to make this section pass. Keep partial pages pending.

## Batch receipt

`prepare` creates the evidence list and hashes. Do not modify them. Example document entry:

```json
{"path":"player-1.txt","evidence":["<original-image-sha256>"],"review":{"checked":true,"unresolved":[]}}
```

Unresolved entries should identify image, row/field, visible alternatives and the missing clarification.
An unresolved document is rejected before any workbook write. Use separate batches only when the user
intends to adopt the independent checked data now; disclose the remaining pending data.

The fixed selector retains older/equal-priority conflicts with their observations; large conflicts do not
silently overwrite the adopted number. Examine run review warnings and report those still unresolved.
