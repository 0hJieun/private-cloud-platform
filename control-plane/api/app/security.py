"""로그인 비밀번호 해시와 SSH 공개키 지문 처리."""

from __future__ import annotations

import base64
import hashlib

from pwdlib import PasswordHash


password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_password: str) -> bool:
    return password_hash.verify(password, encoded_password)


def ssh_fingerprint(public_key: str) -> str:
    """OpenSSH의 SHA256 지문 형식으로 공개키를 식별한다."""

    parts = public_key.strip().split()
    if len(parts) < 2 or not parts[0].startswith("ssh-"):
        raise ValueError("OpenSSH 공개키 형식이 아닙니다.")
    try:
        key_bytes = base64.b64decode(parts[1], validate=True)
    except ValueError as error:
        raise ValueError("공개키 base64 값이 올바르지 않습니다.") from error
    digest = base64.b64encode(hashlib.sha256(key_bytes).digest()).decode().rstrip("=")
    return f"SHA256:{digest}"
