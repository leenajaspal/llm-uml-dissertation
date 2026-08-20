"""Security primitives: password hashing and bearer-token handling.

Passwords are hashed with PBKDF2-HMAC-SHA256 (standard library only, so no
extra dependency) using a per-user random salt and a high iteration count.
Verification is constant-time.

Access tokens are signed JWTs (HS256). The algorithm is pinned on decode to
avoid algorithm-confusion attacks, and every token carries an expiry.
"""
import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from config import JWT_ALGORITHM, SECRET_KEY, TOKEN_TTL_SECONDS
from errors import AuthError

_PBKDF2_ITERATIONS = 200_000
_SALT_BYTES = 16


def hash_password(password: str) -> str:
    """Return an encoded PBKDF2 hash: ``pbkdf2_sha256$iters$salt$hash``."""
    salt = os.urandom(_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return "pbkdf2_sha256${}${}${}".format(
        _PBKDF2_ITERATIONS,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of a password against an encoded hash."""
    try:
        algo, iters_s, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iters_s)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(derived, expected)
    except Exception:
        return False


def create_access_token(user_id: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=TOKEN_TTL_SECONDS)).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> int:
    """Return the user id encoded in a valid token, else raise AuthError."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except Exception:
        raise AuthError("Invalid or expired token")


# A fixed hash used to keep login timing roughly constant whether or not the
# email exists, reducing user-enumeration signal.
DUMMY_PASSWORD_HASH = hash_password("timing-equalisation-placeholder")
