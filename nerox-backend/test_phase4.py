"""Phase 4 Quick Validation Test"""
import sys
import urllib.request
import urllib.error
import json
import time
import uuid

import cv2
import numpy as np

# Force UTF-8 to avoid Windows cp1252 encoding errors
sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://localhost:8000"


def make_png(size=128) -> bytes:
    img = np.random.randint(30, 220, (size, size, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()


def req(method, path, data=None, headers=None, binary_body=None, ctype=None):
    url  = BASE + path
    h    = dict(headers or {})
    body = None
    if binary_body is not None:
        body = binary_body
        h["Content-Type"] = ctype or "application/octet-stream"
    elif data is not None:
        body = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def mp(filename, content_type, data):
    b = uuid.uuid4().hex
    body = (
        ("--" + b + "\r\n").encode()
        + ("Content-Disposition: form-data; "
           'name="file"; filename="' + filename + '"\r\n').encode()
        + ("Content-Type: " + content_type + "\r\n\r\n").encode()
        + data
        + ("\r\n--" + b + "--\r\n").encode()
    )
    return body, "multipart/form-data; boundary=" + b


def mpf(**fields):
    b = uuid.uuid4().hex
    body = b""
    for name, value in fields.items():
        body += (
            ("--" + b + "\r\n").encode()
            + ('Content-Disposition: form-data; name="' + name + '"\r\n\r\n').encode()
            + str(value).encode()
            + b"\r\n"
        )
    body += ("--" + b + "--\r\n").encode()
    return body, "multipart/form-data; boundary=" + b


results = []


def chk(name, ok, detail=""):
    results.append((name, ok, detail))
    tag  = "PASS" if ok else "FAIL"
    info = "  | " + detail if detail else ""
    print(f"  [{tag}] {name}{info}")


SEP = "=" * 62

print(SEP)
print("Nerox Phase 4 - Final Validation")
print(SEP)

# ── Health ────────────────────────────────────────────────────────────────────
print("\n[1] Health / version")
s, b = req("GET", "/health")
chk("v4.0.0 running", b.get("version") == "4.0.0", str(b))
chk("faiss_vectors reported", "faiss_vectors" in b)

# ── Login ─────────────────────────────────────────────────────────────────────
print("\n[2] Auth")
s, b = req("POST", "/auth/login", {"email": "testuser@nerox.io", "password": "TestPass1"})
chk("Login 200", s == 200)
TOKEN = b.get("access_token", "")
AUTH  = {"Authorization": "Bearer " + TOKEN}
chk("Token issued", bool(TOKEN))

# ── Upload ───────────────────────────────────────────────────────────────────
print("\n[3] Upload")
png_data = make_png()
body, ctype = mp("test.png", "image/png", png_data)
s, b = req("POST", "/assets/upload", headers=AUTH, binary_body=body, ctype=ctype)
chk("Upload 201", s == 201, str(s))
AID   = b.get("asset_id", "")
FP_ID = b.get("fingerprint_id", "")
chk("asset_id present", bool(AID))
chk("fingerprint_id in response", bool(FP_ID), FP_ID)
chk("status = processing", b.get("status") == "processing", b.get("status"))

# ── Fingerprint status endpoint ───────────────────────────────────────────────
print("\n[4] GET /assets/{id}/fingerprint-status")
s, b = req("GET", f"/assets/{AID}/fingerprint-status", headers=AUTH)
chk("Status endpoint 200", s == 200, str(s))
chk("fingerprint_id matches", b.get("fingerprint_id") == FP_ID)
chk("model = ResNet50-IMAGENET1K_V1-v1.0", b.get("model_used") == "ResNet50-IMAGENET1K_V1-v1.0",
    b.get("model_used"))
chk("embedding_dim = 2048", b.get("embedding_dim") == 2048)

# ── Poll until completed ──────────────────────────────────────────────────────
print("\n[5] Polling until completed (max 90s)...")
completed = False
for i in range(45):
    time.sleep(2)
    s, b = req("GET", f"/assets/{AID}/fingerprint-status", headers=AUTH)
    ps  = b.get("processing_status", "?")
    hfp = b.get("has_embedding", False)
    fc  = b.get("frame_count")
    ms  = b.get("processing_duration_ms")
    print(f"  [{i*2:3d}s] {ps} | has_embedding={hfp} | frames={fc} | {ms}ms")
    if ps == "completed":
        completed = True
        chk("Fingerprinting completed", True)
        chk("has_embedding = True", hfp is True)
        chk("frame_count = 1 (image)", fc == 1, str(fc))
        chk("completed_at is set", b.get("completed_at") is not None)
        break
    if ps == "failed":
        chk("Fingerprinting completed", False, b.get("error_message", "no message"))
        break

if completed:
    # ── Asset reflects completed ──────────────────────────────────────────────
    print("\n[6] GET /assets/{id} reflects completed state")
    s, b = req("GET", f"/assets/{AID}", headers=AUTH)
    chk("GET asset 200", s == 200)
    chk("status = completed", b.get("status") == "completed", b.get("status"))
    chk("has_fingerprint = True", b.get("has_fingerprint") is True)
    chk("fingerprint_dim = 2048", b.get("fingerprint_dim") == 2048)
    chk("fingerprint_id linked", b.get("fingerprint_id") == FP_ID)

    # ── FAISS ─────────────────────────────────────────────────────────────────
    print("\n[7] FAISS index updated")
    s, b = req("GET", "/health")
    chk("faiss_vectors >= 1", b.get("faiss_vectors", 0) >= 1, str(b.get("faiss_vectors")))

    # ── Detect — asset_id mode ───────────────────────────────────────────────
    print("\n[8] POST /detect (asset_id mode)")
    bd, ct = mpf(asset_id=AID, top_k=5)
    s, b = req("POST", "/detect", headers=AUTH, binary_body=bd, ctype=ct)
    chk("Detect 200", s == 200, str(s))
    chk("query_asset_id echoed", b.get("query_asset_id") == AID)
    chk("total_matches is int", isinstance(b.get("total_matches"), int))
    print(f"  matches: {b.get('matches')}")

    # ── Detect — file mode ────────────────────────────────────────────────────
    print("\n[9] POST /detect (file mode — same image = strong match)")
    bd2, ct2 = mp("copy.png", "image/png", png_data)
    s, b = req("POST", "/detect", headers=AUTH, binary_body=bd2, ctype=ct2)
    chk("Detect file mode 200", s == 200, str(s))
    chk("At least 1 match", b.get("total_matches", 0) >= 1, str(b.get("total_matches")))
    if b.get("matches"):
        top = b["matches"][0]
        chk("Top similarity >= 0.90 (strong)", top.get("similarity", 0) >= 0.90,
            f"sim={top.get('similarity')}")
        chk("match_strength = strong", top.get("match_strength") == "strong")
    print(f"  matches: {b.get('matches')}")

# ── Error handling ────────────────────────────────────────────────────────────
print("\n[10] Error handling")
s, b = req("GET", f"/assets/{AID}/fingerprint-status",
           headers={"Authorization": "Bearer INVALID"})
chk("Invalid JWT -> 401", s == 401, str(s))
chk("401 uses error envelope", "error" in b and "code" in b, str(b))

s, b = req("GET", "/assets/notanid/fingerprint-status", headers=AUTH)
chk("Bad ObjectId -> 400", s == 400, str(s))

s, b = req("GET", "/assets/000000000000000000000099/fingerprint-status", headers=AUTH)
chk("Non-existent asset -> 404", s == 404, str(s))

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print(SEP)
passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
print(f"Results: {passed}/{total} passed")
if passed < total:
    print("Failed:")
    for name, ok, detail in results:
        if not ok:
            print(f"  [FAIL] {name}  | {detail}")
print(SEP)
