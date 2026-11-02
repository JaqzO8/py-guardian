"""Lambda 1: recibe el webhook, valida la firma, deduplica y encola. Responde en ms."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os

log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

ZERO_SHA = "0" * 40


def _resp(status: int, msg: str) -> dict:
    return {"statusCode": status, "headers": {"content-type": "application/json"},
            "body": json.dumps({"message": msg})}


def verify_signature(secret: str, body: bytes, header: str | None) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def handle(event: dict, *, secret: str, claim, release, enqueue) -> dict:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    raw = event.get("body") or ""
    body = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode()

    if not verify_signature(secret, body, headers.get("x-hub-signature-256")):
        return _resp(401, "firma inválida")

    kind = headers.get("x-github-event")
    if kind == "ping":
        return _resp(200, "pong")
    if kind != "push":
        return _resp(200, f"evento «{kind}» ignorado")

    p = json.loads(body)
    ref, after = p.get("ref", ""), p.get("after", "")
    if p.get("deleted") or after == ZERO_SHA or not ref.startswith("refs/heads/"):
        return _resp(200, "push sin código que revisar")

    delivery = headers.get("x-github-delivery", "")
    if not delivery:
        return _resp(400, "falta X-GitHub-Delivery")
    if not claim(delivery):
        return _resp(200, "entrega duplicada")

    job = {"delivery": delivery, "repo": p["repository"]["full_name"],
           "before": p.get("before", ZERO_SHA), "after": after,
           "branch": ref.removeprefix("refs/heads/"),
           "pusher": (p.get("pusher") or {}).get("name", "")}
    try:
        enqueue(job)
    except Exception:
        release(delivery)          # que el reintento de GitHub pueda volver a entrar
        log.exception("no se pudo encolar")
        return _resp(500, "error al encolar")
    return _resp(202, "encolado")


def handler(event, context):
    import boto3

    from .secrets import get_secret
    from .store import Store

    store = Store(os.environ["TABLE_NAME"])
    sqs, url = boto3.client("sqs"), os.environ["QUEUE_URL"]
    return handle(
        event, secret=get_secret(os.environ["WEBHOOK_SECRET_ARN"]),
        claim=store.claim_delivery, release=store.release_delivery,
        enqueue=lambda job: sqs.send_message(QueueUrl=url, MessageBody=json.dumps(job)))
