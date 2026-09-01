# F1 Chatbot

A hybrid Formula 1 assistant that routes questions to the right data source: live telemetry (OpenF1), structured historical CSV lookups, or RAG over FIA regulation PDFs and historical race documents.

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

- Python 3.11+
- [Ollama](https://ollama.com/) with `qwen2.5:7b-instruct-q8_0` pulled locally
- Hugging Face read token (for embedding model downloads)

## Setup

```bash
python3 -m venv botenv
source botenv/bin/activate
pip install -r requirements.txt

# Hugging Face token for embeddings (avoids unauthenticated Hub warnings)
cp .env.example .env
# Edit .env and set HF_TOKEN=...

# Pull the local LLM
ollama pull qwen2.5:7b-instruct-q8_0

# Build FAISS indexes from FIA PDFs in data/
python pdf_processor.py

# Download historical CSVs if not already present, then build the FAISS index
python setup_historical_data.py
python historical_processor.py

# Refresh OpenF1 driver name → car number grid (used for live/lap lookups)
python setup_driver_numbers.py
```

## Usage

```bash
source botenv/bin/activate
python app.py
```

Run `python app.py` from an integrated **Terminal** tab (not the Debug Console) so backspace and arrow keys work while typing.

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

## Testing

```bash
source botenv/bin/activate
PYTHONPATH=. python -m unittest discover -s tests -v
```

## Project Structure

```
app.py                  # Main chat loop, clarification flows, memory
pdf_processor.py        # Builds FAISS indexes from FIA PDFs
historical_processor.py # Builds FAISS index from historical CSVs
setup_historical_data.py # Downloads Kaggle historical dataset
setup_driver_numbers.py # Fetches OpenF1 driver grid → data/driver_numbers.json
data/
  driver_numbers.json   # Name / acronym / #NN → car number per season (OpenF1)
  historical_csvs/
    F1DriversDataset.csv # Canonical driver names for text matching (no car numbers)
utils/
  router.py             # Intent classification + parameter extraction
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

When you run `app.py`, the bot keeps two things in memory for the **entire session** (until you type `exit` or kill the process):

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
| **Long-running CLI / API server** | Keep one process alive. Weights load once at boot and serve all RAG queries until shutdown. |
| **Docker** | Bake `vector_store/` and the Hugging Face model cache into the image, or mount `~/.cache/huggingface`. Set `HF_HOME` so weights persist across container restarts. |
| **Serverless / scale-to-zero** | Every cold start reloads the model unless you use provisioned concurrency, an always-on sidecar, or a managed embedding API. Consider a smaller model or ONNX if latency matters. |
| **Multiple workers** | Each worker holds its own copy of the model (~400MB). Prefer 1–2 workers with async, or a shared external embedding service. |

Do **not** spawn a fresh Python process per query in production — that would reload weights every time regardless of in-process caching.
