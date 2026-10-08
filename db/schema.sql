-- Racecoe PostgreSQL schema (f1 archive, chat sessions, RAG stubs, app caches).
-- Apply with: python scripts/init_postgres.py
-- Optional pgvector pieces live in db/schema_pgvector.sql

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE SCHEMA IF NOT EXISTS f1;
CREATE SCHEMA IF NOT EXISTS chat;
CREATE SCHEMA IF NOT EXISTS rag;
CREATE SCHEMA IF NOT EXISTS app;

-- ---------- f1: Ergast-style archive ----------
CREATE TABLE IF NOT EXISTS f1.seasons (
    year        SMALLINT PRIMARY KEY,
    url         TEXT
);

CREATE TABLE IF NOT EXISTS f1.circuits (
    circuit_id    INTEGER PRIMARY KEY,
    circuit_ref   TEXT NOT NULL UNIQUE,
    name          TEXT NOT NULL,
    location      TEXT,
    country       TEXT NOT NULL,
    lat           DOUBLE PRECISION,
    lng           DOUBLE PRECISION,
    alt           INTEGER,
    url           TEXT
);

CREATE TABLE IF NOT EXISTS f1.drivers (
    driver_id     INTEGER PRIMARY KEY,
    driver_ref    TEXT NOT NULL UNIQUE,
    number        INTEGER,
    code          TEXT,
    forename      TEXT NOT NULL,
    surname       TEXT NOT NULL,
    dob           DATE,
    nationality   TEXT,
    url           TEXT
);

CREATE TABLE IF NOT EXISTS f1.constructors (
    constructor_id   INTEGER PRIMARY KEY,
    constructor_ref  TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    nationality      TEXT,
    url              TEXT
);

CREATE TABLE IF NOT EXISTS f1.status (
    status_id   INTEGER PRIMARY KEY,
    status      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS f1.races (
    race_id       INTEGER PRIMARY KEY,
    year          SMALLINT NOT NULL REFERENCES f1.seasons(year),
    round         SMALLINT NOT NULL,
    circuit_id    INTEGER NOT NULL REFERENCES f1.circuits(circuit_id),
    name          TEXT NOT NULL,
    race_date     DATE,
    race_time     TIME,
    url           TEXT,
    fp1_date      DATE,
    fp1_time      TIME,
    fp2_date      DATE,
    fp2_time      TIME,
    fp3_date      DATE,
    fp3_time      TIME,
    quali_date    DATE,
    quali_time    TIME,
    sprint_date   DATE,
    sprint_time   TIME,
    UNIQUE (year, round)
);

CREATE TABLE IF NOT EXISTS f1.results (
    result_id          INTEGER PRIMARY KEY,
    race_id            INTEGER NOT NULL REFERENCES f1.races(race_id),
    driver_id          INTEGER NOT NULL REFERENCES f1.drivers(driver_id),
    constructor_id     INTEGER NOT NULL REFERENCES f1.constructors(constructor_id),
    car_number         INTEGER,
    grid               INTEGER,
    position           INTEGER,
    position_text      TEXT,
    position_order     INTEGER,
    points             NUMERIC(6,1),
    laps               INTEGER,
    race_time          TEXT,
    milliseconds       BIGINT,
    fastest_lap        INTEGER,
    fastest_lap_rank   INTEGER,
    fastest_lap_time   TEXT,
    fastest_lap_speed  NUMERIC(10,3),
    status_id          INTEGER NOT NULL REFERENCES f1.status(status_id),
    UNIQUE (race_id, driver_id)
);

CREATE TABLE IF NOT EXISTS f1.qualifying (
    qualify_id       INTEGER PRIMARY KEY,
    race_id          INTEGER NOT NULL REFERENCES f1.races(race_id),
    driver_id        INTEGER NOT NULL REFERENCES f1.drivers(driver_id),
    constructor_id   INTEGER NOT NULL REFERENCES f1.constructors(constructor_id),
    car_number       INTEGER,
    position         INTEGER,
    q1               TEXT,
    q2               TEXT,
    q3               TEXT
);

CREATE TABLE IF NOT EXISTS f1.sprint_results (
    result_id          INTEGER PRIMARY KEY,
    race_id            INTEGER NOT NULL REFERENCES f1.races(race_id),
    driver_id          INTEGER NOT NULL REFERENCES f1.drivers(driver_id),
    constructor_id     INTEGER NOT NULL REFERENCES f1.constructors(constructor_id),
    car_number         INTEGER,
    grid               INTEGER,
    position           INTEGER,
    position_text      TEXT,
    position_order     INTEGER,
    points             NUMERIC(6,1),
    laps               INTEGER,
    race_time          TEXT,
    milliseconds       BIGINT,
    fastest_lap        INTEGER,
    fastest_lap_time   TEXT,
    status_id          INTEGER NOT NULL REFERENCES f1.status(status_id)
);

CREATE TABLE IF NOT EXISTS f1.lap_times (
    race_id        INTEGER NOT NULL REFERENCES f1.races(race_id),
    driver_id      INTEGER NOT NULL REFERENCES f1.drivers(driver_id),
    lap            INTEGER NOT NULL,
    position       INTEGER,
    lap_time       TEXT,
    milliseconds   INTEGER,
    PRIMARY KEY (race_id, driver_id, lap)
);

CREATE TABLE IF NOT EXISTS f1.pit_stops (
    race_id        INTEGER NOT NULL REFERENCES f1.races(race_id),
    driver_id      INTEGER NOT NULL REFERENCES f1.drivers(driver_id),
    stop           INTEGER NOT NULL,
    lap            INTEGER,
    stop_time      TIME,
    duration       TEXT,
    milliseconds   INTEGER,
    PRIMARY KEY (race_id, driver_id, stop)
);

CREATE TABLE IF NOT EXISTS f1.driver_standings (
    driver_standings_id  INTEGER PRIMARY KEY,
    race_id              INTEGER NOT NULL REFERENCES f1.races(race_id),
    driver_id            INTEGER NOT NULL REFERENCES f1.drivers(driver_id),
    points               NUMERIC(8,1),
    position             INTEGER,
    position_text        TEXT,
    wins                 INTEGER
);

CREATE TABLE IF NOT EXISTS f1.constructor_results (
    constructor_results_id  INTEGER PRIMARY KEY,
    race_id                 INTEGER NOT NULL REFERENCES f1.races(race_id),
    constructor_id          INTEGER NOT NULL REFERENCES f1.constructors(constructor_id),
    points                  NUMERIC(8,1),
    status                  TEXT
);

CREATE TABLE IF NOT EXISTS f1.constructor_standings (
    constructor_standings_id  INTEGER PRIMARY KEY,
    race_id                   INTEGER NOT NULL REFERENCES f1.races(race_id),
    constructor_id            INTEGER NOT NULL REFERENCES f1.constructors(constructor_id),
    points                    NUMERIC(8,1),
    position                  INTEGER,
    position_text             TEXT,
    wins                      INTEGER
);

CREATE INDEX IF NOT EXISTS idx_races_year ON f1.races (year);
CREATE INDEX IF NOT EXISTS idx_races_circuit ON f1.races (circuit_id);
CREATE INDEX IF NOT EXISTS idx_circuits_country ON f1.circuits (country);
CREATE INDEX IF NOT EXISTS idx_results_race ON f1.results (race_id);
CREATE INDEX IF NOT EXISTS idx_results_driver ON f1.results (driver_id);
CREATE INDEX IF NOT EXISTS idx_qualifying_race ON f1.qualifying (race_id);
CREATE INDEX IF NOT EXISTS idx_sprint_race ON f1.sprint_results (race_id);
CREATE INDEX IF NOT EXISTS idx_standings_race_driver ON f1.driver_standings (race_id, driver_id);
CREATE INDEX IF NOT EXISTS idx_drivers_ref_lower ON f1.drivers (lower(driver_ref));
CREATE INDEX IF NOT EXISTS idx_drivers_surname_trgm ON f1.drivers USING gin (surname gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_races_name_trgm ON f1.races USING gin (name gin_trgm_ops);

-- ---------- chat: conversation memory (session_id is a client string, not always UUID) ----------
CREATE TABLE IF NOT EXISTS chat.sessions (
    session_id     TEXT PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat.turns (
    turn_id        BIGSERIAL PRIMARY KEY,
    session_id     TEXT NOT NULL REFERENCES chat.sessions(session_id) ON DELETE CASCADE,
    turn_index     INTEGER NOT NULL,
    payload        JSONB NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_id, turn_index)
);

CREATE INDEX IF NOT EXISTS idx_turns_session_recent ON chat.turns (session_id, turn_index DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active ON chat.sessions (last_active_at);

-- ---------- rag: regulation / historical docs (vectors optional; see schema_pgvector.sql) ----------
CREATE TABLE IF NOT EXISTS rag.index_runs (
    index_run_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category        TEXT NOT NULL,
    embedding_model TEXT NOT NULL DEFAULT 'BAAI/bge-base-en-v1.5',
    source_note     TEXT,
    built_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_active       BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS rag.regulation_articles (
    article_pk       BIGSERIAL PRIMARY KEY,
    index_run_id     UUID NOT NULL REFERENCES rag.index_runs(index_run_id) ON DELETE CASCADE,
    category         TEXT NOT NULL,
    article_id       TEXT NOT NULL,
    title            TEXT,
    body             TEXT NOT NULL,
    page             INTEGER,
    source_path      TEXT NOT NULL,
    regulation_year  SMALLINT,
    section          TEXT,
    subsection_ids   TEXT[] DEFAULT '{}',
    UNIQUE (index_run_id, category, article_id, source_path)
);

CREATE INDEX IF NOT EXISTS idx_reg_articles_lookup
    ON rag.regulation_articles (category, regulation_year, article_id);

CREATE TABLE IF NOT EXISTS rag.regulation_chunks (
    chunk_id         BIGSERIAL PRIMARY KEY,
    index_run_id     UUID NOT NULL REFERENCES rag.index_runs(index_run_id) ON DELETE CASCADE,
    article_pk       BIGINT REFERENCES rag.regulation_articles(article_pk) ON DELETE SET NULL,
    category         TEXT NOT NULL,
    chunk_index      INTEGER NOT NULL,
    content          TEXT NOT NULL,
    metadata         JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS rag.historical_documents (
    doc_id           BIGSERIAL PRIMARY KEY,
    index_run_id     UUID NOT NULL REFERENCES rag.index_runs(index_run_id) ON DELETE CASCADE,
    race_id          INTEGER REFERENCES f1.races(race_id),
    year             SMALLINT,
    title            TEXT,
    content          TEXT NOT NULL,
    metadata         JSONB NOT NULL DEFAULT '{}'
);

-- ---------- app: operational snapshots ----------
CREATE TABLE IF NOT EXISTS app.driver_number_snapshots (
    snapshot_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    season         SMALLINT NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    payload        JSONB NOT NULL,
    is_current     BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS app.fx_rates (
    base_currency  CHAR(3) NOT NULL DEFAULT 'USD',
    as_of_date     DATE NOT NULL,
    rates          JSONB NOT NULL,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (base_currency, as_of_date)
);

CREATE TABLE IF NOT EXISTS app.venue_map (
    map_id       BIGSERIAL PRIMARY KEY,
    phrase       TEXT NOT NULL,
    year_from    SMALLINT,
    year_to      SMALLINT,
    country      TEXT,
    location     TEXT,
    race_id      INTEGER REFERENCES f1.races(race_id),
    notes        TEXT
);
