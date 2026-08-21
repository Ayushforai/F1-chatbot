# F1 Chatbot

A hybrid Formula 1 assistant that routes questions to the right data source: live telemetry (OpenF1), structured historical CSV lookups, or RAG over FIA regulation PDFs and historical race documents.

## Features

### Routing & clarification
- **Intent routing** — classifies queries into sporting, technical, financial, operational, quantitative, historical, or ambiguous
- **Ambiguous query guard** — vague questions get a capabilities menu instead of a wrong guess
- **Year clarification** — race, lap, and driver-team lookups ask for a season before defaulting to 2026
- **Venue clarification** — multi-GP countries (e.g. Italy, USA) prompt for the specific circuit (Monza vs Imola, Austin vs Miami vs Las Vegas)
- **Driver clarification** — lap and telemetry queries require a named driver; no silent default to Hamilton

### Live & quantitative data
- **OpenF1 integration** — fastest lap, specific-lap lookups, and live telemetry when a session is actually live
- **Lap time formatting** — API responses use F1-style `M:SS.mmm` display
- **Lap-time deltas** — compare two drivers on the same lap from historical `lap_times.csv` (e.g. Bottas vs Stroll, lap 32, Azerbaijan 2017)

### Historical data (CSV + RAG)
- **Full race classifications** — pre-2026 result queries use CSV directly: every finisher, DNFs, and fastest laps (not just the top 10)
- **Driver-team lookups** — career questions like “Which team did Hamilton drive for in 2012?” resolve from `results.csv` (supports surname or full name, e.g. “Lance Stroll”)
- **Historical RAG** — FAISS search over processed race documents for broader historical questions
- **Venue-aware CSV matching** — country/circuit synonyms map correctly to the right Grand Prix

### Regulations
- **Regulation RAG** — FAISS vector search over FIA regulation PDFs (sporting, technical, financial, operational)
- **Regulation year default** — yearless regulation queries default to the current season, with an option to ask about another year

### Conversation & display
- **Conversation memory** — last 5 turns stored with answers; follow-ups like “Who finished second?” or “and in 2023?” reuse prior context
- **Fresh re-fetch** — when memory is insufficient or the user asks to verify, the bot re-queries CSV, API, or RAG
- **Currency display** — financial amounts shown in USD, INR, and GBP (penalties: USD + INR only), using live rates from the Frankfurter API with cached fallback

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
```

## Usage

```bash
source botenv/bin/activate
python app.py
```

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
utils/
  router.py             # Intent classification + parameter extraction
  f1_api.py             # OpenF1 API client + lap time formatting
  historical_db.py      # CSV lookups: race results, driver teams, lap deltas
  venues.py             # Circuit/country resolution + multi-GP clarification
  currency.py           # Live FX rates + multi-currency display
  embeddings.py         # HuggingFace embeddings (HF_TOKEN)
  vector_store.py       # FAISS search wrapper
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
