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
- [x] **I02** (High) — Default **year = 2026** for quantitative queries — `app.py`, `utils/router.py` — Yearless queries hit a season that often has no OpenF1 race data yet. Extractor + fallback both default to 2026.
- [x] **I03** (High) — “Live telemetry” is **not live** — hardcoded Silverstone 2024 session — `utils/f1_api.py` `get_driver_telemetry` — Looks like live car data but is an archive snapshot (`sessions?location=Silverstone&year=2024`, fallback `9565`).
- [x] **I04** (Medium) — Historical RAG only indexes **top 10 finishers** per race — `historical_processor.py` — P11+, many DNFs, midfield often wrong/empty.
- [x] **I05** (Medium) — Historical docs are **race-level only** — weak for driver-career / team questions — `historical_processor.py` — e.g. “Which team did X drive for in 2012?”
- [x] **I06** (Medium) — Conversation memory stores **query + category only**, not the answer — `app.py` — Follow-ups like “Who finished second?” lose prior race context.
- [x] **I07** (Medium) — Router misclassification risk → wrong knowledge base — `utils/router.py` — Ambiguous queries; invalid LLM output falls back to `"sporting"`.
- [x] **I08** (Medium) — Country → GP name mismatches in CSV fallback — `utils/historical_db.py` — Mexico/Brazil naming; Miami/Las Vegas → United States can hit the wrong race.
- [x] **I09** (Low) — Fastest-lap / lap packets expose raw seconds, not F1 `M:SS.mmm` — `utils/f1_api.py` — `format_lap_time` exists but isn’t used in return dicts.
- [ ] **I10** (Low) — Extractor failure fallback omits `driver_name` — `utils/router.py`

### Bugs / broken behavior

- [x] **B01** (High) — Missing driver + specific lap still queries **#44** — `app.py` — `d_num = driver or 44`
- [ ] **B02** (Medium) — Historical CSV fallback only runs if vector search **throws**; empty/irrelevant chunks still answer — `app.py` `_historical_context`
- [x] **B03** (Medium) — `get_session_info` takes **first session** of weekend (often FP1), not Race — `utils/f1_api.py`
- [ ] **B04** (Low) — If historical CSVs missing, module prints warning then **NameError** on use — `utils/historical_db.py`
- [ ] **B05** (Low) — Regulation PDF matcher is keyword-on-filename only — `pdf_processor.py` — Section A General never indexed.
- [x] **B06** (Low) — HF Hub unauthenticated warning on startup — `utils/embeddings.py` — Set `HF_TOKEN` in `.env`; dotenv already wired.

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

- [x] **I02** — 2026-08-21 — Race/lap quantitative queries and Grand Prix result queries without a year prompt for the season first; only default to 2026 after the user replies without specifying one. Removed silent fallback to 2024 in CSV lookups.
- [x] **I06** — 2026-08-21 — Conversation memory stores query, category, and assistant answer for the last 5 turns. Follow-ups use memory when sufficient; otherwise re-fetch CSV/RAG/API, including when the user asks to verify or look up.
- [x] **I09** — 2026-08-21 — `get_fastest_lap_of_race` and `get_historical_lap` return `lap_time` formatted via `format_lap_time` (`M:SS.mmm` or `SS.mmm`), keeping raw seconds in `lap_time_seconds`.
- [x] **I04** — 2026-08-21 — Historical race docs and CSV lookups use the full classification, including DNFs and fastest laps. Pre-2026 result queries print CSV classification directly (classified + DNF section) so the LLM cannot drop retirements or swap winners.
- [x] **I03** — 2026-08-16 — Live telemetry uses OpenF1 `session_key=latest` only while a session is live; otherwise a plain “cannot print live F1 data” error. Silverstone 2024 / session 9565 fallback removed.
- [x] **I08** — 2026-08-16 — Country synonyms map to OpenF1 names; multi-GP countries ask which race; CSV keywords follow the resolved venue.
- [x] **B03** — 2026-08-16 — `get_session_info` now resolves the Race session, not FP1.
- [x] **P03** — 2026-08-16 — Future or unpublished sessions return “The session is yet to be conducted.”
- [x] **P04** — 2026-08-16 — Italy and USA no longer pick the first GP; user must name Imola/Monza or Miami/Austin/Las Vegas.
- [x] **B06** — 2026-08-21 — `HF_TOKEN` loaded from `.env` at app startup; passed explicitly to `HuggingFaceEmbeddings`. See `.env.example`.
- [x] **I07** — 2026-08-21 — Ambiguous queries get a specificity prompt or capabilities menu; invalid router output returns `ambiguous` instead of defaulting to sporting.
- [x] **I05** — 2026-08-21 — Driver-team career questions use CSV lookup via `get_driver_teams()` on `results.csv` (e.g. “Which team did Hamilton drive for in 2012?”) instead of RAG alone.

---

## Notes for triage

- Prefer fixing **I01–I03** and **B01** first — they cause the most confident wrong answers.
- When filing a new unwanted output, include the `[Router]` / `[Debug]` lines from the CLI if possible.
