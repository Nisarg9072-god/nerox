"""
Phase 2 upgrade end-to-end test suite.
Run: python test_phase2.py
"""
import urllib.request
import urllib.error
import json
import uuid

BASE = "http://localhost:8000"

PASS = "[PASS]"
FAIL = "[FAIL]"
SEP  = "-" * 60

def req(method, path, data=None, headers=None, binary_body=None, ctype=None):
    url   = BASE + path
    h     = headers or {}
    body  = None
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

def make_png():
    return (
        b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
        b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
        b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
        b'\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
    )

def multipart(filename, content_type, data):
    b = uuid.uuid4().hex
    body = (
        ("--" + b + "\r\n").encode()
        + f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode()
        + f"Content-Type: {content_type}\r\n\r\n".encode()
        + data
        + ("\r\n--" + b + "--\r\n").encode()
    )
    return body, f"multipart/form-data; boundary={b}"

results = []

def check(name, ok, detail=""):
    results.append((name, ok, detail))
    tag = PASS if ok else FAIL
    print(f"  {tag} {name}" + (f"  |  {detail}" if detail else ""))

print(SEP)
print("Nerox Phase 2 Upgrade Test Suite")
print(SEP)

# ── Health ──────────────────────────────────────────────────────────────────
print("\n[1] Health")
s, b = req("GET", "/health")
check("GET /health returns 200", s == 200)
check("Version is 2.0.0", b.get("version") == "2.0.0", b.get("version"))
check("Storage type in response", "storage" in b, b.get("storage"))

# ── Login ───────────────────────────────────────────────────────────────────
print("\n[2] Auth — login")
s, b = req("POST", "/auth/login", {"email": "testuser@nerox.io", "password": "TestPass1"})
check("Login returns 200", s == 200)
TOKEN = b.get("access_token", "")
AUTH  = {"Authorization": f"Bearer {TOKEN}"}
check("Token issued", bool(TOKEN))

# ── Error format ─────────────────────────────────────────────────────────────
print("\n[3] Error response format")
s, b = req("GET", "/assets/badid", headers=AUTH)
check("Bad ObjectId returns 400", s == 400, str(s))
check("Error envelope has 'error' key", "error" in b, str(b))
check("Error envelope has 'code' key", "code" in b, str(b))

s, b = req("GET", "/assets/000000000000000000000099", headers=AUTH)
check("Non-existent asset returns 404", s == 404, str(s))
check("404 uses error envelope", "error" in b, str(b))

s, b = req("GET", "/assets", headers={"Authorization": "Bearer INVALID"})
check("Invalid token returns 401", s == 401, str(s))
check("401 uses error envelope", "error" in b, str(b))

# ── Upload — happy path ───────────────────────────────────────────────────────
print("\n[4] Upload — valid PNG")
body, ctype = multipart("photo.png", "image/png", make_png())
s, b = req("POST", "/assets/upload", headers=AUTH, binary_body=body, ctype=ctype)
check("Upload returns 201", s == 201, str(s))
check("Response has asset_id", "asset_id" in b)
check("Response has file_url", "file_url" in b, b.get("file_url"))
check("Response has status=uploaded", b.get("status") == "uploaded")
ASSET_ID = b.get("asset_id", "")

# ── GET /assets/{asset_id} — owner ────────────────────────────────────────────
print("\n[5] GET /assets/{asset_id}")
s, b = req("GET", f"/assets/{ASSET_ID}", headers=AUTH)
check("Owner can fetch own asset (200)", s == 200, str(s))
check("file_url present in single-asset response", "file_url" in b, b.get("file_url"))

# ── GET /assets/{asset_id} — 2nd user (403) ───────────────────────────────────
print("\n[6] Ownership enforcement")
email2 = f"user2_{uuid.uuid4().hex[:6]}@nerox.io"
req("POST", "/auth/register", {"company_name": "Other Corp", "email": email2, "password": "Test2Pass1"})
_, b2    = req("POST", "/auth/login", {"email": email2, "password": "Test2Pass1"})
AUTH2    = {"Authorization": f"Bearer {b2.get('access_token','')}"}

s, b = req("GET", f"/assets/{ASSET_ID}", headers=AUTH2)
check("Other user gets 403 (not 404)", s == 403, str(s))
check("403 uses error envelope", "error" in b, str(b))

s, b = req("GET", "/assets", headers=AUTH2)
check("Other user's GET /assets returns 0 items", b.get("total") == 0, str(b.get("total")))

# ── Upload — extension spoofing (magic bytes) ─────────────────────────────────
print("\n[7] Magic-byte anti-spoofing")
# Send JPEG bytes but claim it's a .png
jpeg_bytes = b'\xff\xd8\xff\xe0' + b'\x00' * 20
body, ctype = multipart("evil.png", "image/png", jpeg_bytes)
s, b = req("POST", "/assets/upload", headers=AUTH, binary_body=body, ctype=ctype)
check("JPEG bytes in .png file rejected (422)", s == 422, str(s))

# Send plain text renamed to .jpg
body, ctype = multipart("script.jpg", "image/jpeg", b"<?php echo shell_exec($_GET['cmd']); ?>")
s, b = req("POST", "/assets/upload", headers=AUTH, binary_body=body, ctype=ctype)
check("Text/PHP bytes in .jpg file rejected (422)", s == 422, str(s))

# ── Upload — unsupported extension ────────────────────────────────────────────
print("\n[8] Unsupported file type")
body, ctype = multipart("doc.pdf", "application/pdf", b"%PDF fake content")
s, b = req("POST", "/assets/upload", headers=AUTH, binary_body=body, ctype=ctype)
check("PDF rejected (422)", s == 422, str(s))

# ── Upload — file size label in error ────────────────────────────────────────
print("\n[9] GET /assets list")
s, b = req("GET", "/assets", headers=AUTH)
check("GET /assets returns 200", s == 200, str(s))
check("total >= 1", b.get("total", 0) >= 1, str(b.get("total")))
check("Each item has file_url", all("file_url" in a for a in b.get("assets", [])))

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print(SEP)
passed = sum(1 for _, ok, _ in results if ok)
total  = len(results)
print(f"Results: {passed}/{total} passed")
if passed < total:
    print("Failed tests:")
    for name, ok, detail in results:
        if not ok:
            print(f"  {FAIL} {name}  |  {detail}")
print(SEP)
