import os
import threading
from math import ceil
from time import time

import language_tool_python
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from count import increment_counter, read_counter
from admin_auth import TOKEN_LIFETIME_SECONDS, change_admin_password, create_admin_token, has_admin_password, verify_admin_password, verify_admin_token
from csvCrud import GenderTerm, GenderTermManager
from main_gfl import load_gfl
from schemas import (
	CountResponse,
	AdminLoginBody,
	AdminLoginResponse,
	AdminPasswordChange,
	GenderFairResponse,
	GenderTermBulkCreate,
	GenderTermBulkDelete,
	GenderTermBulkDeleteResult,
	GenderTermBulkResult,
	GenderTermCreate,
	GenderTermRecord,
	GenderTermUpdate,
	GrammarBody,
	GFLBody,
	GrammarResponse,
)

load_dotenv()

API_PREFIX = "/api/v1"
COUNTER_FILE = "count.csv"
TERMS_CSV = "gendered_terms.csv"
RATE_LIMIT = 10
TIME_WINDOW = 30

tool = language_tool_python.LanguageTool("en-US")
genderTermManager = GenderTermManager(TERMS_CSV)
gflEngine = load_gfl(TERMS_CSV)
grammar_lock = threading.Lock()
terms_lock = threading.RLock()
rate_limit_store: dict[str, list[float]] = {}
admin_login_attempts: dict[str, list[float]] = {}
admin_login_lock = threading.Lock()
ADMIN_LOGIN_LIMIT = 5
ADMIN_LOGIN_WINDOW = 15 * 60
bearer_scheme = HTTPBearer(auto_error=False)

app = FastAPI(
	title="Inkclusive API",
	description="Grammar and gender-fair language analysis with a managed term library.",
	version="1.0.0",
)

allowed_origins = [
	origin.strip()
	for origin in os.getenv("CORS_ORIGINS", "*").split(",")
	if origin.strip()
]
app.add_middleware(
	CORSMiddleware,
	allow_origins=allowed_origins,
	allow_credentials=False,
	allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
	allow_headers=["Content-Type", "Authorization", "ngrok-skip-browser-warning"],
)


class AnalysisRateLimitMiddleware(BaseHTTPMiddleware):
	async def dispatch(self, request: Request, call_next):
		if request.method == "POST" and request.url.path in {
			f"{API_PREFIX}/grammar", f"{API_PREFIX}/gfl", "/grammar", "/gfl"
		}:
			client_ip = request.client.host if request.client else "unknown"
			current_time = time()
			request_times = [
				stamp for stamp in rate_limit_store.get(client_ip, [])
				if current_time - stamp < TIME_WINDOW
			]
			if len(request_times) >= RATE_LIMIT:
				retry_after = ceil(TIME_WINDOW - (current_time - request_times[0]))
				rate_limit_store[client_ip] = request_times
				return JSONResponse(
					status_code=429,
					content={"detail": "Too many text analysis requests. Try again later.", "retry_after_seconds": retry_after},
					headers={"Retry-After": str(retry_after)},
				)
			request_times.append(current_time)
			rate_limit_store[client_ip] = request_times
		return await call_next(request)


app.add_middleware(AnalysisRateLimitMiddleware)


def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
	if credentials is None or not verify_admin_token(credentials.credentials):
		raise HTTPException(
			status_code=status.HTTP_401_UNAUTHORIZED,
			detail="Admin authentication is required or has expired.",
			headers={"WWW-Authenticate": "Bearer"},
		)


@app.post(f"{API_PREFIX}/admin/login", response_model=AdminLoginResponse, tags=["admin"])
def admin_login(payload: AdminLoginBody, request: Request):
	if not has_admin_password() or not os.getenv("ADMIN_TOKEN_SECRET"):
		raise HTTPException(status_code=503, detail="Admin authentication is not configured on this server.")

	client_ip = request.client.host if request.client else "unknown"
	current_time = time()
	with admin_login_lock:
		attempts = [stamp for stamp in admin_login_attempts.get(client_ip, []) if current_time - stamp < ADMIN_LOGIN_WINDOW]
		if len(attempts) >= ADMIN_LOGIN_LIMIT:
			retry_after = ceil(ADMIN_LOGIN_WINDOW - (current_time - attempts[0]))
			admin_login_attempts[client_ip] = attempts
			raise HTTPException(
				status_code=429,
				detail="Too many admin login attempts. Try again later.",
				headers={"Retry-After": str(retry_after)},
			)
		if not verify_admin_password(payload.password):
			attempts.append(current_time)
			admin_login_attempts[client_ip] = attempts
			raise HTTPException(status_code=401, detail="The admin password is incorrect.")
		admin_login_attempts.pop(client_ip, None)

	try:
		token = create_admin_token()
	except RuntimeError as error:
		raise HTTPException(status_code=503, detail="Admin authentication is not configured correctly.") from error
	return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_LIFETIME_SECONDS}


@app.post(f"{API_PREFIX}/admin/change-password", tags=["admin"])
def admin_change_password(payload: AdminPasswordChange, _admin=Depends(require_admin)):
	try:
		change_admin_password(payload.current_password, payload.new_password)
	except ValueError as error:
		raise HTTPException(status_code=400, detail=str(error)) from error
	except OSError as error:
		raise HTTPException(status_code=503, detail="Could not save the new admin password.") from error
	return {"success": True, "message": "Password changed. Sign in again with the new password."}


@app.get("/", tags=["system"])
@app.get(f"{API_PREFIX}/health", tags=["system"])
def health_check():
	return {"status": "ok", "service": "inkclusive-api", "api_version": "1.0.0"}


def _grammar_revision(body: GrammarBody) -> dict:
	text = body.prompt
	try:
		with grammar_lock:
			matches = tool.check(text)
			revised_text = language_tool_python.utils.correct(text, matches)
	except Exception as error:
		raise HTTPException(status_code=503, detail="The grammar service is temporarily unavailable.") from error

	corrections = []
	for match in matches:
		start = min(len(text), max(0, match.offset))
		end = max(start, min(len(text), start + match.error_length))
		corrections.append({
			"character_offset": start,
			"character_endset": end,
			"original_text": text[start:end],
			"message": match.message,
			"rationale": match.message,
			"category": str(match.category),
			"rule_id": match.rule_id,
			"replacements": match.replacements[:5],
		})
	return {"original_text": text, "revised_text": revised_text, "corrections": corrections}


@app.post("/grammar", include_in_schema=False)
@app.post(f"{API_PREFIX}/grammar", response_model=GrammarResponse, tags=["analysis"])
def grammar_revision(body: GrammarBody):
	return _grammar_revision(body)


@app.post("/gfl", include_in_schema=False)
@app.post(f"{API_PREFIX}/gfl", response_model=GenderFairResponse, tags=["analysis"])
def gender_fair_revision(body: GFLBody):
	pronoun_map = body.pronoun_map
	try:
		with terms_lock:
			gflEngine.refresh_terms_if_changed()
			result = gflEngine.process_text(body.prompt, pronoun_map)
		increment_counter(COUNTER_FILE)
	except ValueError as error:
		raise HTTPException(status_code=422, detail=str(error)) from error
	except Exception as error:
		raise HTTPException(status_code=503, detail="The gender-fair language service is temporarily unavailable.") from error
	return {"count": read_counter(COUNTER_FILE), **result}


@app.get("/terms", include_in_schema=False, dependencies=[Depends(require_admin)])
def list_all_terms_legacy():
	with terms_lock:
		return genderTermManager.get_all_term()


@app.get(f"{API_PREFIX}/terms", response_model=list[GenderTermRecord], tags=["terms"], dependencies=[Depends(require_admin)])
def list_all_terms():
	with terms_lock:
		return genderTermManager.get_all_records()


@app.get("/terms/records", include_in_schema=False, dependencies=[Depends(require_admin)])
def list_term_records_legacy():
	with terms_lock:
		return genderTermManager.get_all_records()


@app.get("/terms/{term}", include_in_schema=False, dependencies=[Depends(require_admin)])
def get_term_legacy(term: str):
	with terms_lock:
		result = genderTermManager.find_term(term)
	if not result:
		raise HTTPException(status_code=404, detail="Term not found")
	return result


@app.get(f"{API_PREFIX}/terms/{{term}}", response_model=GenderTermRecord, tags=["terms"], dependencies=[Depends(require_admin)])
def get_term(term: str):
	with terms_lock:
		result = genderTermManager.find_record(term)
	if not result:
		raise HTTPException(status_code=404, detail="Term not found")
	return result


def _create_term(term_data: GenderTermCreate) -> dict:
	try:
		with terms_lock:
			genderTermManager.create(term_data.term, term_data.options, term_data.category, term_data.guidance, term_data.examples)
			return genderTermManager.find_record(term_data.term) or {}
	except ValueError as error:
		raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/terms", status_code=status.HTTP_201_CREATED, include_in_schema=False, dependencies=[Depends(require_admin)])
def create_term_legacy(term_data: GenderTermCreate):
	_create_term(term_data)
	return {"message": f"Term '{term_data.term}' created"}


@app.post(f"{API_PREFIX}/terms", status_code=status.HTTP_201_CREATED, response_model=GenderTermRecord, tags=["terms"], dependencies=[Depends(require_admin)])
def create_term(term_data: GenderTermCreate):
	return _create_term(term_data)


def _update_term(term: str, update_data: GenderTermUpdate) -> dict:
	try:
		with terms_lock:
			existing = genderTermManager.find_record(term)
			if not existing:
				raise KeyError(term)
			genderTermManager.update(
				term,
				update_data.options if update_data.options is not None else existing["options"],
				update_data.category,
				update_data.guidance,
				update_data.examples,
			)
			return genderTermManager.find_record(term) or {}
	except KeyError as error:
		raise HTTPException(status_code=404, detail="Term not found") from error


@app.put("/terms/{term}", include_in_schema=False, dependencies=[Depends(require_admin)])
def update_term_legacy(term: str, update_data: GenderTermUpdate):
	_update_term(term, update_data)
	return {"message": f"Term '{term}' updated"}


@app.put(f"{API_PREFIX}/terms/{{term}}", response_model=GenderTermRecord, tags=["terms"], include_in_schema=False, dependencies=[Depends(require_admin)])
def update_term(term: str, update_data: GenderTermUpdate):
	return _update_term(term, update_data)


@app.patch(f"{API_PREFIX}/terms/{{term}}", response_model=GenderTermRecord, tags=["terms"], dependencies=[Depends(require_admin)])
def patch_term(term: str, update_data: GenderTermUpdate):
	return _update_term(term, update_data)


def _delete_term(term: str):
	try:
		with terms_lock:
			genderTermManager.delete(term)
	except KeyError as error:
		raise HTTPException(status_code=404, detail="Term not found") from error


@app.delete("/terms/{term}", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False, dependencies=[Depends(require_admin)])
def delete_term_legacy(term: str):
	_delete_term(term)


@app.delete(f"{API_PREFIX}/terms/{{term}}", status_code=status.HTTP_204_NO_CONTENT, tags=["terms"], dependencies=[Depends(require_admin)])
def delete_term(term: str):
	_delete_term(term)


def _create_terms_bulk(payload: GenderTermBulkCreate) -> dict:
	entries = [GenderTerm(item.term, item.options, item.category, item.guidance, item.examples) for item in payload.terms]
	try:
		with terms_lock:
			genderTermManager.create_many(entries)
	except ValueError as error:
		raise HTTPException(status_code=409, detail=str(error)) from error
	return {"created": len(entries)}


@app.post("/terms/bulk", status_code=status.HTTP_201_CREATED, include_in_schema=False, dependencies=[Depends(require_admin)])
def create_terms_bulk_legacy(payload: GenderTermBulkCreate):
	return _create_terms_bulk(payload)


@app.post(f"{API_PREFIX}/terms/bulk", status_code=status.HTTP_201_CREATED, response_model=GenderTermBulkResult, tags=["terms"], dependencies=[Depends(require_admin)])
def create_terms_bulk(payload: GenderTermBulkCreate):
	return _create_terms_bulk(payload)


@app.delete(f"{API_PREFIX}/terms", response_model=GenderTermBulkDeleteResult, tags=["terms"], dependencies=[Depends(require_admin)])
def delete_terms_bulk(payload: GenderTermBulkDelete):
	try:
		with terms_lock:
			deleted = genderTermManager.delete_many(payload.terms)
	except KeyError as error:
		raise HTTPException(status_code=404, detail=str(error)) from error
	return {"deleted": deleted}


@app.get("/count", include_in_schema=False)
@app.get(f"{API_PREFIX}/count", response_model=CountResponse, tags=["system"])
def get_count_request():
	return {"count": read_counter(COUNTER_FILE)}
