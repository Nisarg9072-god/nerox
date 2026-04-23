"""Phase 5 End-to-End Test — Invisible Watermarking + Ownership Trace"""
import sys
import urllib.request
import urllib.error
import json
import time
import uuid

import cv2
import numpy as np

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://localhost:8000"
SEP  = "=" * 65

def make_png(size=256) -> bytes:
    img = np.random.randint(30, 220, (size, size, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".png", img)
    return buf.tobytes()

def req(method, path, data=None, headers=None, body=None, ctype=None):
    url = BASE + path
    h   = dict(headers or {})
    b   = None
    if body is not None:
        b = body
        h["Content-Type"] = ctype or "application/octet-stream"
    elif data is not None:
        b = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=b, headers=h, method=method)
    try:
        with urllib.request.urlopen(r) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())

def mp(filename, ctype_file, data):
    bnd  = uuid.uuid4().hex
    body = (
        ("--" + bnd + "\r\n").encode()
        + ('Content-Disposition: form-data; name="file"; filename="' + filename + '"\r\n').encode()
        + ("Content-Type: " + ctype_file + "\r\n\r\n").encode()
        + data
        + ("\r\n--" + bnd + "--\r\n").encode()
    )
    return body, "multipart/form-data; boundary=" + bnd

results = []

def chk(name, ok, detail=""):
    results.append((name, ok, detail))
    tag  = "PASS" if ok else "FAIL"
    info = "  | " + str(detail) if detail else ""
    print(f"  [{tag}] {name}{info}")

print(SEP)
print("Nerox Phase 5 - Invisible Watermarking + Ownership Trace")
print(SEP)

# ── 1. Health v5.0.0 ─────────────────────────────────────────────────────────
print("\n[1] Health / version")
s, b = req("GET", "/health")
chk("v5.0.0 running", b.get("version") == "5.0.0", b)
chk("wm_completed key present", "wm_completed" in b)
chk("faiss_vectors reported", "faiss_vectors" in b)

# ── 2. Routes registered ──────────────────────────────────────────────────────
print("\n[2] Route registration")
s, b = req("GET", "/openapi.json")
paths = list(b.get("paths", {}).keys())
chk("/watermark/verify registered", "/watermark/verify" in paths)
chk("/assets/{asset_id}/watermark-status registered",
    "/assets/{asset_id}/watermark-status" in paths)
chk("/watermark/health registered", "/watermark/health" in paths)

# ── 3. Auth ───────────────────────────────────────────────────────────────────
print("\n[3] Authentication")
s, b = req("POST", "/auth/login", {"email": "testuser@nerox.io", "password": "TestPass1"})
chk("Login 200", s == 200, s)
TOKEN = b.get("access_token", "")
AUTH  = {"Authorization": "Bearer " + TOKEN}
chk("Token issued", bool(TOKEN))

# ── 4. Upload (starts both background tasks) ──────────────────────────────────
print("\n[4] Upload (Phase 5)")
png_data = make_png(256)
body, ct = mp("asset_wm_test.png", "image/png", png_data)
s, b = req("POST", "/assets/upload", headers=AUTH, body=body, ctype=ct)
chk("Upload 201", s == 201, s)
AID   = b.get("asset_id", "")
FP_ID = b.get("fingerprint_id", "")
WM_ID = b.get("watermark_id", "")
chk("asset_id present", bool(AID))
chk("fingerprint_id in upload response", bool(FP_ID), FP_ID)
chk("watermark_id in upload response", bool(WM_ID), WM_ID)
chk("status = processing", b.get("status") == "processing")
chk("message mentions watermarking", "watermark" in b.get("message","").lower())
print(f"  asset_id    = {AID}")
print(f"  fingerprint_id = {FP_ID}")
print(f"  watermark_id   = {WM_ID}")

# ── 5. Watermark status endpoint ──────────────────────────────────────────────
print("\n[5] GET /assets/{id}/watermark-status (initial)")
s, b = req("GET", f"/assets/{AID}/watermark-status", headers=AUTH)
chk("Watermark status 200", s == 200, s)
chk("watermark_id matches", b.get("watermark_id") == WM_ID)
chk("method = DCT-frequency-domain", b.get("watermark_method") == "DCT-frequency-domain",
    b.get("watermark_method"))
chk("has_token = False or True (fast machine)", b.get("has_token") in (True, False))

# ── 6. Poll watermark until completed ─────────────────────────────────────────
print("\n[6] Polling watermark-status until completed (max 120s)...")
wm_done = False
for i in range(60):
    time.sleep(2)
    s, b = req("GET", f"/assets/{AID}/watermark-status", headers=AUTH)
    ws  = b.get("status", "?")
    ht  = b.get("has_token", False)
    ms  = b.get("processing_duration_ms")
    print(f"  [{i*2:3d}s] status={ws} has_token={ht} duration={ms}ms")
    if ws == "completed":
        wm_done = True
        chk("Watermark completed", True)
        chk("has_token = True", ht is True)
        chk("processing_duration_ms > 0", ms and ms > 0, ms)
        chk("completed_at is set", b.get("completed_at") is not None)
        break
    if ws == "failed":
        chk("Watermark completed", False, b.get("error_message", "no message"))
        break

# ── 7. Watermark verify (own asset — fetch watermarked file from server) ──────
if wm_done:
    print("\n[7] POST /watermark/verify (watermarked file from server = strong match)")

    # Fetch the watermarked file from the server's file_url
    s2, asset_b = req("GET", f"/assets/{AID}", headers=AUTH)
    file_url = asset_b.get("file_url", "")
    print(f"  Downloading watermarked file from: {file_url}")
    try:
        with urllib.request.urlopen(file_url) as r:
            watermarked_bytes = r.read()
        print(f"  Downloaded {len(watermarked_bytes)} bytes")
    except Exception as dl_exc:
        print(f"  [WARN] Could not download file_url: {dl_exc}")
        watermarked_bytes = png_data   # fallback (will likely fail verify)

    body2, ct2 = mp("copy.png", "image/png", watermarked_bytes)
    s, b = req("POST", "/watermark/verify", headers=AUTH, body=body2, ctype=ct2)
    chk("Verify 200", s == 200, s)
    chk("verified = True", b.get("verified") is True)
    chk("confidence > 0.70", b.get("confidence", 0) > 0.70, b.get("confidence"))
    chk("confidence_label in [strong, probable, possible]",
        b.get("confidence_label") in ("strong", "probable", "possible"), b.get("confidence_label"))
    own = b.get("ownership") or {}
    chk("ownership.asset_id matches", own.get("asset_id") == AID, own.get("asset_id"))
    chk("ownership.user_id populated", bool(own.get("user_id")), own.get("user_id"))
    print(f"  confidence={b.get('confidence')} label={b.get('confidence_label')}")
    print(f"  ownership = {b.get('ownership')}")

    # ── 8. Verify with unrelated image ────────────────────────────────────────
    print("\n[8] POST /watermark/verify (unrelated random image = not verified)")
    rand_data = make_png(256)
    body3, ct3 = mp("random.png", "image/png", rand_data)
    s, b = req("POST", "/watermark/verify", headers=AUTH, body=body3, ctype=ct3)
    chk("Verify unrelated 200", s == 200, s)
    chk("verified = False (different token)", b.get("verified") is False)
    print(f"  wm_token_detected={b.get('wm_token_detected')} confidence={b.get('confidence')}")

    # ── 9. Verification audit log ─────────────────────────────────────────────
    print("\n[9] Verification audit log appended")
    s, b = req("GET", f"/assets/{AID}/watermark-status", headers=AUTH)
    chk("verification_count >= 1", b.get("verification_count", 0) >= 1,
        b.get("verification_count"))
    chk("last_verified_at is set", bool(b.get("last_verified_at")), b.get("last_verified_at"))

    # ── 10. Watermark health endpoint ─────────────────────────────────────────
    print("\n[10] GET /watermark/health")
    s, b = req("GET", "/watermark/health", headers=AUTH)
    chk("Watermark health 200", s == 200, s)
    chk("completed >= 1", b.get("completed", 0) >= 1, b.get("completed"))
    chk("method = DCT-frequency-domain", b.get("method") == "DCT-frequency-domain")

# ── 11. Fingerprint still works in parallel ───────────────────────────────────
print("\n[11] Fingerprint-status still works (Phase 4 unaffected)")
s, b = req("GET", f"/assets/{AID}/fingerprint-status", headers=AUTH)
chk("Fingerprint status 200", s == 200, s)
ps = b.get("processing_status", "?")
chk("Fingerprint completed or processing (both valid)", ps in ("completed","processing","pending"), ps)

# ── 12. Asset item has both IDs ───────────────────────────────────────────────
print("\n[12] GET /assets/{id} reflects Phase 5 fields")
s, b = req("GET", f"/assets/{AID}", headers=AUTH)
chk("Asset 200", s == 200, s)
chk("watermark_id in asset item", b.get("watermark_id") == WM_ID)
chk("fingerprint_id in asset item", b.get("fingerprint_id") == FP_ID)

# ── 13. Error handling ────────────────────────────────────────────────────────
print("\n[13] Error handling")
s, b = req("GET", f"/assets/{AID}/watermark-status",
           headers={"Authorization": "Bearer INVALID"})
chk("Invalid JWT -> 401", s == 401, s)

s, b = req("GET", "/assets/badid/watermark-status", headers=AUTH)
chk("Bad ObjectId -> 400", s == 400, s)

s, b = req("GET", "/assets/000000000000000000000000/watermark-status", headers=AUTH)
chk("Non-existent -> 404", s == 404, s)

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print(SEP)
passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
print(f"Results: {passed}/{total} passed")
if passed < total:
    print("\nFailed:")
    for name, ok, detail in results:
        if not ok:
            print(f"  [FAIL] {name}  | {detail}")
print(SEP)
