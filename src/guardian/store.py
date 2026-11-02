"""Persistencia en DynamoDB: deduplicación de entregas e historial de revisiones."""
from __future__ import annotations

import time

TTL_DELIVERY = 7 * 24 * 3600
TTL_REVIEW = 90 * 24 * 3600


class Store:
    def __init__(self, table_name: str):
        import boto3
        self._t = boto3.resource("dynamodb").Table(table_name)
        self._cond_error = self._t.meta.client.exceptions.ConditionalCheckFailedException

    def claim_delivery(self, delivery_id: str) -> bool:
        """True si es la primera vez que vemos esta entrega (GitHub reintenta webhooks)."""
        try:
            self._t.put_item(
                Item={"pk": f"delivery#{delivery_id}", "expires_at": int(time.time()) + TTL_DELIVERY},
                ConditionExpression="attribute_not_exists(pk)")
            return True
        except self._cond_error:
            return False

    def release_delivery(self, delivery_id: str) -> None:
        self._t.delete_item(Key={"pk": f"delivery#{delivery_id}"})

    def save_review(self, repo: str, sha: str, verdict: str, counts: dict) -> None:
        self._t.put_item(Item={"pk": f"review#{repo}#{sha}", "verdict": verdict, **counts,
                               "created_at": int(time.time()),
                               "expires_at": int(time.time()) + TTL_REVIEW})
