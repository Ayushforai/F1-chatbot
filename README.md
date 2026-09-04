# Racecoe

A hybrid Formula 1 assistant (formerly the F1 Pit Wall chatbot) that routes questions to the right data source: live telemetry (OpenF1), structured historical CSV lookups, or RAG over FIA regulation PDFs and historical race documents.

## Models & deployment (local vs production)

Racecoe uses **different LLM setups** for local development and cloud deployment:

| Environment | LLM | Notes |
|-------------|-----|--------|
| **Local development** | [Ollama](https://ollama.com/) with `qwen2.5:7b-instruct-q8_0` | Set `LLM_PROVIDER=ollama` (default). No cloud API key required. |
| **Deployed / production** | **Gemini 3.8 Flash** (`gemini-3.8-flash`) | Set `LLM_PROVIDER=gemini` + `GEMINI_API_KEY`. Free tier is rate-limited (RPM/TPM/RPD). |

One codebase supports both via `utils/llm.py` (`LLM_PROVIDER` + optional `LLM_MODEL`).

### Why Gemini 3.8 Flash?

`gemini-3.8-flash` is the newest Flash workhorse and is available on the Gemini API free tier (rate-limited). Racecoe defaults to it for deploy. Older IDs like `gemini-3.6-flash` still work via `LLM_MODEL`.

**Gemini overload (503):** On the free Flash API, Google may return `503 UNAVAILABLE` with *“This model is currently experiencing high demand”*. That is an **LLM provider** failure — CSV/RAG context can be fine while chat still fails. Racecoe retries with backoff and falls back across models (`gemini-3.6-flash`, then `gemini-2.0-flash`) via `utils/llm.py` / `GEMINI_FALLBACK_MODELS`.

### Google One Plus vs Gemini API

The models you see in the **Gemini app** with Google One Plus are **consumer product names**. Racecoe talks to the **Gemini Developer API**, which uses model IDs like:

| What you see in Gemini app | Typical API model ID |
|----------------------------|----------------------|
| Flash 3.8 / latest Flash | `gemini-3.8-flash` (**Racecoe default**) |
| Flash 3.6 | `gemini-3.6-flash` |
| Flash Lite | `gemini-3.5-flash-lite` (or newer lite ID your project lists) |
| 3.1 Pro | `gemini-3.1-pro-preview` |

Google One subscription does **not** automatically give your Docker app those models. You still need a **`GEMINI_API_KEY`** from [Google AI Studio](https://aistudio.google.com/apikey).

```bash
export LLM_PROVIDER=gemini
export GEMINI_API_KEY=...
export LLM_MODEL=gemini-3.8-flash          # default
export GEMINI_THINKING_LEVEL=LOW           # LOW|MEDIUM|HIGH for 3.8
# export LLM_MODEL=gemini-3.1-pro-preview  # optional heavier model
```

Embeddings stay on **Hugging Face** (`BAAI/bge-base-en-v1.5`) in both environments (set `HF_TOKEN`).

## Features

### Routing & clarification
- **Intent routing** — classifies queries into general, sporting, technical, financial, operational, quantitative, historical, or ambiguous
- **Ambiguous query guard** — vague questions get a capabilities menu instead of a wrong guess
- **Year clarification** — race, lap, and driver-team lookups ask for a season before defaulting to 2026
- **Venue clarification** — multi-GP countries (e.g. Italy, USA) prompt for the specific circuit (Monza vs Imola, Austin vs Miami vs Las Vegas)
- **Driver clarification** — lap and telemetry queries require a named driver; no silent default to Hamilton
- **Driver number lookup** — names, surnames, and `#NN` tokens map to car numbers via `data/driver_numbers.json` (OpenF1 grid). `F1DriversDataset.csv` helps recognize 868 canonical driver names in query text before number lookup.

### Live & quantitative data
- **OpenF1 integration** — fastest lap, specific-lap lookups, and live telemetry when a session is actually live
- **Lap time formatting** — API responses use F1-style `M:SS.mmm` display
- **Top-speed lookup** — highest speed-trap readings via OpenF1 (2021+) and fastest-lap speeds from CSV; handles all-time and GP-specific queries

### Historical data (CSV + RAG)
- **Full race classifications** — pre-2026 result queries use CSV directly: every finisher, DNFs, and fastest laps (not just the top 10)
- **Driver-team lookups** — career questions like “Which team did Hamilton drive for in 2012?” resolve from `results.csv` (supports surname or full name, e.g. “Lance Stroll”)
- **Historical RAG** — FAISS search over processed race documents for broader historical questions
- **Venue-aware CSV matching** — country/circuit synonyms map correctly to the right Grand Prix

### Regulations
- **Regulation RAG** — FAISS vector search over FIA regulation PDFs (general/Section A, sporting, technical, financial, operational)
- **Article-aware indexing** — PDFs split by `ARTICLE` headings with section/article metadata; `articles.json` enables exact Article lookups
- **Hybrid retrieval** — article/section refs hit structured lookup first; broad questions retrieve more chunks
- **Regulation year default** — yearless regulation queries default to the current season, with an option to ask about another year

### Conversation & display
- **Conversation memory** — last 5 turns stored with answers; follow-ups like “Who finished second?” or “and in 2023?” reuse prior context
- **Fresh re-fetch** — when memory is insufficient or the user asks to verify, the bot re-queries CSV, API, or RAG
- **Currency display** — financial amounts shown in USD, INR, and GBP (penalties: USD + INR only), using live rates from the Frankfurter API with cached fallback
- **Source citations** — every answer ends with where the data came from (CSV tables, OpenF1 API, regulation PDF chunk, historical vector doc, or prior turn)
- **In-memory RAG cache** — embedding model weights and FAISS indexes stay loaded for the whole session; only RAG queries use the model, CSV/API queries do not

## Requirements

### Local development
- Python 3.11+
- Node.js 18+ (for the React / Vite frontend)
- [Ollama](https://ollama.com/) with `qwen2.5:7b-instruct-q8_0` pulled locally
- Hugging Face read token (for embedding model downloads)

### Production / deploy
- Docker (recommended) — see `Dockerfile`
- Cloud LLM: **Gemini** (recommended) or **Groq**
- Host secrets: `HF_TOKEN`, `GEMINI_API_KEY` or `GROQ_API_KEY`, optional `CORS_ORIGINS`
- Outbound HTTPS for OpenF1, Hugging Face, currency FX, and the LLM API
- Built FAISS indexes (`vector_store/*/index.faiss`) and historical CSVs (`data/historical_csvs/`) are committed so the Docker image includes them (`data/archive/` is excluded)

### Deploy checklist

1. Create a **Gemini API key** at https://aistudio.google.com/apikey (Google One alone is not enough)  
2. Create an **HF_TOKEN** at https://huggingface.co/settings/tokens  
3. Put both in `.env` (never commit `.env`):
   ```bash
   LLM_PROVIDER=gemini
   LLM_MODEL=gemini-3.8-flash
   GEMINI_API_KEY=...
   HF_TOKEN=...
   ```
4. Build FAISS indexes locally if needed (`pdf_processor.py`, `historical_processor.py`)  
5. Run locally in production shape:
   ```bash
   docker compose up --build
   # open http://127.0.0.1:8000 — check /api/health
   ```
6. Deploy with Docker to **Render** (uses `render.yaml`) or Railway / HF Spaces  
7. Set secret env vars on the host: `GEMINI_API_KEY`, `HF_TOKEN`, optional `CORS_ORIGINS`  
8. Smoke test: `python scripts/smoke_deploy.py --http --base-url https://YOUR-URL`

```bash
# Example without Docker
export LLM_PROVIDER=gemini
export LLM_MODEL=gemini-3.8-flash
export GEMINI_API_KEY=...
export HF_TOKEN=...
export HOST=0.0.0.0
export PORT=8000
uvicorn server:app --host 0.0.0.0 --port 8000
```

## Setup (local)

```bash
python3 -m venv botenv
source botenv/bin/activate
pip install -r requirements.txt

# Hugging Face token for embeddings (avoids unauthenticated Hub warnings)
cp .env.example .env
# Edit .env and set HF_TOKEN=...

# Pull the local LLM (development only)
ollama pull qwen2.5:7b-instruct-q8_0

# Build FAISS indexes from FIA PDFs in data/
python pdf_processor.py

# Download historical CSVs if not already present, then build the FAISS index
python setup_historical_data.py
python historical_processor.py

# Refresh OpenF1 driver name → car number grid (used for live/lap lookups)
python setup_driver_numbers.py

# Frontend (optional for web UI)
cd frontend && npm install && npm run build && cd ..
```

## Usage

### CLI

```bash
source botenv/bin/activate
python app.py
```

Run `python app.py` from an integrated **Terminal** tab (not the Debug Console) so backspace and arrow keys work while typing.

### Web UI (FastAPI + React)

```bash
source botenv/bin/activate
python server.py
# open http://127.0.0.1:5001
```

For frontend hot-reload during UI work:

```bash
cd frontend && npm run dev
# proxies /api to http://127.0.0.1:5001
```

On startup you will see:

```
[RAG] Loading embedding model into memory...
[RAG] Embedding model ready.
```

That is a **one-time load per process** (~5–15s on CPU). The weights then stay in memory until you exit the bot. Switching between regulation categories or historical RAG does not reload them.

Example queries:

| Query | Route |
|---|---|
| `What is the cost cap for 2026?` | Financial regulations (RAG) |
| `What was Verstappen's lap 12 time at Monza 2024?` | OpenF1 lap lookup |
| `Results of Monaco GP 2021` | CSV full classification |
| `Which team did Hamilton drive for in 2012?` | CSV driver-team lookup |
| `Time delta between Bottas and Stroll on lap 32 of Azerbaijan GP 2017?` | CSV lap-time delta |
| `Which GP in Italy?` → `Monza` | Venue clarification, then lookup |
| `Who finished second?` | Follow-up from conversation memory |
| `and in 2023?` (after a driver-team answer) | Follow-up with new season |

## Evaluation

Racecoe is evaluated with an **issue-driven quality backlog**, **automated regression tests**, and **deploy smoke checks** (not a single end-to-end LLM accuracy score). Metrics below reflect what has been tracked since the project started.

### 1. Issue backlog quality (`ISSUES.md`)

Incorrect answers, bugs, and product gaps are tracked with stable IDs and severity.

| Bucket | Tracked | Closed | Still open |
|--------|---------|--------|------------|
| Incorrect / misleading answers (**I01–I10**) | 10 | 10 | 0 |
| Bugs (**B01–B06**) | 6 | 5 | **1** (`B02` — empty RAG chunks can still answer) |
| Product / pipeline gaps (**P01–P04**) | 4 | 4 | 0 |
| **Total** | **20** | **19** | **1** |

**Closure rate:** 19/20 = **95%** of logged correctness/product issues fixed.

Representative regressions that now have dedicated tests (named after issue IDs):

| ID | Failure mode | Evaluation signal |
|----|--------------|-------------------|
| I01 | Silent default to Hamilton (#44) | Driver clarification tests |
| I02 | Silent year=2026 | Year clarification tests |
| I03 | Fake “live” Silverstone 2024 archive | Live-session gate tests |
| I04 | Top-10-only classifications / missing DNFs | Full classification + CSV preference tests |
| I05 | Weak driver–team career answers | CSV `get_driver_teams` tests |
| I06 | Follow-ups lost prior answer | Conversation memory tests |
| I07 | Ambiguous → wrong KB | Ambiguous-query / router tests |
| I09 | Raw lap seconds instead of `M:SS.mmm` | Lap-time format tests |
| B01 | Missing driver still queried #44 | Covered with I01 suite |
| P02 | No source citation | Citation footer tests |

### 2. Automated regression suite

| Suite | Scope | Count (current) | How to run |
|-------|--------|-----------------|------------|
| Python unit tests | Router, CSV/RAG paths, venues, API wrapper, Gemini client, regulations, follow-ups | **226** cases in `tests/` | `PYTHONPATH=. python -m unittest discover -s tests -v` |
| Frontend formatting | Answer markdown / race list rendering | **4** cases | `cd frontend && node --test src/formatAnswer.test.js` |
| In-process deploy smoke | Monaco 2021 → “who was third?” stickiness + `/api/health` | **2** assertions | `PYTHONPATH=. python scripts/smoke_deploy.py` |
| HTTP / production smoke | Same follow-up against a running server | Live gate | `python scripts/smoke_deploy.py --http --base-url URL` |

**Pass criterion for merge/deploy:** unit suite green; smoke asserts Norris stays P3 for Monaco 2021 and does not re-prompt session choice.

### 3. Deploy / public-host metrics

Checked during Docker + Render bring-up:

| Metric | Target / observed |
|--------|-------------------|
| Historical CSVs in image | **15/15** files under `/app/data/historical_csvs` |
| FAISS indexes in image | **5/5** categories (`historical`, `sporting`, `technical`, `financial`, `operational`) |
| `/api/health` | `ready: true`, `provider: gemini`, `model: gemini-3.8-flash`, `has_api_key: yes` |
| Live smoke (Render) | Monaco results + follow-up **passed** on `https://racecoe.onrender.com` |
| Port bind on Render | Must listen on injected `PORT` (observed `10000`) before health checks succeed |

#### Public reliability incidents (and fixes)

These are separate failure modes that both blocked public historical Q&A until fixed:

| Incident | What users saw | Root cause | Fix |
|----------|----------------|------------|-----|
| **Gemini overload** | Chat failed on follow-ups (raw API error / “stream interrupted”) even when race CSV context was present | Gemini API **`503 UNAVAILABLE`** — *“This model is currently experiencing high demand”* on `gemini-3.8-flash` free tier | Retries + exponential backoff; fallback chain `gemini-3.6-flash` → `gemini-2.0-flash`; clearer user-facing overload message |
| **Render free-tier OOM** | Site never became healthy / deploy failed (“no open ports”, then crash) | **512MB RAM** exceeded while eagerly loading CUDA torch + embedding weights before uvicorn bound | CPU-only torch image; lazy import of sentence-transformers; `F1_SKIP_WARMUP=1` so the API becomes ready without preloading embeddings (RAG loads on first use) |

**Takeaway:** overload = temporary **LLM API** unavailability; OOM = **host memory** killing the process. Both are documented in Evaluation because both made public historical Q&A unavailable until mitigated.

### 4. Behavioural correctness checks (non-LLM-score)

These are binary / structural checks used instead of BLEU/RAGAS:

- **No silent defaults** — missing driver/year must clarify (I01/I02).
- **Full grid integrity** — classifications include all finishers + DNFs, not top 10 (I04).
- **Follow-up stickiness** — position questions reuse race context; session-choice offer does not trap the dialog.
- **Live vs archive honesty** — off-weekend telemetry returns unavailable, never a hardcoded 2024 session (I03).
- **Citation present** — answers append a source footer (P02).
- **Multi-GP safety** — Italy/USA/etc. require venue choice before answering.

> Note: Racecoe does **not** yet publish a held-out LLM accuracy % (e.g. RAGAS faithfulness). Quality is measured by the issue closure rate, the 226 automated regressions, and deploy smoke gates above.

## Testing

```bash
source botenv/bin/activate
PYTHONPATH=. python -m unittest discover -s tests -v

# Frontend answer-formatting unit tests
cd frontend && node --test src/formatAnswer.test.js

# Deploy smoke (in-process)
PYTHONPATH=. python scripts/smoke_deploy.py

# Deploy smoke against local Docker or Render
python scripts/smoke_deploy.py --http --base-url http://127.0.0.1:8000
python scripts/smoke_deploy.py --http --base-url https://racecoe.onrender.com
```

## Project Structure

```
app.py                  # Main chat loop, clarification flows, memory
server.py               # FastAPI wrapper + serves frontend/dist
pdf_processor.py        # Builds FAISS indexes from FIA PDFs
historical_processor.py # Builds FAISS index from historical CSVs
setup_historical_data.py # Downloads Kaggle historical dataset
setup_driver_numbers.py # Fetches OpenF1 driver grid → data/driver_numbers.json
frontend/               # Racecoe React (Vite) UI
data/
  driver_numbers.json   # Name / acronym / #NN → car number per season (OpenF1)
  historical_csvs/
    F1DriversDataset.csv # Canonical driver names for text matching (no car numbers)
utils/
  router.py             # Intent classification + parameter extraction
  llm.py                # LLM_PROVIDER abstraction (ollama / gemini / groq / openai / grok)
  driver_names.py       # F1DriversDataset name resolution
  driver_numbers.py     # Driver name → car number resolution
  f1_api.py             # OpenF1 API client + lap time formatting
  historical_db.py      # CSV lookups: race results, driver teams, lap deltas
  venues.py             # Circuit/country resolution + multi-GP clarification
  currency.py           # Live FX rates + multi-currency display
  citations.py          # Source footer formatting for answers
  embeddings.py         # HuggingFace embeddings (singleton cache, HF_TOKEN)
  vector_store.py       # FAISS search wrapper (per-category index cache)
tests/                  # Regression tests for routing, venues, memory, etc.
data/
  *.pdf                 # FIA regulation documents
  historical_csvs/      # Race results, drivers, constructors, lap times, etc.
vector_store/           # Generated FAISS indexes (gitignored)
.env.example            # HF_TOKEN template
ISSUES.md               # Bug backlog and fix history
```

## Data Notes

- **FIA PDFs**: Regulation sections are included in `data/`
- **Historical CSVs**: From the [Kaggle F1 dataset](https://www.kaggle.com/datasets/rohanrao/formula-1-world-championship-1950-2020) (1950–2020)
- **Archive PDFs**: Older regulation PDFs in `data/archive/` are gitignored due to size; add them locally if needed
- **OpenF1**: Used for 2021+ live and lap data; pre-2026 race results and lap deltas come from CSV

## RAG performance & deployment

### What stays loaded

When you run `app.py` or `server.py`, the bot keeps two things in memory for the **entire session** (until you exit or kill the process):

| Cached in memory | Loaded when | Reloaded? |
|------------------|-------------|-----------|
| **Embedding model** (`BAAI/bge-base-en-v1.5`, ~400MB) | Startup (`warmup_rag()`) | No — singleton for the process |
| **FAISS indexes** (per category: `historical`, `sporting`, `financial`, …) | First search in that category | No — cached after first use |

A new terminal run or process restart pays the startup cost again. That is expected.

### Which queries use the embedding model

The weights stay loaded for all query types, but **only RAG paths actually run them** (to embed the user's question for vector search):

| Query type | Uses embeddings? |
|------------|------------------|
| Regulation RAG (general, sporting, technical, financial, operational) | Yes |
| Historical RAG | Yes |
| CSV lookups (race results, driver teams, country GP lists, lap deltas) | No |
| OpenF1 (laps, telemetry, speed trap) | No |
| Conversation-memory follow-ups | No |

So CSV and API answers stay fast even though the model remains resident in memory.

### Optional index preload

By default only the embedding model is warmed at startup. To also load specific FAISS indexes up front, set in `.env`:

```bash
RAG_WARMUP_CATEGORIES=historical,sporting,financial
```

Or export before running:

```bash
export RAG_WARMUP_CATEGORIES=historical,sporting,financial
python app.py
```

### Deployment notes

| Setup | Recommendation |
|-------|----------------|
| **Local LLM** | Use **Ollama** (`LLM_PROVIDER=ollama`, model `qwen2.5:7b-instruct-q8_0`). |
| **Production LLM** | Use **Gemini 3.8 Flash** (`LLM_PROVIDER=gemini`, `LLM_MODEL=gemini-3.8-flash`). Free tier is rate-limited; **503 high-demand** responses are retried and fall back to other Flash models (see Evaluation). |
| **Packaging** | Prefer **Docker** (`Dockerfile`): builds the React app, copies CSVs + `vector_store/`, runs `uvicorn server:app --host 0.0.0.0 --port $PORT`. On Render free (512MB), default `F1_SKIP_WARMUP=1` so boot does not OOM on embeddings. |
| **Long-running API server** | Keep one process alive. With warmup enabled, embedding weights load once at boot; with skip-warmup, they load on first RAG use. |
| **Hugging Face cache** | Mount or bake `~/.cache/huggingface`, or set `HF_HOME`, so embedding weights persist across container restarts. |
| **Serverless / scale-to-zero** | Every cold start reloads the embedding model unless you use provisioned concurrency or a managed embedding API. |
| **Multiple workers** | Each worker holds its own copy of the embedding model (~400MB). Prefer 1–2 workers with async, or a shared external embedding service. |

Do **not** spawn a fresh Python process per query in production — that would reload weights every time regardless of in-process caching.
