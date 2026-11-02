import hashlib
import hmac
import json

from guardian.receiver import handle, verify_signature

SECRET = "s3cret"


def event(payload, kind="push", delivery="d-1", secret=SECRET, sig=None):
    body = json.dumps(payload)
    sig = sig or "sha256=" + hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return {"headers": {"X-Hub-Signature-256": sig, "X-GitHub-Event": kind,
                        "X-GitHub-Delivery": delivery}, "body": body}


PUSH = {"ref": "refs/heads/feat/x", "before": "a" * 40, "after": "b" * 40,
        "repository": {"full_name": "org/repo"}, "pusher": {"name": "ana"}}


def run(ev, claimed=True, enqueue_exc=None):
    sent, released = [], []

    def enqueue(job):
        if enqueue_exc:
            raise enqueue_exc
        sent.append(job)

    r = handle(ev, secret=SECRET, claim=lambda d: claimed, release=released.append, enqueue=enqueue)
    return r, sent, released


def test_signature_ok_and_tampered():
    assert verify_signature("k", b"hi", "sha256=" + hmac.new(b"k", b"hi", hashlib.sha256).hexdigest())
    assert not verify_signature("k", b"hi", "sha256=deadbeef")
    assert not verify_signature("k", b"hi", None)


def test_rejects_bad_signature_and_does_not_enqueue():
    r, sent, _ = run(event(PUSH, sig="sha256=bad"))
    assert r["statusCode"] == 401 and not sent


def test_push_is_enqueued():
    r, sent, _ = run(event(PUSH))
    assert r["statusCode"] == 202
    assert sent[0]["repo"] == "org/repo" and sent[0]["branch"] == "feat/x"


def test_ping_and_other_events_ignored():
    assert run(event({}, kind="ping"))[0]["statusCode"] == 200
    r, sent, _ = run(event({}, kind="issues"))
    assert r["statusCode"] == 200 and not sent


def test_branch_deletion_and_tags_ignored():
    assert not run(event({**PUSH, "deleted": True}))[1]
    assert not run(event({**PUSH, "ref": "refs/tags/v1"}))[1]


def test_duplicate_delivery_is_not_enqueued():
    r, sent, _ = run(event(PUSH), claimed=False)
    assert r["statusCode"] == 200 and not sent


def test_enqueue_failure_releases_claim_so_github_retry_works():
    r, _, released = run(event(PUSH), enqueue_exc=RuntimeError("sqs down"))
    assert r["statusCode"] == 500 and released == ["d-1"]
