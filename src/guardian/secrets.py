from __future__ import annotations

import functools


@functools.lru_cache(maxsize=8)
def get_secret(secret_id: str) -> str:
    import boto3  # incluido en el runtime de Lambda
    return boto3.client("secretsmanager").get_secret_value(SecretId=secret_id)["SecretString"]
