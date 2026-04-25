CREATE TABLE IF NOT EXISTS rounds (
    id              TEXT PRIMARY KEY,
    course_slug     TEXT NOT NULL,
    tee_name        TEXT NOT NULL,
    player_name     TEXT,
    round_date      TEXT NOT NULL,
    handicap_index  REAL,
    handicap_profile TEXT,
    playing_handicap INTEGER,
    course_rating   REAL,
    slope_rating    INTEGER,
    scoring_mode    TEXT NOT NULL DEFAULT 'stroke',
    target_score    INTEGER,
    holes_played    TEXT NOT NULL DEFAULT '18' CHECK(holes_played IN ('18', 'front_9', 'back_9')),
    course_snapshot TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS round_holes (
    id              TEXT PRIMARY KEY,
    round_id        TEXT NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
    hole_number     INTEGER NOT NULL,
    par             INTEGER NOT NULL,
    distance        INTEGER NOT NULL,
    handicap        INTEGER NOT NULL,
    score           INTEGER,
    putts           INTEGER,
    fir             INTEGER,
    gir             INTEGER,
    penalty_strokes INTEGER,
    miss_direction  TEXT,
    up_and_down     INTEGER,
    sand_save       INTEGER,
    sz_in_reg       INTEGER,
    down_in_3       INTEGER,
    putt_under_4ft  INTEGER,
    made_over_4ft   INTEGER,
    notes           TEXT,
    UNIQUE(round_id, hole_number)
);

CREATE TABLE IF NOT EXISTS insights_cache (
    id              TEXT PRIMARY KEY,
    generated_at    TEXT NOT NULL,
    rounds_hash     TEXT NOT NULL,
    insights_json   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
