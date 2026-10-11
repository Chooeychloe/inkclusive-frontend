import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import tempfile
import time
from pathlib import Path

TOKEN_LIFETIME_SECONDS = 8 * 60 * 60


def _credentials_path() -> Path:
	return Path(os.getenv("ADMIN_CREDENTIALS_FILE", "admin_credentials.json"))


def _read_credentials() -> dict:
	try:
		data = json.loads(_credentials_path().read_text(encoding="utf-8"))
		return data if isinstance(data, dict) else {}
	except (OSError, json.JSONDecodeError):
		return {}


def _write_credentials(data: dict) -> None:
	path = _credentials_path()
	path.parent.mkdir(parents=True, exist_ok=True)
	fd, temporary_path = tempfile.mkstemp(prefix=f"{path.name}.", dir=str(path.parent))
	try:
		with os.fdopen(fd, "w", encoding="utf-8") as file:
			json.dump(data, file)
			file.flush()
			os.fsync(file.fileno())
		os.replace(temporary_path, path)
		try:
			os.chmod(path, 0o600)
		except OSError:
			pass
	finally:
		if os.path.exists(temporary_path):
			os.unlink(temporary_path)


def _password_hash(password: str, salt: bytes | None = None) -> tuple[str, str]:
	salt = salt or secrets.token_bytes(16)
	digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
	return _encode(salt), _encode(digest)


def verify_admin_password(password: str) -> bool:
	credentials = _read_credentials()
	if credentials.get("password_hash") and credentials.get("salt"):
		try:
			salt = _decode(credentials["salt"])
			expected = _decode(credentials["password_hash"])
			actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
			return hmac.compare_digest(actual, expected)
		except (ValueError, TypeError, binascii.Error):
			return False
	configured = os.getenv("ADMIN_PASSWORD", "")
	return bool(configured) and hmac.compare_digest(password.encode("utf-8"), configured.encode("utf-8"))


def has_admin_password() -> bool:
	credentials = _read_credentials()
	return bool(os.getenv("ADMIN_PASSWORD", "") or credentials.get("password_hash"))


def change_admin_password(current_password: str, new_password: str) -> None:
	if not verify_admin_password(current_password):
		raise ValueError("The current password is incorrect.")
	salt, digest = _password_hash(new_password)
	credentials = _read_credentials()
	_write_credentials({"salt": salt, "password_hash": digest, "version": _credential_version() + 1})


def _credential_version() -> int:
	try:
		return int(_read_credentials().get("version", 0))
	except (ValueError, TypeError):
		return 0


def _encode(value: bytes) -> str:
	return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value: str) -> bytes:
	return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def create_admin_token() -> str:
	secret = os.getenv("ADMIN_TOKEN_SECRET", "")
	if len(secret.encode("utf-8")) < 32:
		raise RuntimeError("ADMIN_TOKEN_SECRET must contain at least 32 bytes.")
	payload = _encode(json.dumps({"sub": "admin", "exp": int(time.time()) + TOKEN_LIFETIME_SECONDS, "ver": _credential_version()}, separators=(",", ":")).encode("utf-8"))
	signature = _encode(hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())
	return f"{payload}.{signature}"


def verify_admin_token(token: str) -> bool:
	secret = os.getenv("ADMIN_TOKEN_SECRET", "")
	if len(secret.encode("utf-8")) < 32:
		return False
	try:
		payload, supplied_signature = token.split(".", 1)
		expected_signature = _encode(hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest())
		if not hmac.compare_digest(supplied_signature, expected_signature):
			return False
		claims = json.loads(_decode(payload))
		return claims.get("sub") == "admin" and int(claims.get("exp", 0)) > int(time.time()) and int(claims.get("ver", 0)) == _credential_version()
	except (ValueError, TypeError, AttributeError, UnicodeDecodeError, json.JSONDecodeError, binascii.Error):
		return False
