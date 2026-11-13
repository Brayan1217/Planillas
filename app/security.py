"""Firma de mensajes (HMAC-SHA256) con proteccion anti-replay entre la plataforma y la CSS."""
from __future__ import annotations

import hashlib
import hmac
import time

MAX_SKEW_SEGUNDOS = 300


def firmar(secreto: str, timestamp: str, cuerpo: bytes) -> str:
    msg = timestamp.encode() + b"." + cuerpo
    return hmac.new(secreto.encode(), msg, hashlib.sha256).hexdigest()


def verificar(secreto: str, timestamp: str, cuerpo: bytes, firma: str) -> bool:
    try:
        if abs(time.time() - float(timestamp)) > MAX_SKEW_SEGUNDOS:
            return False
    except ValueError:
        return False
    return hmac.compare_digest(firmar(secreto, timestamp, cuerpo), firma or "")


def enmascarar_cedula(c: str) -> str:
    return c[:2] + "***" + c[-2:] if len(c) > 5 else "***"
