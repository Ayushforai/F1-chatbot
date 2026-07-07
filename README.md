# F1 Chatbot

A hybrid Formula 1 assistant that routes questions to the right data source: live telemetry (OpenF1), historical race results (RAG over Kaggle CSVs), or FIA regulation documents (RAG over PDFs).

## Features

- **Intent routing** — classifies queries into sporting, technical, financial, operational, quantitative, or historical
- **Live telemetry** — OpenF1 API for real-time car data and lap times
- **Historical RAG** — driver teams, race results, gaps, and championship standings from 1950–2020 CSV data via FAISS
- **Regulation RAG** — FAISS vector search over FIA 2026 regulation PDFs
- **Conversation memory** — follow-up questions inherit context from prior turns

## Requirements

- Python 3.11+
- [Ollama](https://ollama.com/) with `qwen2.5:7b-instruct-q8_0` pulled locally

## Setup

```bash
python3 -m venv botenv
source botenv/bin/activate
pip install -r requirements.txt

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
- `What is the cost cap for 2026?` → financial regulations (RAG)
- `What was Lewis Hamilton's fastest lap in Monaco 2024?` → OpenF1 API
- `Which team did Lewis drive for in the 2008 British GP?` → historical RAG
- `Who finished second?` → follow-up using conversation memory

## Project Structure

```
app.py                  # Main chat loop
pdf_processor.py         # Builds FAISS indexes from FIA PDFs
historical_processor.py  # Builds FAISS index from historical CSVs
setup_historical_data.py # Downloads Kaggle historical dataset
utils/
  router.py             # Intent classification + parameter extraction
  f1_api.py             # OpenF1 API client
  historical_db.py      # Historical CSV helpers (optional structured lookup)
data/
  *.pdf                 # FIA 2026 regulation documents
  historical_csvs/      # Race results, drivers, constructors, etc.
vector_store/           # Generated FAISS indexes (gitignored)
```

## Data Notes

- **FIA PDFs**: 2026 regulation sections are included in `data/`
- **Historical CSVs**: Included from the [Kaggle F1 dataset](https://www.kaggle.com/datasets/rohanrao/formula-1-world-championship-1950-2020)
- **Archive PDFs**: Older regulation PDFs in `data/archive/` are gitignored due to size; add them locally if needed
