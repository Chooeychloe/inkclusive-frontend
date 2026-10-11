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
| `POST` | `/api/v1/admin/login` | Verify the admin password and issue an expiring bearer token. |
| `POST` | `/api/v1/admin/change-password` | Change the password for the authenticated admin. |
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

Use Python 3.10 or newer and Java 17 or newer for the local LanguageTool server (see the [`language_tool_python` requirements](https://pypi.org/project/language_tool_python/)). From the project root, open PowerShell and run these commands the first time you set up the backend:

```powershell
cd inkclusive-backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Create a private `.env` file in `inkclusive-backend` with these values. The backend loads this file when it starts, and `.env` is excluded from Git:

```text
ADMIN_PASSWORD=choose-a-long-unique-password
ADMIN_TOKEN_SECRET=paste-a-generated-secret-here
# Optional: store password changes in persistent storage (defaults to ./admin_credentials.json)
ADMIN_CREDENTIALS_FILE=./admin_credentials.json
```

Generate a secret once with `python -c "import secrets; print(secrets.token_urlsafe(48))"` and paste the output as `ADMIN_TOKEN_SECRET`. Keep reusing the same secret across restarts; changing it immediately expires existing admin sessions.

`ADMIN_PASSWORD` is the initial admin password. After signing in, use **Change password** in the admin header to save a new password as a salted PBKDF2 hash in `ADMIN_CREDENTIALS_FILE`. The file takes precedence over `ADMIN_PASSWORD` for later sign-ins, and changing the password expires existing admin sessions. The default file is in the backend working directory; configure this path to a persistent volume when deploying to a host with temporary container storage, or the changed password will be lost when that storage is replaced. Keep the credentials file private and back it up securely.

You only need to create the virtual environment, install dependencies, and download the spaCy model once per environment. To run the backend on later occasions, open PowerShell in the `inkclusive-backend` folder and run:

```powershell
.venv\Scripts\Activate.ps1
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Keep that terminal open while using the app. Activate the environment again in each new terminal. Repeat the setup commands only if you delete or recreate `.venv`, or when project dependencies change.

On macOS or Linux, activate the environment with `source .venv/bin/activate` instead.

The API is available at `http://localhost:8000`; FastAPI's interactive documentation is at `/docs`.

## Docker

From this directory, create the `.env` file described above, then run:

```sh
docker compose up --build
```

Compose passes these values to the container and maps host port 8000 to port 80. Keep the `.env` file private and out of version control.

## Important deployment note

All term-library endpoints, including legacy aliases, require a valid admin bearer token. The admin login is rate-limited to five failed attempts per client IP every 15 minutes. Tokens expire after eight hours. The frontend keeps the token in an HttpOnly, same-site cookie and proxies admin requests to the backend, so browser scripts cannot read the token.

Configure these backend environment variables before enabling admin management:

```text
ADMIN_PASSWORD=<a long, unique admin password>
ADMIN_TOKEN_SECRET=<a random secret of at least 32 bytes>
```

Generate a token secret locally with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Set the same backend URL in the frontend's `PUBLIC_BACKEND_URL`. In production, serve the frontend and backend over HTTPS and set `CORS_ORIGINS` to trusted frontend origins. CORS is not a replacement for authentication.

Set `CORS_ORIGINS` to a comma-separated list of trusted web origins in production. It defaults to `*` for local development and does not enable credentialed requests. CORS allows the `ngrok-skip-browser-warning` header used by the frontend for tunneled API requests. The in-memory analysis rate limit is per worker process; use a shared rate limiter when deploying multiple workers.

The term CSV, term metadata JSON, and count CSV files are the current storage layer. Back them up together if their contents need to survive container replacement; the Compose bind mount keeps the backend directory available to the container.
