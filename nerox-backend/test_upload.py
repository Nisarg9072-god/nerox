"""
Live end-to-end test: Login → Upload → List Assets
Run: python test_upload.py
"""
import urllib.request
import json
import uuid
import os

BASE = "http://localhost:8000"

# ── 1. Login ──────────────────────────────────────────────────────────────────
body = json.dumps({"email": "testuser@nerox.io", "password": "TestPass1"}).encode()
req = urllib.request.Request(
    BASE + "/auth/login", data=body,
    headers={"Content-Type": "application/json"}, method="POST"
)
with urllib.request.urlopen(req) as res:
    token = json.loads(res.read())["access_token"]
print(f"[OK] Login    -- token: {token[:40]}...")

# ── 2. Upload a tiny valid PNG ─────────────────────────────────────────────────
# Minimal 1×1 white PNG (67 bytes)
image_bytes = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
    b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
    b'\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18'
    b'\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
)

boundary = uuid.uuid4().hex
body = (
    ("--" + boundary + "\r\n").encode()
    + ('Content-Disposition: form-data; name="file"; filename="test.png"\r\n').encode()
    + b"Content-Type: image/png\r\n\r\n"
    + image_bytes
    + ("\r\n--" + boundary + "--\r\n").encode()
)

req = urllib.request.Request(
    BASE + "/assets/upload",
    data=body,
    headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {token}",
    },
    method="POST",
)
with urllib.request.urlopen(req) as res:
    upload_result = json.loads(res.read())

print("[OK] Upload  --")
print(json.dumps(upload_result, indent=2))

# ── 3. List Assets ─────────────────────────────────────────────────────────────
req = urllib.request.Request(
    BASE + "/assets",
    headers={"Authorization": f"Bearer {token}"},
)
with urllib.request.urlopen(req) as res:
    assets = json.loads(res.read())

print(f"[OK] GET /assets -- total: {assets['total']}")
for a in assets["assets"]:
    print(f"  • {a['original_filename']} | {a['file_type']} | {a['file_size']} bytes | {a['status']}")

# ── 4. Check file on disk ──────────────────────────────────────────────────────
filename = upload_result["filename"]
disk_path = os.path.join("storage", "uploads", filename)
exists = os.path.exists(disk_path)
print(f"[OK] File on disk: {disk_path} exists={exists}")
