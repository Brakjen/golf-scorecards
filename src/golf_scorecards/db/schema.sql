CREATE TABLE IF NOT EXISTS users (
    id              TEXT PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    is_admin        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rounds (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL DEFAULT '',
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
    opponent_name   TEXT,
    opponent_handicap REAL,
    strokes_given   INTEGER,
    team_size       INTEGER,
    teammates       TEXT,
    holes_played    TEXT NOT NULL DEFAULT '18' CHECK(holes_played IN ('18', 'front_9', 'back_9')),
    notes           TEXT,
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
    penalty_strokes INTEGER,
    miss_direction  TEXT,
    up_and_down     INTEGER,
    sand_save       INTEGER,
    sz_in_reg       INTEGER,
    down_in_3       INTEGER,
    nfs             INTEGER,
    hole_result     TEXT,
    drive_used      TEXT,
    notes           TEXT,
    UNIQUE(round_id, hole_number)
);

CREATE TABLE IF NOT EXISTS insights_cache (
    id              TEXT PRIMARY KEY,
    cache_key       TEXT NOT NULL DEFAULT 'dashboard',
    generated_at    TEXT NOT NULL,
    rounds_hash     TEXT NOT NULL,
    insights_json   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key     TEXT NOT NULL,
    user_id TEXT NOT NULL DEFAULT '',
    value   TEXT NOT NULL,
    PRIMARY KEY (key, user_id)
);

CREATE TABLE IF NOT EXISTS practice_sessions (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL DEFAULT '',
    title           TEXT,
    session_date    TEXT NOT NULL,
    notes           TEXT,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS practice_attempts (
    id              TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES practice_sessions(id) ON DELETE CASCADE,
    station_slug    TEXT NOT NULL,
    attempt_number  INTEGER NOT NULL,
    strokes         INTEGER NOT NULL,
    nfs             INTEGER NOT NULL DEFAULT 0,
    UNIQUE(session_id, station_slug, attempt_number)
);
