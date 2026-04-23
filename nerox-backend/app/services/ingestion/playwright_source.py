from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote_plus, urlparse, urlunparse, parse_qsl, urlencode

from app.core.config import settings
from app.core.logger import get_logger
from app.services.ingestion.base import BaseSource, MediaItem, MediaType

logger = get_logger(__name__)

_DEFAULT_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1920, "height": 1080},
]
_REALISTIC_UAS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
]


class PlaywrightSource(BaseSource):
    """Dynamic website scraper using Playwright + headless Chromium."""

    @property
    def name(self) -> str:
        return "Playwright Dynamic Web"

    async def search(self, query: str, max_results: int = 20) -> List[MediaItem]:
        try:
            from playwright.async_api import async_playwright
        except Exception as exc:
            logger.warning("Playwright unavailable, dynamic scraping disabled: %s", exc)
            return []

        target_url = query if query.startswith(("http://", "https://")) else self._to_search_url(query)
        max_keep = max(1, min(max_results, settings.PLAYWRIGHT_MAX_IMAGES_PER_PAGE, 20))
        timeout_ms = max(5000, int(settings.PLAYWRIGHT_TIMEOUT))

        viewport = random.choice(_DEFAULT_VIEWPORTS)
        user_agent = random.choice(_REALISTIC_UAS)
        logger.info("Playwright page load start url=%s", target_url)
        urls: list[str] = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=bool(settings.PLAYWRIGHT_HEADLESS))
                context = await browser.new_context(
                    viewport=viewport,
                    user_agent=user_agent,
                    locale="en-US",
                )
                page = await context.new_page()
                page.set_default_navigation_timeout(timeout_ms)
                page.set_default_timeout(timeout_ms)

                await page.goto(target_url, wait_until="domcontentloaded")
                await self._human_delay()
                await self._scroll_for_lazy_load(page)
                await self._human_delay()

                urls = await self._extract_candidate_urls(page, target_url)
                await context.close()
                await browser.close()
        except Exception as exc:
            logger.warning("Playwright load/extract failed url=%s err=%s", target_url, exc)
            return []

        selected = self._select_best_urls(urls, page_url=target_url, limit=max_keep)

        logger.info(
            "Playwright extraction complete url=%s extracted=%d skipped=%d kept=%d",
            target_url,
            len(urls),
            selected.filtered_out,
            len(selected.urls),
        )
        return [
            MediaItem(
                url=u,
                title=u.split("/")[-1][:80],
                thumbnail_url=u,
                source_platform=(urlparse(target_url).hostname or "dynamic_web").lower(),
                media_type=MediaType.IMAGE,
                metadata={"page_url": target_url, "source_type": "dynamic_web"},
            )
            for u in selected.urls
        ]

    @staticmethod
    def _to_search_url(query: str) -> str:
        return f"https://www.google.com/search?tbm=isch&q={quote_plus(query)}"

    async def _scroll_for_lazy_load(self, page) -> None:
        max_depth = max(1, int(settings.PLAYWRIGHT_MAX_SCROLL_DEPTH))
        for _ in range(max_depth):
            await page.evaluate("window.scrollBy(0, document.body.scrollHeight * 0.8)")
            await self._human_delay()

    async def _human_delay(self) -> None:
        await asyncio.sleep(random.uniform(1.0, 3.0))

    async def _extract_candidate_urls(self, page, target_url: str) -> list[str]:
        # Collect src, data-src, srcset and background-image style URLs.
        js = """
        () => {
          const urls = [];
          const push = (u) => { if (u && typeof u === "string") urls.push(u.trim()); };
          const pickHighestSrcset = (srcset) => {
            if (!srcset) return null;
            const parts = srcset.split(',').map(s => s.trim()).filter(Boolean);
            if (parts.length === 0) return null;
            let best = parts[0];
            let bestW = 0;
            for (const p of parts) {
              const seg = p.split(/\\s+/);
              const cand = seg[0];
              const dim = seg[1] || "";
              const w = parseInt(dim.replace('w','')) || 0;
              if (w >= bestW) { bestW = w; best = cand; }
            }
            return best;
          };
          document.querySelectorAll('img').forEach(img => {
            push(img.getAttribute('src'));
            push(img.getAttribute('data-src'));
            push(img.getAttribute('data-original'));
            push(pickHighestSrcset(img.getAttribute('srcset')));
            push(pickHighestSrcset(img.getAttribute('data-srcset')));
          });
          document.querySelectorAll('*').forEach(el => {
            const bg = window.getComputedStyle(el).getPropertyValue('background-image');
            if (!bg || bg === 'none') return;
            const m = bg.match(/url\\((['"]?)(.*?)\\1\\)/);
            if (m && m[2]) push(m[2]);
          });
          return urls;
        }
        """
        raw = await page.evaluate(js)
        if not isinstance(raw, list):
            return []
        resolved = []
        for u in raw:
            if not isinstance(u, str):
                continue
            x = u.strip()
            if x.startswith("//"):
                x = "https:" + x
            elif x.startswith("/"):
                from urllib.parse import urljoin
                x = urljoin(target_url, x)
            resolved.append(x)
        return resolved

    @staticmethod
    def _is_high_quality_image_url(url: str) -> bool:
        return _is_candidate_image_url(url)

    @dataclass
    class _SelectionResult:
        urls: list[str]
        filtered_out: int
        rejected_reasons: dict[str, int]

    def _select_best_urls(self, urls: list[str], *, page_url: str, limit: int) -> _SelectionResult:
        """
        Post-process raw extracted URLs into a small, high-quality set suitable
        for detection (avoid placeholders, thumbs, UI images).
        """
        reasons: dict[str, int] = {}

        def reject(reason: str) -> None:
            reasons[reason] = reasons.get(reason, 0) + 1

        page_host = (urlparse(page_url).hostname or "").lower()
        min_side = int(settings.PLAYWRIGHT_MIN_IMAGE_SIDE_PX)

        # Normalize + upgrade + score
        candidates: list[_ScoredUrl] = []
        seen_norm: set[str] = set()

        for raw in urls:
            if not isinstance(raw, str):
                reject("non_string")
                continue
            u0 = raw.strip()
            if not u0:
                reject("empty")
                continue

            u1 = _normalize_url(u0)
            if not u1:
                reject("normalize_failed")
                continue

            u2 = _upgrade_cdn_url(u1)

            norm = _dedupe_key(u2)
            if norm in seen_norm:
                reject("duplicate")
                continue
            seen_norm.add(norm)

            ok, reason = _passes_url_rules(u2, page_host=page_host)
            if not ok:
                reject(reason)
                continue

            inferred = _infer_size_from_url(u2)
            if inferred is not None:
                w, h = inferred
                if w < min_side or h < min_side:
                    reject("too_small")
                    continue

            if not _is_candidate_image_url(u2):
                reject("not_image")
                continue

            score = _score_url(u2, page_host=page_host)
            candidates.append(_ScoredUrl(score=score, url=u2))

        candidates.sort(key=lambda s: s.score, reverse=True)
        best = [c.url for c in candidates[: max(1, limit)]]
        filtered_out = max(0, len(urls) - len(best))

        logger.info(
            "Playwright select url=%s raw=%d selected=%d rejected=%d reasons=%s",
            page_url,
            len(urls),
            len(best),
            len(urls) - len(best),
            {k: reasons[k] for k in sorted(reasons.keys())[:10]},
        )
        return self._SelectionResult(urls=best, filtered_out=(len(urls) - len(best)), rejected_reasons=reasons)


@dataclass(frozen=True)
class _ScoredUrl:
    score: float
    url: str


_REJECT_SUBSTRINGS = [
    "error",
    "placeholder",
    "logo",
    "icon",
    "sprite",
    "avatar",
    "profile",
    "ads",
    "banner",
]


def _passes_url_rules(url: str, *, page_host: str) -> tuple[bool, str]:
    u = url.lower()
    # global rejects
    for s in _REJECT_SUBSTRINGS:
        if s in u:
            return False, f"keyword:{s}"

    host = (urlparse(url).hostname or "").lower()
    # Freepik safety: drop common assets
    if "cdnpk.net" in host and "/common/" in u:
        return False, "freepik_common"

    return True, "ok"


def _upgrade_cdn_url(url: str) -> str:
    """Platform-specific URL upgrades (prefer higher-res variants)."""
    host = (urlparse(url).hostname or "").lower()
    u = url
    # Pinterest: /236x/ -> /originals/
    if host.endswith("pinimg.com"):
        u = re.sub(r"/\d{2,4}x\d{2,4}/", "/originals/", u)
        u = re.sub(r"/\d{2,4}x/", "/originals/", u)
    return u


def _infer_size_from_url(url: str) -> Optional[tuple[int, int]]:
    u = url.lower()
    m = re.search(r"(?:/|=)(\d{2,4})x(\d{2,4})(?:/|\b)", u)
    if m:
        try:
            return int(m.group(1)), int(m.group(2))
        except Exception:
            return None
    return None


def _score_url(url: str, *, page_host: str) -> float:
    """
    Priority scoring:
    + domain trust
    + resolution hints
    + quality keywords
    """
    host = (urlparse(url).hostname or "").lower()
    u = url.lower()
    score = 0.0

    # domain trust
    if host.endswith("pinimg.com") or "pinterest" in page_host:
        score += 2.0
    if "freepik.com" in page_host or host.endswith("freepik.com") or host.endswith("cdnpk.net"):
        score += 1.0

    # quality keywords
    if "originals" in u:
        score += 2.0
    if any(k in u for k in ("hd", "large", "full", "highres")):
        score += 0.5

    # Freepik: prioritize real content paths
    if any(seg in u for seg in ("/premium-photo/", "/free-photo/", "/vector/")):
        score += 1.5

    # resolution hints
    inferred = _infer_size_from_url(url)
    if inferred:
        w, h = inferred
        score += min(3.0, (min(w, h) / 600.0))

    return score


def _dedupe_key(url: str) -> str:
    """Normalize URL for dedupe: scheme/host/path + stable query params."""
    try:
        p = urlparse(url)
        qs = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)]
        # drop common trackers
        drop = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}
        qs2 = [(k, v) for (k, v) in qs if k.lower() not in drop]
        qs2.sort()
        new_q = urlencode(qs2, doseq=True)
        return urlunparse((p.scheme, p.netloc.lower(), p.path, "", new_q, ""))
    except Exception:
        return url


def _normalize_url(url: str) -> str:
    x = url.strip()
    if x.startswith("//"):
        x = "https:" + x
    return x


def _is_candidate_image_url(url: str) -> bool:
    u = url.lower()
    if not u.startswith(("http://", "https://")):
        return False
    if "data:image" in u or "base64," in u:
        return False
    if any(ext in u for ext in (".svg", ".ico")):
        return False
    if not re.search(r"\.(jpg|jpeg|png|webp|bmp)(\?|$)", u):
        # allow extensionless CDN urls if clearly image-ish
        if "image" not in u and "img" not in u and "photo" not in u:
            return False
    return True

