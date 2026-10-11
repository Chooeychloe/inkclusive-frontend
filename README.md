# Inkclusive API server

This FastAPI service processes writing requests and stores the gender-fair term rules used by Inkclusive. The web client lives in [`../inkclusive-frontend/`](../inkclusive-frontend/README.md).

## What it does

- `POST /grammar` - returns a LanguageTool revision and correction details.
- `POST /gfl` - applies gender-fair language rules and preferred pronouns, then increments the request counter.
- `/terms` - reads, creates, updates, and deletes replacement rules stored in `gendered_terms.csv`.
- `/count` - reads or updates the counter stored in `count.csv`.

`main.py` defines the HTTP endpoints and a simple per-client rate limiter. `main_gfl.py` contains the text processing rules and uses spaCy's `en_core_web_sm` model. `csvCrud.py` reads and writes the term CSV; `schemas.py` defines request bodies; `count.py` manages the counter file.

## Local setup

Use Python 3.10 or newer and Java 17 or newer for the local LanguageTool server (see the [`language_tool_python` requirements](https://pypi.org/project/language_tool_python/)), then install the dependencies and spaCy model:

```sh
python -m venv .venv
# macOS/Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_sm
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at `http://localhost:8000`; FastAPI's interactive documentation is at `/docs`.

## Docker

From this directory:

```sh
docker compose up --build
```

The Compose setup maps host port 8000 to port 80 in the container.

## Important deployment note

The `/terms` create, update, and delete endpoints currently have no authentication. The frontend's admin password check does not protect these backend routes. Add server-side authorization and restrict network access before making the API available to untrusted users. CORS settings are not an authorization mechanism.

The term and count CSV files are the current storage layer. Back them up if their contents need to survive container replacement; the Compose bind mount keeps the backend directory available to the container.
