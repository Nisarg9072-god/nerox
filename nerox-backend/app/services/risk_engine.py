"""
app/services/risk_engine.py
============================
Pure-Python risk scoring engine for Nerox detection events.

Risk Score Formula (0–100)
---------------------------
The score is composed of four independent components:

  Component 1 — Similarity (weight 40 pts)
    similarity_score × 40
    Direct measure of how closely the detected content matches the original.

  Component 2 — Watermark verification (weight 25 pts)
    +25 if DCT watermark successfully extracted and matched in DB.
    Watermark confirmation is the strongest form of ownership proof.

  Component 3 — Platform severity (weight 20 pts)
    Platforms are pre-ranked by their typical piracy risk:
      - Telegram channels / torrent / pirate sites → 20
      - Instagram / TikTok / Facebook → 15 (wide reach, frequent piracy)
      - YouTube / Twitter / Reddit → 12
      - Generic websites → 10
      - Unknown → 5
    Higher reach + weaker DMCA enforcement = higher score.

  Component 4 — Detection frequency (weight 15 pts)
    How many times has this asset been detected before?
    Increases logarithmically:  0→0, 1→3, 3→7, 5→10, 10→15
    Repeated detections indicate systematic misuse.

Risk Labels
-----------
  0–25   = "low"
  26–50  = "medium"
  51–75  = "high"
  76–100 = "critical"

Design notes
------------
  • All arithmetic is integer/float — no ML dependencies.
  • Each component is bounded to prevent overflow.
  • Function is pure (stateless) — safe to call from async contexts.
  • detection_count is passed in (not fetched here) to keep the function fast.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Platform severity table
# ---------------------------------------------------------------------------

PLATFORM_SEVERITY: dict[str, int] = {
    # Highest risk — active piracy ecosystems, weak enforcement
    "telegram":         20,
    "telegram_channel": 20,
    "torrent":          20,
    "pirate_site":      20,
    "warez":            20,
    "darkweb":          20,

    # High reach social media — viral spread potential
    "instagram":        15,
    "tiktok":           15,
    "facebook":         15,
    "snapchat":         14,
    "reddit":           13,
    "twitter":          12,

    # Moderated platforms — DMCA takedowns effective but volume is high
    "youtube":          12,
    "twitch":           11,
    "vimeo":            10,

    # Websites — varied, harder to assess
    "website":          10,
    "blog":              8,
    "forum":             8,
    "other":             7,

    # Source unknown
    "unknown":           5,
}


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def calculate_risk_score(
    similarity_score:   float,
    watermark_verified: bool,
    platform_name:      str,
    detection_count:    int,
) -> int:
    """
    Compute a risk score [0, 100] for a detection event.

    Args:
        similarity_score:   Cosine similarity or watermark confidence [0, 1].
        watermark_verified: True if DCT watermark extraction confirmed ownership.
        platform_name:      Platform where the content was found.
        detection_count:    Number of prior detections for this same asset.

    Returns:
        Integer risk score in [0, 100].
    """
    # Component 1: Similarity (0–40)
    sim_component = round(similarity_score * 40)

    # Component 2: Watermark verification (0 or 25)
    wm_component = 25 if watermark_verified else 0

    # Component 3: Platform severity (0–20)
    plat_key       = platform_name.strip().lower()
    plat_component = PLATFORM_SEVERITY.get(plat_key, PLATFORM_SEVERITY["other"])

    # Component 4: Detection frequency (0–15, logarithmic growth)
    if detection_count <= 0:
        freq_component = 0
    elif detection_count == 1:
        freq_component = 3
    elif detection_count <= 3:
        freq_component = 7
    elif detection_count <= 5:
        freq_component = 10
    elif detection_count <= 10:
        freq_component = 13
    else:
        freq_component = 15

    total = sim_component + wm_component + plat_component + freq_component
    return min(total, 100)


def risk_label(score: int) -> str:
    """
    Convert a numeric risk score to a human-readable label.

    Returns:
        'low' | 'medium' | 'high' | 'critical'
    """
    if score <= 25:
        return "low"
    if score <= 50:
        return "medium"
    if score <= 75:
        return "high"
    return "critical"


def confidence_from_similarity(similarity: float) -> str:
    """
    Map a cosine similarity score to a confidence label.

    Args:
        similarity: Float [0, 1].

    Returns:
        'strong' | 'medium' | 'low'
    """
    if similarity >= 0.90:
        return "strong"
    if similarity >= 0.70:
        return "medium"
    return "low"


def recommendation(risk: str, detection_count: int) -> str:
    """
    Generate an action recommendation string based on risk level and frequency.

    Args:
        risk:            Risk label ('low'|'medium'|'high'|'critical').
        detection_count: Total number of detections for the asset.

    Returns:
        Recommendation string suitable for display in a dashboard.
    """
    if risk == "critical":
        return "Immediate DMCA takedown required. Escalate to legal team."
    if risk == "high":
        return "Issue takedown notice. Monitor for further spread."
    if risk == "medium":
        if detection_count >= 5:
            return "Consider issuing a takedown. Pattern of misuse detected."
        return "Monitor closely. Set up automated alerts for new detections."
    return "Low priority. Continue routine monitoring."
