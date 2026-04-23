"""Phase 5 health + startup check"""
import sys
import time
import urllib.request
import json

sys.stdout.reconfigure(encoding="utf-8")
print("Waiting for server reload (Phase 5 v5.0.0)...")
for i in range(15):
    time.sleep(2)
    try:
        with urllib.request.urlopen("http://localhost:8000/health") as r:
            b = json.loads(r.read())
            v = b.get("version", "?")
            wm = b.get("wm_completed", "?")
            fv = b.get("faiss_vectors", "?")
            print(f"  [{i*2}s] version={v} wm_completed={wm} faiss_vectors={fv}")
            if v == "5.0.0":
                print("Phase 5 startup: OK")
                break
    except Exception as e:
        print(f"  [{i*2}s] not ready: {e}")
