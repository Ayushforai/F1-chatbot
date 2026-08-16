# F1 Chatbot — Bugs, Incorrect Outputs & Issues

Living backlog. Add new items as we spot them during testing. Check them off as we fix them.

**Continue in a new chat:** open or `@` this file and say e.g. `fix I01 and B01` or `check off I09`. The IDs below are the durable references across sessions.

**How we update this file when something is fixed:**
1. Mark the item `[x]`
2. Move a one-line summary into **Fixed** with the date
3. Leave the ID stable (don’t renumber)

**How to add a new issue:** append under the right section with the next free ID (`I11`, `B07`, `P05`, `U01`, …) plus date + example query/output if available.

---

## Open

### Incorrect / misleading answers

- [x] **I01** (High) — Silent default to **driver #44 (Hamilton)** when no driver is extracted — `app.py` — Any lap/live query without a clear driver returns Hamilton’s data as if requested.
- [ ] **I02** (High) — Default **year = 2026** for quantitative queries — `app.py`, `utils/router.py` — Yearless queries hit a season that often has no OpenF1 race data yet. Extractor + fallback both default to 2026.
- [x] **I03** (High) — “Live telemetry” is **not live** — hardcoded Silverstone 2024 session — `utils/f1_api.py` `get_driver_telemetry` — Looks like live car data but is an archive snapshot (`sessions?location=Silverstone&year=2024`, fallback `9565`).
- [ ] **I04** (Medium) — Historical RAG only indexes **top 10 finishers** per race — `historical_processor.py` — P11+, many DNFs, midfield often wrong/empty.
- [ ] **I05** (Medium) — Historical docs are **race-level only** — weak for driver-career / team questions — `historical_processor.py` — e.g. “Which team did X drive for in 2012?”
- [ ] **I06** (Medium) — Conversation memory stores **query + category only**, not the answer — `app.py` — Follow-ups like “Who finished second?” lose prior race context.
- [ ] **I07** (Medium) — Router misclassification risk → wrong knowledge base — `utils/router.py` — Ambiguous queries; invalid LLM output falls back to `"sporting"`.
- [x] **I08** (Medium) — Country → GP name mismatches in CSV fallback — `utils/historical_db.py` — Mexico/Brazil naming; Miami/Las Vegas → United States can hit the wrong race.
- [ ] **I09** (Low) — Fastest-lap / lap packets expose raw seconds, not F1 `M:SS.mmm` — `utils/f1_api.py` — `format_lap_time` exists but isn’t used in return dicts.
- [ ] **I10** (Low) — Extractor failure fallback omits `driver_name` and forces live Hamilton 2026 — `utils/router.py`

### Bugs / broken behavior

- [x] **B01** (High) — Missing driver + specific lap still queries **#44** — `app.py` — `d_num = driver or 44`
- [ ] **B02** (Medium) — Historical CSV fallback only runs if vector search **throws**; empty/irrelevant chunks still answer — `app.py` `_historical_context`
- [x] **B03** (Medium) — `get_session_info` takes **first session** of weekend (often FP1), not Race — `utils/f1_api.py`
- [ ] **B04** (Low) — If historical CSVs missing, module prints warning then **NameError** on use — `utils/historical_db.py`
- [ ] **B05** (Low) — Regulation PDF matcher is keyword-on-filename only — `pdf_processor.py` — Section A General never indexed.
- [ ] **B06** (Low) — HF Hub unauthenticated warning on startup — `utils/embeddings.py` — Set `HF_TOKEN` in `.env`; dotenv already wired.

### Product / pipeline gaps

- [ ] **P01** (Medium) — `streamlit` in `requirements.txt` but app is CLI-only (`app.py`)
- [ ] **P02** (Medium) — No source citation in answers (race doc / PDF chunk / API field)
- [x] **P03** (Low) — No guard when OpenF1 returns empty for future year / wrong country
- [x] **P04** (Low) — Emilia Romagna / sprint weekends / multi-race countries poorly mapped

---

## Observed unwanted outputs (user-reported)

> Paste examples here as you find them. Template:

```
### UXX — YYYY-MM-DD
- Query: ...
- Router category: ...
- Debug params / context (if shown): ...
- Unwanted output: ...
- Expected: ...
- Status: open | fixed
```

*(none yet)*

---

## Fixed

- [x] **I01** — 2026-08-16 — Missing driver no longer defaults to #44; the bot asks which driver they mean.
- [x] **I03** — 2026-08-16 — Live telemetry uses OpenF1 `session_key=latest` only while a session is live; otherwise a plain “cannot print live F1 data” error. Silverstone 2024 / session 9565 fallback removed.
- [x] **I08** — 2026-08-16 — Country synonyms map to OpenF1 names; multi-GP countries ask which race; CSV keywords follow the resolved venue.
- [x] **B03** — 2026-08-16 — `get_session_info` now resolves the Race session, not FP1.
- [x] **P03** — 2026-08-16 — Future or unpublished sessions return “The session is yet to be conducted.”
- [x] **P04** — 2026-08-16 — Italy and USA no longer pick the first GP; user must name Imola/Monza or Miami/Austin/Las Vegas.

<!-- Example:
- [x] **I09** — 2026-08-16 — Used `format_lap_time` in fastest/specific lap responses.
-->

---

## Notes for triage

- Prefer fixing **I01–I03** and **B01** first — they cause the most confident wrong answers.
- When filing a new unwanted output, include the `[Router]` / `[Debug]` lines from the CLI if possible.
