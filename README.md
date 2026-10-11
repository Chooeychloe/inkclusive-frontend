# Inkclusive API server

This FastAPI service processes writing checks and stores the gender-fair term rules used by Inkclusive. The SvelteKit web client lives in [`../inkclusive-frontend/`](../inkclusive-frontend/README.md).

## API v1

New clients should use the versioned `/api/v1` routes. Interactive docs are available at `/docs` and the OpenAPI schema at `/openapi.json`.

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/health` | Basic service health response. |
| `POST` | `/api/v1/grammar` | Grammar suggestions and corrected text. |
| `POST` | `/api/v1/gfl` | Gender-fair suggestions, taking an optional `pronoun_map`. |
| `GET` | `/api/v1/count` | Read the analysis counter. |
| `GET` | `/api/v1/terms` | List full term records. |
| `GET` | `/api/v1/terms/{term}` | Read a term, case-insensitively. |
| `POST` | `/api/v1/terms` | Create a term; returns the created record. |
| `PATCH` | `/api/v1/terms/{term}` | Update the supplied alternatives and/or metadata fields. |
| `DELETE` | `/api/v1/terms/{term}` | Delete one term; returns `204`. |
| `POST` | `/api/v1/terms/bulk` | Create 1–500 terms in one validated operation. |
| `DELETE` | `/api/v1/terms` | Delete a list of terms in one operation. |

Analysis bodies accept up to 20,000 characters. Grammar responses include the original and revised text plus correction offsets, explanatory messages, rule identifiers, and replacements. Offsets refer to the submitted text exactly; leading and trailing whitespace is preserved. Term mutations return validation errors as `422`, duplicate terms as `409`, and missing terms as `404`. Analysis routes return `429` with a `Retry-After` header when the per-process limit of 10 analysis requests per 30 seconds is reached; unavailable analyzers return `503`.

Example request bodies:

```json
{"prompt":"The chairman shared his report."}
```

```json
{"prompt":"The chairman shared his report.","pronoun_map":{"Alex":"gender_fair"}}
```

```json
{"term":"chairman","options":["chairperson","chair"],"category":"Job title","guidance":"Use a role name when gender is not relevant.","examples":["The chair opened the meeting."]}
```

The previous unversioned routes remain as compatibility aliases but are omitted from OpenAPI. The unversioned `GET /terms` keeps its older term-to-options response. The old count mutation route has been removed; the analysis counter is read-only over HTTP.

## Request flow and storage

The web client posts the current document text to `/api/v1/grammar`, reviews those corrections, and then posts it to `/api/v1/gfl` with any name and pronoun preferences. The client uses each correction's character range to apply a chosen replacement to the editor. LanguageTool performs grammar analysis; `main_gfl.py` uses spaCy and the configured term CSV for gender-fair pattern detection.

`main.py` defines the HTTP endpoints and per-client rate limiter. `schemas.py` validates request bodies. `csvCrud.py` reads and writes `gendered_terms.csv`, with one term and its alternatives per row. Additional term category, guidance, and example metadata is stored in `gendered_terms_metadata.json` so the CSV remains readable by the checker. `count.py` manages `count.csv`.

The term CSV and metadata JSON must be backed up together. The frontend's local draft is stored in the user's browser and is not sent to this service unless the user runs a language check.

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

The term create, update, and delete endpoints do not have authentication. The frontend's admin password check does not protect these backend routes. Add server-side authorization and restrict network access before making the API available to untrusted users. CORS settings are not an authorization mechanism.

Set `CORS_ORIGINS` to a comma-separated list of trusted web origins in production. It defaults to `*` for local development and does not enable credentialed requests. CORS allows the `ngrok-skip-browser-warning` header used by the frontend for tunneled API requests. The in-memory analysis rate limit is per worker process; use a shared rate limiter when deploying multiple workers.

The term CSV, term metadata JSON, and count CSV files are the current storage layer. Back them up together if their contents need to survive container replacement; the Compose bind mount keeps the backend directory available to the container.
