"""
GMaps Scraper CLI — Desktop App Mode
=====================================
Jalan di komputer user, pakai IP residential asli.
Dipanggil Flutter Desktop App via Process.run().

Usage:
  python scraper.py --keyword "tour surabaya" --max-scrolls 10 \
      --fields "nama_usaha,nomor_hp,alamat,website" --output result.csv

Progress diprint ke stdout dengan prefix "PROGRESS:" untuk Flutter parsing.
"""

import argparse
import asyncio as aio
import csv
import json
import os
import random
import sys
import time as time_mod
from datetime import datetime

from playwright.async_api import async_playwright

# ── Anti-Detection: User-Agent Pool ────────────────────────────────

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

STEALTH_SCRIPT = """
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
    window.chrome = {runtime: {}};
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({state: Notification.permission}) :
        originalQuery(parameters)
    );
    Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
    Object.defineProperty(navigator, 'languages', {get: () => ['id-ID', 'id', 'en-US', 'en']});
"""

# Blocked resource types (hemat bandwidth)
BLOCKED_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".css", ".woff", ".woff2", ".ttf", ".eot", ".mp4", ".mp3",
    ".webm", ".avif",
)
BLOCKED_DOMAINS = (
    "google-analytics", "googletagmanager", "doubleclick",
    "googleadservices", "adservice",
)


async def resource_blocker(route):
    """Block unnecessary resources to save bandwidth."""
    url = route.request.url.lower()
    # Block by extension
    if any(url.endswith(ext) for ext in BLOCKED_EXTENSIONS):
        await route.abort()
        return
    # Block by domain
    if any(domain in url for domain in BLOCKED_DOMAINS):
        await route.abort()
        return
    await route.continue_()


from city_coords import detect_location, DEFAULT_COORDS


# ── DOM Extraction ──────────────────────────────────────────────────

async def extract_business_info(page) -> dict:
    """Ekstrak nama, HP, alamat, website dari halaman detail GMaps."""
    data = await page.evaluate("""
        () => {
            const result = {nama_usaha: '', nomor_hp: '', alamat: '', website: ''};
            const h1 = document.querySelector('h1');
            if (h1) {
                let name = h1.textContent.trim();
                name = name.replace(/[★☆\\d.]+\\s*\\(?\\d+[\\.\\,]?\\d*\\s*ribu?\\s*ulasan?\\)?.*$/i, '').trim();
                result.nama_usaha = name;
            }
            if (!result.nama_usaha) {
                result.nama_usaha = document.title.replace(/ - Google Maps.*$/, '').trim();
            }

            const buttons = [...document.querySelectorAll('button')];
            const phoneRegex = /(\\+?62|0)[\\s\\-.]?\\d{2,4}[\\s\\-.]?\\d{3,4}[\\s\\-.]?\\d{3,4}/;
            const generalPhone = /[\\d\\s\\-\\+\\(\\)\\.]{7,20}/;
            const webRegex = /https?:\\/\\/[^\\s]+/;
            const domainRegex = /[\\w\\-]+\\.(com|co\\.id|id|net|org|biz|io|store|site|online|web\\.id|my\\.id)(\\/[^\\s]*)?/i;

            for (const btn of buttons) {
                const text = (btn.textContent || '').trim();
                const aria = (btn.getAttribute('aria-label') || '').trim();
                const combined = text + ' ' + aria;

                if (!result.nomor_hp) {
                    let m = combined.match(phoneRegex) || combined.match(generalPhone);
                    if (m) {
                        let phone = m[0].trim().replace(/\\s+/g, ' ');
                        if (phone.replace(/[^\\d]/g, '').length >= 8) result.nomor_hp = phone;
                    }
                }
                if (!result.website) {
                    let m = combined.match(webRegex) || combined.match(domainRegex);
                    if (m) result.website = m[0].trim();
                    const link = btn.querySelector('a[href*="http"]');
                    if (link && !result.website) result.website = link.href;
                }
            }

            if (!result.nomor_hp || !result.website) {
                const allText = document.body.innerText;
                if (!result.nomor_hp) { const m = allText.match(phoneRegex); if (m) result.nomor_hp = m[0].trim(); }
                if (!result.website) { const m = allText.match(webRegex); if (m) result.website = m[0].trim(); }
            }

            let bestAddr = '';
            for (const btn of buttons) {
                const text = (btn.textContent || '').trim();
                const aria = (btn.getAttribute('aria-label') || '').trim();
                const candidate = aria || text;
                if (candidate.length < 8) continue;
                if (/^(telp|telepon|phone|call|website|buka|tutup|simpan|bagikan|kirim|rute|arahkan)/i.test(candidate)) continue;
                if (phoneRegex.test(candidate) || webRegex.test(candidate)) continue;
                if (candidate === result.nama_usaha) continue;
                if (candidate.includes(',') || /J(l|alan)\\b/i.test(candidate) || candidate.length > 20) {
                    if (candidate.length > bestAddr.length) bestAddr = candidate;
                }
            }
            if (bestAddr && !result.alamat) result.alamat = bestAddr;

            if (!result.alamat) {
                const addrEl = document.querySelector('[data-tooltip*="alamat"], [data-tooltip*="address"], [aria-label*="alamat"], [aria-label*="address"]');
                if (addrEl) result.alamat = (addrEl.getAttribute('aria-label') || addrEl.textContent || '').trim();
            }
            return result;
        }
    """)
    return data


# ── Main Scraping Logic ─────────────────────────────────────────────

async def scrape(keyword: str, max_scrolls: int = 10,
                 lat: float = None, lng: float = None,
                 fields: list[str] = None) -> list[dict]:
    """Scrape Google Maps — return list of business results."""
    if fields is None:
        fields = ["nama_usaha", "nomor_hp", "alamat", "website"]

    city_name = keyword
    if lat is None or lng is None:
        lat, lng = detect_location(keyword)
        # Find city name for progress
        for c, coord in [("Jakarta", DEFAULT_COORDS)]:
            pass
    else:
        city_name = f"{lat:.2f},{lng:.2f}"

    url = f"https://www.google.com/maps/search/{keyword.replace(' ', '+')}/@{lat},{lng},12z"

    print(f"PROGRESS:0:Mulai scraping \"{keyword}\"...")
    results: list[dict] = []

    async with async_playwright() as p:
        # Browser launch — HEADLESS mode
        print(f"PROGRESS:2:Meluncurkan browser...")
        browser = await p.chromium.launch(
            headless=True,  # HEADLESS — tanpa browser UI
            timeout=120000,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage", "--no-sandbox",
                "--disable-infobars", "--disable-setuid-sandbox",
                "--no-first-run", "--no-default-browser-check",
                "--ignore-certificate-errors",
                "--disable-gpu",
            ]
        )

        random_ua = random.choice(USER_AGENTS)

        context = await browser.new_context(
            viewport={"width": random.randint(1280, 1440), "height": random.randint(800, 960)},
            locale="id-ID", timezone_id="Asia/Jakarta",
            user_agent=random_ua,
            permissions=["geolocation"],
            geolocation={"latitude": lat, "longitude": lng},
            extra_http_headers={
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "DNT": "1", "Upgrade-Insecure-Requests": "1",
            },
        )

        page = await context.new_page()
        await page.add_init_script(STEALTH_SCRIPT)

        # ═══ Resource Blocking ═══
        await page.route("**/*", resource_blocker)
        print(f"PROGRESS:5:Resource blocking aktif — hemat bandwidth")

        # ═══ PHASE 1: Search + Scroll ═══

        print(f"PROGRESS:10:Membuka Google Maps...")
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
        except Exception:
            fallback = f"https://www.google.com/maps/search/{keyword.replace(' ', '+')}"
            await page.goto(fallback, wait_until="domcontentloaded", timeout=120000)

        await page.wait_for_timeout(random.randint(1500, 3500))

        try:
            await page.wait_for_selector('[role="feed"]', timeout=20000)
        except Exception:
            pass

        await page.wait_for_timeout(random.randint(2000, 4000))
        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(random.randint(400, 800))
        except Exception:
            pass

        # ── Scroll Feed ──
        scroll_start = time_mod.time()
        SCROLL_TIMEOUT = 300
        limit = max(max_scrolls, 3)
        last_card_count = 0
        stuck_card_count = 0
        bottom_hit_count = 0
        MAX_STUCK = 3
        total_phases = 60  # Phase 1 is first 60% of progress

        for i in range(limit):
            elapsed = time_mod.time() - scroll_start
            if elapsed > SCROLL_TIMEOUT:
                print(f"PROGRESS:55:Timeout scroll ({SCROLL_TIMEOUT}s)")
                break

            scroll_ratio = random.uniform(0.7, 0.95)
            info = await page.evaluate(f"""
                () => {{
                    const feed = document.querySelector('[role="feed"]');
                    if (!feed) return {{scrolled: false, top: 0, count: 0, atBottom: false, scrollHeight: 0}};
                    const prevTop = feed.scrollTop;
                    feed.scrollBy(0, feed.clientHeight * {scroll_ratio});
                    const cards = feed.querySelectorAll('[role="article"]');
                    const atBottom = (feed.scrollTop + feed.clientHeight) >= (feed.scrollHeight - 25);
                    return {{scrolled: feed.scrollTop > (prevTop + 5), top: feed.scrollTop, count: cards.length, atBottom, scrollHeight: feed.scrollHeight}};
                }}
            """)
            await page.wait_for_timeout(int(random.uniform(3.0, 4.5) * 1000))

            count = info.get("count", 0)
            at_bottom = info.get("atBottom", False)
            progress = int(10 + (i / limit) * total_phases)
            print(f"PROGRESS:{progress}:Scroll {i+1}/{limit} — {count} kartu ditemukan")

            if at_bottom:
                bottom_hit_count += 1
                if bottom_hit_count <= 3:
                    await page.wait_for_timeout(random.randint(5000, 8000))
                    await page.evaluate("""() => { const feed = document.querySelector('[role="feed"]'); if (feed) feed.scrollTop = feed.scrollHeight; }""")
                    await page.wait_for_timeout(random.randint(2500, 4000))
                    recheck = await page.evaluate("""() => { const feed = document.querySelector('[role="feed"]'); if (!feed) return {count:0}; return {count: feed.querySelectorAll('[role="article"]').length, h: feed.scrollHeight}; }""")
                    if recheck.get("count", count) > count:
                        bottom_hit_count = 0; last_card_count = recheck["count"]; stuck_card_count = 0
                    continue
                else:
                    print(f"PROGRESS:{progress}:Mentok — stop scroll")
                    break

            if not at_bottom:
                bottom_hit_count = 0
            if count != last_card_count:
                stuck_card_count = 0; last_card_count = count
            if i + 1 >= 3 and count == last_card_count:
                stuck_card_count += 1
                if stuck_card_count >= MAX_STUCK:
                    print(f"PROGRESS:{progress}:Kartu stuck — stop")
                    break

        await page.wait_for_timeout(random.randint(4000, 7000))

        # ── Kumpulkan link ──
        print(f"PROGRESS:70:Mengumpulkan link...")
        place_urls: list[str] = await page.evaluate("""
            () => {
                const urls = new Set();
                const cards = document.querySelectorAll('[role="feed"] [role="article"]');
                cards.forEach(card => {
                    card.querySelectorAll('a[href*="/place/"]').forEach(a => {
                        if (a.href && a.href.includes('/place/')) urls.add(a.href);
                    });
                });
                if (urls.size < 3) {
                    document.querySelectorAll('a[href*="/place/"]').forEach(a => {
                        if (a.href && a.href.includes('/place/') && !a.href.includes('/search/')) urls.add(a.href);
                    });
                }
                return [...urls];
            }
        """)
        card_count = await page.evaluate("document.querySelectorAll('[role=\"feed\"] [role=\"article\"]').length")
        print(f"PROGRESS:75:{card_count} kartu, {len(place_urls)} link /place/ ditemukan")
        await page.close()

        # ═══ PHASE 2: Extract detail ═══
        CONCURRENCY = 4
        semaphore = aio.Semaphore(CONCURRENCY)
        total = len(place_urls)
        results = [{}] * total
        done_count = 0

        async def process_one(idx: int, biz_url: str):
            nonlocal done_count
            async with semaphore:
                try:
                    jitter = random.uniform(1.5, 4.0)
                    await aio.sleep(idx * random.uniform(0.3, 1.0) + jitter)
                    biz_page = await context.new_page()
                    await biz_page.route("**/*", resource_blocker)
                    try:
                        await biz_page.goto(biz_url, wait_until="domcontentloaded", timeout=30000)
                        await biz_page.wait_for_timeout(random.randint(2000, 4000))
                        try:
                            await biz_page.keyboard.press("Escape")
                            await biz_page.wait_for_timeout(random.randint(200, 500))
                        except Exception:
                            pass
                        info = await extract_business_info(biz_page)
                        results[idx] = info
                        done_count += 1
                        name = info.get("nama_usaha", "?")[:25]
                        prog_pct = 75 + int((done_count / total) * 20)
                        print(f"PROGRESS:{prog_pct}:[{done_count}/{total}] {name}")
                    finally:
                        await biz_page.close()
                except Exception as e:
                    results[idx] = {"nama_usaha": "", "nomor_hp": "", "alamat": "", "website": ""}
                    done_count += 1
                    prog_pct = 75 + int((done_count / total) * 20)
                    print(f"PROGRESS:{prog_pct}:[{done_count}/{total}] Gagal: {e}")

        tasks = [process_one(i, url) for i, url in enumerate(place_urls)]
        await aio.gather(*tasks)

        results = [r if r else {"nama_usaha": "", "nomor_hp": "", "alamat": "", "website": ""} for r in results]
        await browser.close()

    # ── Filter fields ──
    if set(fields) != {"nama_usaha", "nomor_hp", "alamat", "website"}:
        results = [{k: v for k, v in row.items() if k in fields} for row in results]

    print(f"PROGRESS:100:Selesai — {len(results)} hasil")
    return results


# ── Output Helpers ───────────────────────────────────────────────────

def save_json(results: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def save_csv(results: list[dict], path: str):
    if not results:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("")
        return
    keys = list(results[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)


# ── CLI Entry Point ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GMaps Scraper CLI — ekstrak data bisnis dari Google Maps"
    )
    parser.add_argument("--keyword", "-k", required=True, help="Kata kunci pencarian")
    parser.add_argument("--max-scrolls", "-s", type=int, default=10, help="Jumlah scroll (default: 10)")
    parser.add_argument("--fields", "-f", default="nama_usaha,nomor_hp,alamat,website",
                        help="Field yang diekstrak, comma-separated (default: nama_usaha,nomor_hp,alamat,website)")
    parser.add_argument("--output", "-o", required=True, help="File output (.csv atau .json)")
    parser.add_argument("--lat", type=float, default=None, help="Latitude manual")
    parser.add_argument("--lng", type=float, default=None, help="Longitude manual")

    args = parser.parse_args()

    fields = [f.strip() for f in args.fields.split(",") if f.strip()]
    lat, lng = args.lat, args.lng
    if lat is None or lng is None:
        lat, lng = detect_location(args.keyword)

    print(f"PROGRESS:0:GMaps Scraper CLI — {args.keyword}")
    print(f"PROGRESS:1:Max scroll: {args.max_scrolls} | Fields: {args.fields}")

    results = aio.run(scrape(args.keyword, args.max_scrolls, lat, lng, fields))

    output = args.output
    if output.endswith(".json"):
        save_json(results, output)
    else:
        if not output.endswith(".csv"):
            output += ".csv"
        save_csv(results, output)

    print(f"RESULT:{output}:{len(results)}")

    # Print summary ke stdout
    for i, r in enumerate(results):
        if r.get("nama_usaha"):
            print(f"DATA:{i}:{r.get('nama_usaha','')}|{r.get('nomor_hp','')}|{r.get('alamat','')}|{r.get('website','')}")


if __name__ == "__main__":
    main()
