"""
Detection accuracy smoke test (real-world transforms).

Runs a small matrix against POST /detect (file mode):
  - exact same image (uploaded twice so there is a match)
  - resized (downscale then upscale)
  - compressed JPEG
  - slight center crop + resize

Outputs:
  - match counts and top similarity per variant
  - similarity distribution (top-5) per variant

Usage:
  python test_detection_accuracy.py
"""

from __future__ import annotations

import io
import json
import time
import uuid
import urllib.error
import urllib.request

import cv2
import numpy as np

BASE = "http://localhost:8000"


def req(method, path, *, data=None, headers=None, binary_body=None, ctype=None):
    url = BASE + path
    h = headers or {}
    body = None
    if binary_body is not None:
        body = binary_body
        h["Content-Type"] = ctype or "application/octet-stream"
    elif data is not None:
        body = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=40) as res:
            raw = res.read()
            return res.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def multipart_file(field_name: str, filename: str, content_type: str, data: bytes):
    boundary = uuid.uuid4().hex
    body = (
        (f"--{boundary}\r\n").encode()
        + f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'.encode()
        + f"Content-Type: {content_type}\r\n\r\n".encode()
        + data
        + (f"\r\n--{boundary}--\r\n").encode()
    )
    return body, f"multipart/form-data; boundary={boundary}"


def make_test_png_bytes() -> bytes:
    # Simple 256x256 synthetic image with structure (better for embeddings than 1x1).
    img = np.zeros((256, 256, 3), dtype=np.uint8)
    cv2.rectangle(img, (20, 20), (236, 236), (255, 255, 255), 3)
    cv2.circle(img, (128, 128), 60, (0, 255, 0), 4)
    cv2.putText(img, "NEROX", (55, 140), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise RuntimeError("Failed to encode PNG")
    return buf.tobytes()


def variant_resize(png_bytes: bytes) -> bytes:
    img = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    small = cv2.resize(img, (128, 128), interpolation=cv2.INTER_AREA)
    back = cv2.resize(small, (256, 256), interpolation=cv2.INTER_CUBIC)
    ok, buf = cv2.imencode(".png", back)
    return buf.tobytes() if ok else png_bytes


def variant_compress_jpeg(png_bytes: bytes) -> bytes:
    img = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
    return buf.tobytes() if ok else png_bytes


def variant_center_crop(png_bytes: bytes) -> bytes:
    img = cv2.imdecode(np.frombuffer(png_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
    h, w = img.shape[:2]
    side = int(min(h, w) * 0.85)
    y0 = (h - side) // 2
    x0 = (w - side) // 2
    crop = img[y0:y0 + side, x0:x0 + side]
    crop = cv2.resize(crop, (256, 256), interpolation=cv2.INTER_LANCZOS4)
    ok, buf = cv2.imencode(".png", crop)
    return buf.tobytes() if ok else png_bytes


def main():
    print("=== Detection accuracy smoke test ===")

    # login
    s, b = req("POST", "/auth/login", data={"email": "testuser@nerox.io", "password": "TestPass1"})
    if s != 200:
        raise SystemExit(f"Login failed: {s} {b}")
    token = b.get("access_token")
    auth = {"Authorization": f"Bearer {token}"}

    # Seed DB: upload the same asset twice so /detect has something to match.
    seed = make_test_png_bytes()
    for i in range(2):
        body, ctype = multipart_file("file", f"seed_{i}.png", "image/png", seed)
        s, b = req("POST", "/assets/upload", headers=auth, binary_body=body, ctype=ctype)
        if s != 201:
            raise SystemExit(f"Upload failed: {s} {b}")
        print(f"Seed upload {i+1}/2: asset_id={b.get('asset_id')}")

    # Give workers a moment to fingerprint/watermark in background
    time.sleep(3)

    variants = [
        ("exact_png", "image/png", seed),
        ("resize_png", "image/png", variant_resize(seed)),
        ("compress_jpg", "image/jpeg", variant_compress_jpeg(seed)),
        ("crop_png", "image/png", variant_center_crop(seed)),
    ]

    for name, ctype_img, data in variants:
        body, ctype = multipart_file("file", f"{name}.png" if "png" in ctype_img else f"{name}.jpg", ctype_img, data)
        s, b = req("POST", "/detect", headers=auth, binary_body=body, ctype=ctype)
        if s != 200:
            print(f"[FAIL] /detect {name}: {s} {b}")
            continue
        matches = b.get("matches", [])
        sims = [m.get("similarity") for m in matches]
        top = sims[0] if sims else None
        print(f"[OK] {name}: matches={len(matches)} top_similarity={top} top5={sims[:5]}")


if __name__ == "__main__":
    main()

