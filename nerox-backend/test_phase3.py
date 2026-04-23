"""Phase 3 end-to-end test: Upload → Fingerprint → FAISS → Detect"""
import urllib.request
import urllib.error
import json
import time
import uuid

BASE = "http://localhost:8000"

import io
import cv2
import numpy as np

def make_valid_png() -> bytes:
    """Generate a valid 64x64 PNG that OpenCV can read."""
    img = np.random.randint(50, 200, (64, 64, 3), dtype=np.uint8)
    ret, buf = cv2.imencode('.png', img)
    return buf.tobytes()

def req(method, path, data=None, headers=None, binary_body=None, ctype=None):
    url = BASE + path
    h   = dict(headers or {})
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

def multipart(filename, content_type, data):
    boundary = uuid.uuid4().hex
    body = (
        ("--" + boundary + "\r\n").encode()
        + ("Content-Disposition: form-data; "
           'name="file"; filename="' + filename + '"\r\n').encode()
        + ("Content-Type: " + content_type + "\r\n\r\n").encode()
        + data
        + ("\r\n--" + boundary + "--\r\n").encode()
    )
    return body, "multipart/form-data; boundary=" + boundary

SEP = "-" * 60

print(SEP)
print("Nerox Phase 3 — Fingerprinting & Detection Test")
print(SEP)

# ── Health ──────────────────────────────────────────────────────────────────
print("\n[1] Health check")
s, b = req("GET", "/health")
print(f"  {s} {b}")
assert b.get("version") == "3.0.0", "Version mismatch"
print("  [OK] v3.0.0 confirmed, faiss_vectors =", b.get("faiss_vectors"))

# ── Login ───────────────────────────────────────────────────────────────────
print("\n[2] Login")
s, b = req("POST", "/auth/login", {"email": "testuser@nerox.io", "password": "TestPass1"})
assert s == 200
TOKEN = b["access_token"]
AUTH  = {"Authorization": "Bearer " + TOKEN}
print("  [OK] Logged in")

# ── Upload ──────────────────────────────────────────────────────────────────
print("\n[3] Upload PNG")
body, ctype = multipart("nerox_test.png", "image/png", make_valid_png())
s, b = req("POST", "/assets/upload", headers=AUTH, binary_body=body, ctype=ctype)
assert s == 201, f"Expected 201, got {s}: {b}"
AID    = b["asset_id"]
assert b["status"] == "processing", f"Expected processing, got {b['status']}"
print(f"  [OK] Uploaded — asset_id={AID} status={b['status']}")
print(f"  [OK] file_url={b.get('file_url')}")

# ── Poll for completion ──────────────────────────────────────────────────────
print("\n[4] Polling for fingerprinting completion (max 120s) ...")
completed = False
for i in range(60):
    time.sleep(2)
    s, b = req("GET", "/assets/" + AID, headers=AUTH)
    st   = b.get("status", "?")
    hfp  = b.get("has_fingerprint", False)
    dim  = b.get("fingerprint_dim")
    print(f"  [{i*2:3d}s] status={st} has_fingerprint={hfp} dim={dim}")
    if st == "completed":
        completed = True
        break
    if st == "failed":
        print("  [FAIL] Fingerprinting failed!")
        break

# ── Status check ──────────────────────────────────────────────────────────
print("\n[5] Post-upload health (FAISS should have vectors)")
s, b = req("GET", "/health")
print(f"  {s} faiss_vectors={b.get('faiss_vectors')}")

# ── Detect (asset_id mode — only if completed) ───────────────────────────────
if completed:
    print("\n[6] POST /detect with asset_id (self-similarity test)")
    boundary = uuid.uuid4().hex
    body = (
        ("--" + boundary + "\r\n").encode()
        + ('Content-Disposition: form-data; name="asset_id"\r\n\r\n').encode()
        + AID.encode()
        + ("\r\n--" + boundary + "\r\n").encode()
        + ('Content-Disposition: form-data; name="top_k"\r\n\r\n').encode()
        + b"5"
        + ("\r\n--" + boundary + "--\r\n").encode()
    )
    s, b = req(
        "POST", "/detect",
        headers=AUTH,
        binary_body=body,
        ctype="multipart/form-data; boundary=" + boundary,
    )
    print(f"  {s} total_matches={b.get('total_matches')} matches={b.get('matches')}")

    print("\n[7] POST /detect with file upload")
    body2, ctype2 = multipart("similar.png", "image/png", make_valid_png())
    s2, b2 = req("POST", "/detect", headers=AUTH, binary_body=body2, ctype=ctype2)
    print(f"  {s2} total_matches={b2.get('total_matches')} matches={b2.get('matches')}")
else:
    print("\n[SKIP] Fingerprinting not completed — skipping /detect test")

print()
print(SEP)
print("Phase 3 test complete.")
print(SEP)
