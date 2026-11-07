"""
TOTP (RFC 6238) для двухфакторной аутентификации (лабораторная № 8, шаг 1).

Сервер и приложение-аутентификатор (Google / Microsoft Authenticator, Authy)
делят секрет base32. Каждые 30 секунд обе стороны считают
HMAC-SHA1(secret, unix_time // 30) и берут 6 цифр. Часы синхронизировать не
нужно: сервер принимает код текущего интервала и соседних (valid_window=1,
±30 секунд), а этого хватает на обычный дрейф часов телефона.

Защиты сверх минимального примера из методички:
  • секрет в БД зашифрован (Fernet = AES-128-CBC + HMAC-SHA256): утечка
    дампа БД не даёт сгенерировать коды;
  • код можно использовать один раз: запоминаем номер принятого интервала
    и отклоняем такой же или более старый (перехваченный код не повторить);
  • коды восстановления — одноразовые, в БД лежат только их SHA-256.
"""

import base64
import hashlib
import io
import json
import secrets
import time
from typing import Optional

import pyotp
import qrcode
from cryptography.fernet import Fernet, InvalidToken

from app.config import totp_encryption_key, totp_issuer
from app.db_models.user import User

RECOVERY_CODES_COUNT = 8
TOTP_INTERVAL = 30


def _fernet() -> Fernet:
    # Из произвольной строки-ключа получаем 32 байта для Fernet.
    digest = hashlib.sha256(("totp:" + totp_encryption_key()).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(secret: str) -> str:
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token: str) -> Optional[str]:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def new_secret() -> str:
    return pyotp.random_base32()  # 32 символа base32 = 160 бит


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=account, issuer_name=totp_issuer())


def qr_png_base64(uri: str) -> str:
    img = qrcode.make(uri, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _normalize(code: str) -> str:
    return "".join(ch for ch in (code or "") if not ch.isspace())


def verify_code(user: User, code: str, now: Optional[float] = None) -> bool:
    """
    Проверяет 6-значный код. При успехе запоминает интервал в
    user.totp_last_timestep (вызывающий код должен сделать commit).
    """
    code = _normalize(code)
    if not user.totp_secret or len(code) != 6 or not code.isdigit():
        return False
    secret = decrypt_secret(user.totp_secret)
    if secret is None:
        return False
    totp = pyotp.TOTP(secret)
    now = time.time() if now is None else now
    current = int(now // TOTP_INTERVAL)
    for step in (current - 1, current, current + 1):  # ±30 секунд
        if secrets.compare_digest(totp.at(step * TOTP_INTERVAL), code):
            if user.totp_last_timestep is not None and step <= user.totp_last_timestep:
                return False  # этот (или более ранний) код уже использован
            user.totp_last_timestep = step
            return True
    return False


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.replace("-", "").lower().encode()).hexdigest()


def generate_recovery_codes(user: User) -> list[str]:
    """Новые коды восстановления; в БД сохраняются только хэши."""
    codes = [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}" for _ in range(RECOVERY_CODES_COUNT)]
    user.totp_recovery_codes = json.dumps([_hash_code(c) for c in codes])
    return codes


def recovery_codes_left(user: User) -> int:
    try:
        return len(json.loads(user.totp_recovery_codes or "[]"))
    except ValueError:
        return 0


def use_recovery_code(user: User, code: str) -> bool:
    """Одноразовый код восстановления (если телефон потерян)."""
    code = _normalize(code)
    if len(code) < 8:
        return False
    try:
        hashes = json.loads(user.totp_recovery_codes or "[]")
    except ValueError:
        return False
    h = _hash_code(code)
    for stored in hashes:
        if secrets.compare_digest(stored, h):
            hashes.remove(stored)
            user.totp_recovery_codes = json.dumps(hashes)
            return True
    return False


def verify_code_or_recovery(user: User, code: str) -> bool:
    return verify_code(user, code) or use_recovery_code(user, code)
