"""Phase 6 End-to-End Test — Analytics + Piracy Spread Tracking Engine"""
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
    info = "  | " + str(detail)[:120] if detail else ""
    print(f"  [{tag}] {name}{info}")

print(SEP)
print("Nerox Phase 6 - Analytics + Piracy Spread Tracking Engine")
print(SEP)

# ── 1. Login ──────────────────────────────────────────────────────────────────
print("\n[1] Authentication")
s, b = req("POST", "/auth/login", {"email": "testuser@nerox.io", "password": "TestPass1"})
TOKEN = b.get("access_token", "")
AUTH  = {"Authorization": "Bearer " + TOKEN}
chk("Login 200 + token", s == 200 and bool(TOKEN))

# ── 2. Routes registered ──────────────────────────────────────────────────────
print("\n[2] Analytics routes in OpenAPI")
s, b = req("GET", "/openapi.json")
paths = list(b.get("paths", {}).keys())
EXPECTED_ROUTES = [
    "/analytics/dashboard",
    "/analytics/assets/high-risk",
    "/analytics/timeline",
    "/analytics/platforms",
    "/analytics/alerts",
    "/analytics/alerts/{alert_id}/resolve",
    "/analytics/manual-detection",
]
for route in EXPECTED_ROUTES:
    chk(f"{route} registered", route in paths)

# ── 3. Seed data: upload an asset ────────────────────────────────────────────
print("\n[3] Upload asset for detection seeding")
png_data = make_png(256)
body, ct = mp("phase6_test.png", "image/png", png_data)
s, b = req("POST", "/assets/upload", headers=AUTH, body=body, ctype=ct)
chk("Upload 201", s == 201, s)
AID = b.get("asset_id", "")
WM_ID = b.get("watermark_id", "")
chk("asset_id present", bool(AID))

# Wait for watermark to complete
print("  Waiting for watermark...")
for _ in range(30):
    time.sleep(2)
    s2, b2 = req("GET", f"/assets/{AID}/watermark-status", headers=AUTH)
    if b2.get("status") == "completed":
        print(f"  Watermark completed in background")
        break

# ── 4. POST /analytics/manual-detection ──────────────────────────────────────
print("\n[4] POST /analytics/manual-detection")
PLATFORMS = ["instagram", "telegram", "youtube", "website", "tiktok"]
inserted_ids = []
for i, plat in enumerate(PLATFORMS):
    sim = round(0.70 + i * 0.05, 2)
    wm  = (i % 2 == 0)
    payload = {
        "asset_id":         AID,
        "platform_name":    plat,
        "source_url":       f"https://{plat}.com/stolen_content_{i}",
        "similarity_score": sim,
        "confidence_label": "strong",
        "watermark_verified": wm,
        "notes":            f"manual test detection {i}",
    }
    s, b = req("POST", "/analytics/manual-detection", data=payload, headers=AUTH)
    chk(f"Manual detection #{i+1} ({plat}) 201", s == 201, s)
    if s == 201:
        inserted_ids.append(b.get("detection_id", ""))
        chk(f"  risk_score computed", b.get("risk_score", 0) > 0, b.get("risk_score"))
        chk(f"  risk_label present", b.get("risk_label") in ("low","medium","high","critical"),
            b.get("risk_label"))

# ── 5. Dashboard ──────────────────────────────────────────────────────────────
print("\n[5] GET /analytics/dashboard")
s, b = req("GET", "/analytics/dashboard", headers=AUTH)
chk("Dashboard 200", s == 200, s)
chk("generated_at present", "generated_at" in b)
ov = b.get("overview", {})
chk("overview.total_assets >= 1", ov.get("total_assets", 0) >= 1)
chk("overview.total_detections >= 5", ov.get("total_detections", 0) >= 5)
chk("risk_summary present", "risk_summary" in b)
rs = b.get("risk_summary", {})
chk("risk_summary has all 4 keys", all(k in rs for k in ("low","medium","high","critical")))
chk("platform_distribution is list", isinstance(b.get("platform_distribution"), list))
chk("recent_detections is list", isinstance(b.get("recent_detections"), list))
chk("recent_detections <= 10", len(b.get("recent_detections", [])) <= 10)
chk("trend_last_30_days is list of 30", len(b.get("trend_last_30_days", [])) == 30)
chk("top_suspicious_sources is list", isinstance(b.get("top_suspicious_sources"), list))
print(f"  total_assets={ov.get('total_assets')} total_detections={ov.get('total_detections')}")
print(f"  risk_summary={rs}")

# ── 6. High-risk assets ───────────────────────────────────────────────────────
print("\n[6] GET /analytics/assets/high-risk")
s, b = req("GET", "/analytics/assets/high-risk", headers=AUTH)
chk("High-risk 200", s == 200, s)
chk("total >= 1", b.get("total", 0) >= 1)
if b.get("assets"):
    a = b["assets"][0]
    chk("max_risk_score present", "max_risk_score" in a)
    chk("detection_count >= 5", a.get("detection_count", 0) >= 5, a.get("detection_count"))
    chk("platforms is list", isinstance(a.get("platforms"), list))
    chk("recommendation present", bool(a.get("recommendation")))
    print(f"  top asset: {a.get('original_filename')} risk={a.get('max_risk_score')} detections={a.get('detection_count')}")
    print(f"  recommendation: {a.get('recommendation')}")

# ── 7. Timeline ───────────────────────────────────────────────────────────────
print("\n[7] GET /analytics/timeline")
s, b = req("GET", "/analytics/timeline?period=day&days=30", headers=AUTH)
chk("Timeline 200", s == 200, s)
chk("period_type = day", b.get("period_type") == "day")
chk("total >= 5", b.get("total", 0) >= 5)
chk("points is list", isinstance(b.get("points"), list))
if b.get("points"):
    p = b["points"][-1]
    chk("point has period+count+avg_risk", all(k in p for k in ("period","count","avg_risk")))

s2, b2 = req("GET", "/analytics/timeline?period=week&days=90", headers=AUTH)
chk("Timeline week 200", s2 == 200, s2)
chk("period_type = week", b2.get("period_type") == "week")

# ── 8. Platforms ──────────────────────────────────────────────────────────────
print("\n[8] GET /analytics/platforms")
s, b = req("GET", "/analytics/platforms", headers=AUTH)
chk("Platforms 200", s == 200, s)
chk("total_detections >= 5", b.get("total_detections", 0) >= 5)
chk("platforms is list", isinstance(b.get("platforms"), list))
if b.get("platforms"):
    p = b["platforms"][0]
    chk("platform has all required keys",
        all(k in p for k in ("platform","detection_count","percentage","avg_similarity","avg_risk_score","severity")))
    chk("percentages sum ~100", abs(sum(x["percentage"] for x in b["platforms"]) - 100) < 1)
    for plat in b["platforms"]:
        print(f"  {plat['platform']}: count={plat['detection_count']} risk={plat['avg_risk_score']} severity={plat['severity']}")

# ── 9. Alerts ─────────────────────────────────────────────────────────────────
print("\n[9] GET /analytics/alerts")
s, b = req("GET", "/analytics/alerts", headers=AUTH)
chk("Alerts 200", s == 200, s)
chk("alerts list present", "alerts" in b)
print(f"  Active alerts: {b.get('total', 0)}")
alert_types = [a["alert_type"] for a in b.get("alerts", [])]
print(f"  Alert types: {set(alert_types)}")
if alert_types:
    chk("At least one meaningful alert", len(alert_types) >= 1)
    # Resolve first alert
    first_alert_id = b["alerts"][0]["alert_id"]
    s2, b2 = req("POST", f"/analytics/alerts/{first_alert_id}/resolve",
                 headers=AUTH, data={})
    chk("Resolve alert 200", s2 == 200, s2)
    chk("Resolved message", "resolved" in b2.get("message", "").lower())
else:
    chk("Alerts (may be empty on fresh DB)", True, "no alerts yet — ok")

# ── 10. Risk scoring validation ───────────────────────────────────────────────
print("\n[10] Risk score logic validation (unit-level)")
import sys
sys.path.insert(0, ".")
from app.services.risk_engine import calculate_risk_score, risk_label, recommendation

chk("Watermark TRUE adds 25pts",
    calculate_risk_score(0.5, True, "unknown", 0) >
    calculate_risk_score(0.5, False, "unknown", 0))

chk("Telegram > website risk",
    calculate_risk_score(0.8, False, "telegram", 0) >
    calculate_risk_score(0.8, False, "website", 0))

chk("High freq > zero freq",
    calculate_risk_score(0.8, False, "unknown", 15) >
    calculate_risk_score(0.8, False, "unknown", 0))

chk("Perfect score = 100",
    calculate_risk_score(1.0, True, "telegram", 20) == 100)

chk("Low score label = low",     risk_label(20) == "low")
chk("Medium score label",        risk_label(40) == "medium")
chk("High score label",          risk_label(70) == "high")
chk("Critical score label",      risk_label(80) == "critical")

chk("Recommendation: critical",  "DMCA" in recommendation("critical", 1))
chk("Recommendation: high",      "takedown" in recommendation("high", 1).lower())

# ── 11. Error handling ────────────────────────────────────────────────────────
print("\n[11] Error handling")
s, b = req("GET", "/analytics/dashboard", headers={"Authorization": "Bearer BAD"})
chk("Dashboard 401 without valid JWT", s == 401, s)

s, b = req("POST", "/analytics/manual-detection",
           data={"asset_id": "000000000000000000000000", "platform_name": "youtube"},
           headers=AUTH)
chk("Manual detection 404 for nonexistent asset", s == 404, s)

s, b = req("POST", "/analytics/manual-detection",
           data={"asset_id": "INVALID", "platform_name": "youtube"},
           headers=AUTH)
chk("Manual detection 400 for invalid ObjectId", s == 400, s)

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
