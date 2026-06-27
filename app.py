"""
Web App: Google Maps Scraper — DOM Extraction (No AI, No Token)
================================================================
Backend: FastAPI + Playwright

Alur:
 1. Playwright buka Google Maps dengan keyword
 2. Scroll hasil pencarian, kumpulkan link tiap usaha
 3. Buka tiap link di tab baru → ekstrak data dari DOM langsung
 4. Return hasil JSON ke frontend
"""

import uuid
import random
import time as time_mod
import asyncio as aio
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from playwright.async_api import async_playwright

# ── Setup ────────────────────────────────────────────────────────────

app = FastAPI(title="GMaps Scraper AI")

BASE_DIR = Path(__file__).parent

# Static
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ── Global Rate Limiter (anti banyak user serentak) ───────────────
# Max 2 scrape jalan bersamaan. Masing-masing punya browser instance
# sendiri dengan fingerprint unik → Google Maps lihat sebagai user berbeda.
# Cooldown 5 detik antar scrape selesai → cegah burst request.
SCRAPE_LOCK = aio.Semaphore(2)          # max 2 concurrent scrape
COOLDOWN_SECONDS = 5                    # jeda minimal antar scrape (detik)
_last_scrape_time = 0.0                 # timestamp scrape terakhir


# ── Anti-Detection: Random User-Agent Pool ────────────────────────
USER_AGENTS = [
    # Chrome Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    # Chrome Mac
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    # Edge Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    # Firefox Windows
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

# ── Anti-Detection: Browser Launch Args ───────────────────────────
BROWSER_ARGS = [
    "--disable-blink-features=AutomationControlled",  # Sembunyikan automation flag
    "--disable-dev-shm-usage",                         # Hindari crash di container/VPS
    "--no-sandbox",                                    # Required di Docker container
    "--disable-infobars",                              # Hilangkan info bar Chrome
    "--disable-setuid-sandbox",                        # Kompatibilitas sandbox
    "--no-first-run",
    "--no-default-browser-check",
    "--ignore-certificate-errors",
    "--window-size=1366,768",
]

async def extract_business_info(page) -> dict:
    """
    Ekstrak nama usaha, nomor HP, alamat, website dari halaman detail Google Maps.
    Multi-strategy: structured DOM → regex fallback → full text scan.
    """
    data = await page.evaluate("""
        () => {
            const result = {nama_usaha: '', nomor_hp: '', alamat: '', website: ''};

            // ── 1. Nama usaha: h1 paling akurat ──────────────────
            const h1 = document.querySelector('h1');
            if (h1) {
                let name = h1.textContent.trim();
                // Hapus teks rating/review yang kadang nempel
                name = name.replace(/[★☆\\d.]+\\s*\\(?\\d+[\\.\\,]?\\d*\\s*ribu?\\s*ulasan?\\)?.*$/i, '').trim();
                result.nama_usaha = name;
            }
            if (!result.nama_usaha) {
                result.nama_usaha = document.title.replace(/ - Google Maps.*$/, '').trim();
            }

            // ── 2. Kumpulkan semua tombol di panel info ──────────
            const buttons = [...document.querySelectorAll('button')];
            const phoneRegex = /(\\+?62|0)[\\s\\-.]?\\d{2,4}[\\s\\-.]?\\d{3,4}[\\s\\-.]?\\d{3,4}/;
            const generalPhone = /[\\d\\s\\-\\+\\(\\)\\.]{7,20}/;
            const webRegex = /https?:\\/\\/[^\\s]+/;
            const domainRegex = /[\\w\\-]+\\.(com|co\\.id|id|net|org|biz|io|store|site|online|web\\.id|my\\.id)(\\/[^\\s]*)?/i;

            for (const btn of buttons) {
                const text = (btn.textContent || '').trim();
                const aria = (btn.getAttribute('aria-label') || '').trim();
                const combined = text + ' ' + aria;

                // ── Phone ─────────────────────────────────────────
                if (!result.nomor_hp) {
                    let m = combined.match(phoneRegex) || combined.match(generalPhone);
                    if (m) {
                        let phone = m[0].trim().replace(/\\s+/g, ' ');
                        // Minimal 8 digit angka
                        if (phone.replace(/[^\\d]/g, '').length >= 8) {
                            result.nomor_hp = phone;
                        }
                    }
                }

                // ── Website ───────────────────────────────────────
                if (!result.website) {
                    // Cari di text, aria-label, dan href child
                    let m = combined.match(webRegex) || combined.match(domainRegex);
                    if (m) {
                        result.website = m[0].trim();
                    }
                    // Coba dari link child
                    const link = btn.querySelector('a[href*="http"]');
                    if (link && !result.website) {
                        result.website = link.href;
                    }
                }
            }

            // ── 3. Fallback: scan seluruh teks halaman ────────────
            if (!result.nomor_hp || !result.website) {
                const allText = document.body.innerText;

                if (!result.nomor_hp) {
                    const m = allText.match(phoneRegex);
                    if (m) result.nomor_hp = m[0].trim();
                }
                if (!result.website) {
                    const m = allText.match(webRegex);
                    if (m) result.website = m[0].trim();
                }
            }

            // ── 4. Alamat: cari teks terpanjang bernada alamat ────
            // Google Maps tempatkan alamat di button dengan teks multi-baris
            let bestAddr = '';
            for (const btn of buttons) {
                const text = (btn.textContent || '').trim();
                const aria = (btn.getAttribute('aria-label') || '').trim();
                const candidate = aria || text;

                // Skip kalau terlalu pendek atau mengandung pola non-alamat
                if (candidate.length < 8) continue;
                if (/^(telp|telepon|phone|call|website|buka|tutup|simpan|bagikan|kirim|rute|arahkan)/i.test(candidate)) continue;
                if (phoneRegex.test(candidate) || webRegex.test(candidate)) continue;
                if (candidate === result.nama_usaha) continue;

                // Alamat biasanya ada koma, kata "Jl", "Jalan", atau panjang >20 karakter
                if (candidate.includes(',') || /J(l|alan)\\b/i.test(candidate) || candidate.length > 20) {
                    if (candidate.length > bestAddr.length) {
                        bestAddr = candidate;
                    }
                }
            }
            if (bestAddr && !result.alamat) {
                result.alamat = bestAddr;
            }

            // ── 5. Fallback alamat: elemen dengan data attribute ──
            if (!result.alamat) {
                const addrEl = document.querySelector('[data-tooltip*="alamat"], [data-tooltip*="address"], [aria-label*="alamat"], [aria-label*="address"]');
                if (addrEl) {
                    result.alamat = (addrEl.getAttribute('aria-label') || addrEl.textContent || '').trim();
                }
            }

            return result;
        }
    """)
    return data


async def scrape_businesses_from_gmaps(keyword: str,
                                        max_scrolls: int = 10,
                                        lat: float = None, lng: float = None,
                                        proxy: str = None) -> list[dict]:
    """
    Phase 1: Buka Google Maps, cari keyword, scroll feed, kumpulkan link tiap usaha.
    Phase 2: Buka tiap link di tab baru → ekstrak data dari DOM langsung.
    Return list of dict {nama_usaha, nomor_hp, alamat, website}.
    """
    results: list[dict] = []

    if lat is not None and lng is not None:
        url = f"https://www.google.com/maps/search/{keyword.replace(' ', '+')}/@{lat},{lng},12z"
    else:
        url = f"https://www.google.com/maps/search/{keyword.replace(' ', '+')}"

    async with async_playwright() as p:
        # ── Anti-Detection: Browser launch dengan arg khusus ────
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-setuid-sandbox",
                "--no-first-run",
                "--no-default-browser-check",
                "--ignore-certificate-errors",
            ]
        )

        # ── Random User-Agent ────────────────────────────────────
        random_ua = random.choice(USER_AGENTS)
        if proxy:
            print(f"   🏠  Proxy user: {proxy[:50]}...")
        print(f"   🕵️  UA: {random_ua[:60]}...")

        context_kwargs = {
            "viewport": {"width": random.randint(1280, 1440), "height": random.randint(800, 960)},
            "locale": "id-ID",
            "timezone_id": "Asia/Jakarta",
            "user_agent": random_ua,
            "permissions": ["geolocation"],
            "extra_http_headers": {
                "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
                "Upgrade-Insecure-Requests": "1",
            },
        }
        if lat is not None and lng is not None:
            context_kwargs["geolocation"] = {"latitude": lat, "longitude": lng}

        # ── Proxy: user bawa IP sendiri ─────────────────────────
        if proxy:
            context_kwargs["proxy"] = {"server": proxy}

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        # ── Anti-Detection: Inject stealth scripts ──────────────
        await page.add_init_script("""
            // Overwrite navigator.webdriver agar tidak terdeteksi automation
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            // Overwrite chrome object
            window.chrome = {runtime: {}};
            // Overwrite permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                originalQuery(parameters)
            );
            // Overwrite plugins length
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            // Overwrite languages
            Object.defineProperty(navigator, 'languages', {get: () => ['id-ID', 'id', 'en-US', 'en']});
        """)

        # ═══════════════════════════════════════════════════════════
        # PHASE 1: Buka hasil pencarian → scroll → kumpulkan link
        # ═══════════════════════════════════════════════════════════

        async def try_goto(target_url: str, label: str) -> bool:
            try:
                await page.goto(target_url, wait_until="domcontentloaded", timeout=120000)
                print(f"   ✅ Halaman Maps terbuka ({label})")
                return True
            except Exception as e:
                print(f"   ⚠  Gagal buka ({label}): {e}")
                return False

        # Coba URL dengan koordinat dulu
        ok = await try_goto(url, "dgn koordinat")
        if not ok:
            # Fallback: URL tanpa koordinat
            fallback_url = f"https://www.google.com/maps/search/{keyword.replace(' ', '+')}"
            ok = await try_goto(fallback_url, "tanpa koordinat")
            if not ok:
                raise Exception("Gagal membuka Google Maps — timeout / koneksi")

        # ── Random initial delay (simulasi user mikir) ──────────
        await page.wait_for_timeout(random.randint(1500, 3500))

        try:
            await page.wait_for_selector('[role="feed"]', timeout=20000)
            print(f"   ✅ Hasil pencarian muncul")
        except:
            print(f"   ⚠  Feed tidak ditemukan, lanjut")

        # ── Random settle time ───────────────────────────────────
        await page.wait_for_timeout(random.randint(2000, 4000))

        try:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(random.randint(400, 800))
        except:
            pass

        # Scroll — handling batch loading Google Maps
        scroll_start = time_mod.time()
        SCROLL_TIMEOUT = 300  # max total detik (5 menit)
        limit = max_scrolls
        last_card_count = 0
        stuck_card_count = 0
        last_scroll_top = -1
        stuck_scroll_count = 0
        last_scroll_height = 0
        fake_growth_count = 0
        bottom_hit_count = 0      # berapa kali mentok berturut
        MAX_STUCK = 3             # 3x stuck baru stop
        MIN_SCROLLS_BEFORE_STOP = 3
        SCROLL_WAIT = random.uniform(3.0, 4.5)  # detik tunggu setelah scroll (random)

        for i in range(limit):
            # ⏱ Timeout total
            elapsed = time_mod.time() - scroll_start
            if elapsed > SCROLL_TIMEOUT:
                print(f"   🛑  Stop: timeout {SCROLL_TIMEOUT}s")
                break

            # ── Scroll ───────────────────────────────────────────
            scroll_ratio = random.uniform(0.7, 0.95)  # random scroll amount
            info = await page.evaluate(f"""
                () => {{
                    const feed = document.querySelector('[role="feed"]');
                    if (!feed) return {{scrolled: false, top: 0, count: 0, atBottom: false, scrollHeight: 0}};
                    const prevTop = feed.scrollTop;
                    feed.scrollBy(0, feed.clientHeight * {scroll_ratio});
                    const cards = feed.querySelectorAll('[role="article"]');
                    const atBottom = (feed.scrollTop + feed.clientHeight) >= (feed.scrollHeight - 25);
                    return {{
                        scrolled: feed.scrollTop > (prevTop + 5),
                        top: feed.scrollTop,
                        count: cards.length,
                        atBottom: atBottom,
                        scrollHeight: feed.scrollHeight
                    }};
                }}
            """)
            await page.wait_for_timeout(int(SCROLL_WAIT * 1000))

            top = info.get("top", 0)
            count = info.get("count", 0)
            at_bottom = info.get("atBottom", False)
            cur_scroll_height = info.get("scrollHeight", 0)
            total_label = f"/{limit}" if limit > 0 else "/demo"
            print(f"   📜 Scroll {i+1}{total_label} → pos={top}px, {count} kartu, mentok={'YA' if at_bottom else 'tidak'}, h={cur_scroll_height}px")

            # ── Handle MENTOK: jangan stop, kasih kesempatan load batch berikutnya ──
            if at_bottom:
                bottom_hit_count += 1
                if bottom_hit_count <= 3:
                    prev_h = cur_scroll_height
                    print(f"      🔄  Mentok #{bottom_hit_count}: tunggu, trigger batch berikutnya...")
                    await page.wait_for_timeout(random.randint(5000, 8000))
                    # Scroll paksa ke paling ujung biar trigger lazy load
                    new_h = await page.evaluate("""
                        () => {
                            const feed = document.querySelector('[role="feed"]');
                            if (!feed) return 0;
                            feed.scrollTop = feed.scrollHeight;
                            return feed.scrollHeight;
                        }
                    """)
                    await page.wait_for_timeout(random.randint(2500, 4000))
                    # Cek ulang
                    recheck = await page.evaluate("""
                        () => {
                            const feed = document.querySelector('[role="feed"]');
                            if (!feed) return {count: 0, h: 0};
                            return {
                                count: feed.querySelectorAll('[role="article"]').length,
                                h: feed.scrollHeight
                            };
                        }
                    """)
                    new_count = recheck.get("count", count)
                    new_h2 = recheck.get("h", cur_scroll_height)
                    print(f"      📊  Setelah trigger: {new_count} kartu, h={new_h2}px (sebelumnya {count} kartu, h={cur_scroll_height}px)")

                    if new_count > count or new_h2 > cur_scroll_height + 50:
                        # Ada batch baru! Reset tracker & lanjut
                        print(f"      ✅  Batch baru terdeteksi! Lanjut scroll...")
                        bottom_hit_count = 0
                        last_card_count = new_count
                        stuck_card_count = 0
                        fake_growth_count = 0
                        last_scroll_height = new_h2
                        last_scroll_top = top
                        stuck_scroll_count = 0
                        continue
                    # Kalau tidak ada perubahan, tetap lanjut iterasi (jangan break!)
                    continue
                else:
                    print(f"   🛑  Stop: mentok {bottom_hit_count}x berturut tanpa batch baru")
                    break

            # Reset bottom counter kalau tidak mentok
            if not at_bottom:
                bottom_hit_count = 0

            # Update tracker
            if count != last_card_count:
                stuck_card_count = 0
                last_card_count = count
                fake_growth_count = 0

            if cur_scroll_height > last_scroll_height + 20 and count == last_card_count:
                fake_growth_count += 1
            else:
                fake_growth_count = 0
            last_scroll_height = cur_scroll_height

            if info.get("scrolled"):
                stuck_scroll_count = 0
                last_scroll_top = top
            else:
                if abs(top - last_scroll_top) < 10:
                    stuck_scroll_count += 1
                else:
                    stuck_scroll_count = 0
                last_scroll_top = top

            # ── Stopper hanya aktif setelah MIN scroll awal ──────
            if i + 1 < MIN_SCROLLS_BEFORE_STOP:
                continue

            # ── Stopper #2: kartu stuck ─────────────────────────
            if count == last_card_count:
                stuck_card_count += 1
                if stuck_card_count >= MAX_STUCK:
                    print(f"   🛑  Stop: kartu stuck di {count} ({MAX_STUCK}x)")
                    break

            # ── Stopper #3: posisi scroll stuck ─────────────────
            if stuck_scroll_count >= MAX_STUCK:
                print(f"   🛑  Stop: posisi scroll stuck di {top}px")
                break

            # ── Stopper #4: loading skeleton ────────────────────
            if fake_growth_count >= 6:
                print(f"   🛑  Stop: scrollHeight naik terus tanpa kartu baru (skeleton)")
                break

        # ── Final settle: random delay ──
        settle_time = random.randint(4000, 7000)
        print(f"   ⏳  Final settle: tunggu {settle_time/1000:.1f} detik...")
        await page.wait_for_timeout(settle_time)

        # Kumpulkan link — multi-strategy
        place_urls: list[str] = await page.evaluate("""
            () => {
                const urls = new Set();

                // Strategy 1: cards di dalam feed dgn role="article"
                const cards = document.querySelectorAll('[role="feed"] [role="article"]');
                cards.forEach(card => {
                    const links = card.querySelectorAll('a[href*="/place/"]');
                    links.forEach(a => {
                        if (a.href && a.href.includes('/place/')) {
                            urls.add(a.href);
                        }
                    });
                });

                // Strategy 2: fallback — semua link /place/ di halaman
                if (urls.size < 3) {
                    const allLinks = document.querySelectorAll('a[href*="/place/"]');
                    allLinks.forEach(a => {
                        if (a.href && a.href.includes('/place/') && !a.href.includes('/search/')) {
                            urls.add(a.href);
                        }
                    });
                }

                return [...urls];
            }
        """)

        card_count = await page.evaluate("document.querySelectorAll('[role=\"feed\"] [role=\"article\"]').length")
        print(f"   📊 {card_count} kartu di feed → 🔗 {len(place_urls)} link /place/ ditemukan")

        await page.close()

        # ═══════════════════════════════════════════════════════════
        # PHASE 2: Buka tab paralel → ekstrak DOM sekaligus
        # ═══════════════════════════════════════════════════════════

        CONCURRENCY = 4  # jumlah tab paralel (rendah = lebih aman)
        semaphore = aio.Semaphore(CONCURRENCY)
        total = len(place_urls)
        done_count = 0
        delay_lock = aio.Lock()  # biar delay per tab berurutan

        # Pre-allocate results list biar urutan tetap
        results = [{}] * total

        async def process_one(idx: int, url: str):
            nonlocal done_count
            async with semaphore:
                try:
                    # ── Random delay antar tab (anti rate-limit) ──
                    jitter = random.uniform(1.5, 4.0)
                    await aio.sleep(idx * random.uniform(0.3, 1.0) + jitter)

                    biz_page = await context.new_page()
                    try:
                        await biz_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        # Random wait setelah load
                        await biz_page.wait_for_timeout(random.randint(2000, 4000))

                        try:
                            await biz_page.keyboard.press("Escape")
                            await biz_page.wait_for_timeout(random.randint(200, 500))
                        except:
                            pass

                        info = await extract_business_info(biz_page)
                        results[idx] = info
                        done_count += 1
                        print(f"   ✅ [{done_count}/{total}] {info.get('nama_usaha', '?')[:30]} → HP: {info.get('nomor_hp', '-')[:15]}")
                    finally:
                        await biz_page.close()
                except Exception as e:
                    results[idx] = {"nama_usaha": "", "nomor_hp": "", "alamat": "", "website": ""}
                    done_count += 1
                    print(f"   ⚠  [{done_count}/{total}] Gagal: {e}")

        # Jalankan semua paralel (dibatasi semaphore 10)
        tasks = [process_one(i, url) for i, url in enumerate(place_urls)]
        await aio.gather(*tasks)

        # Pastikan gak ada slot kosong (defensive)
        results = [r if r else {"nama_usaha": "", "nomor_hp": "", "alamat": "", "website": ""} for r in results]

        await browser.close()

    print(f"   ✅ Total {len(results)} data usaha diekstrak dari DOM")
    return results

from city_coords import CITY_COORDS, DEFAULT_COORDS, detect_location


# ── Routes ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse(BASE_DIR / "templates" / "index.html")


@app.get("/hasil", response_class=HTMLResponse)
async def hasil():
    return FileResponse(BASE_DIR / "templates" / "hasil.html")


@app.post("/api/scrape")
async def scrape(keyword: str = Form(...),
                 max_scrolls: int = Form(0),
                 fields: str = Form("nama_usaha,nomor_hp,alamat,website"),
                 proxy: str = Form("")):
    """
    Endpoint utama: scrape Google Maps → ekstrak data dari DOM langsung.
    proxy: opsional — http://host:port atau http://user:pass@host:port
    Kalau proxy diisi (IP residential user sendiri), skip rate limiter.
    """
    global _last_scrape_time

    task_id = uuid.uuid4().hex[:8]
    proxy = proxy.strip() if proxy else None
    is_proxy_user = bool(proxy)

    selected_fields = [f.strip() for f in fields.split(",") if f.strip()]
    if not selected_fields:
        selected_fields = ["nama_usaha", "nomor_hp", "alamat", "website"]
    print(f"[{task_id}] 📋  Fields diterima: {fields}")
    print(f"[{task_id}] 📋  Selected fields: {selected_fields}")
    if is_proxy_user:
        print(f"[{task_id}] 🏠  Proxy user — skip rate limiter")

    # ── Rate Limit: hanya untuk non-proxy user ──────────────────
    if is_proxy_user:
        # Proxy user = IP sendiri, bebas scrape tanpa antri
        async with SCRAPE_LOCK:
            try:
                print(f"[{task_id}] 🔍  Mencari: {keyword} (via proxy...)")
                lat, lng = detect_location(keyword)
                print(f"[{task_id}] 📍  Lokasi: {lat}, {lng}")
                data = await scrape_businesses_from_gmaps(keyword, max_scrolls, lat, lng, proxy=proxy)
                print(f"[{task_id}] ✅  Dapat {len(data)} hasil")

                if set(selected_fields) != {"nama_usaha", "nomor_hp", "alamat", "website"}:
                    data = [{k: v for k, v in row.items() if k in selected_fields} for row in data]
                    print(f"[{task_id}] ✂️  Difilter ke field: {', '.join(selected_fields)}")

                return JSONResponse({
                    "success": True,
                    "task_id": task_id,
                    "keyword": keyword,
                    "total_results": len(data),
                    "data": data,
                })
            except Exception as e:
                print(f"[{task_id}] ❌  Error: {e}")
                return JSONResponse({
                    "success": False,
                    "error": str(e),
                }, status_code=500)
    else:
        # Non-proxy user: antri + cooldown (berbagi Railway IP)
        async with SCRAPE_LOCK:
            elapsed = time_mod.time() - _last_scrape_time
            if elapsed < COOLDOWN_SECONDS:
                wait = COOLDOWN_SECONDS - elapsed
                print(f"[{task_id}] ⏳  Cooldown: tunggu {wait:.1f}s...")
                await aio.sleep(wait)

            try:
                print(f"[{task_id}] 🔍  Mencari: {keyword}")
                lat, lng = detect_location(keyword)
                print(f"[{task_id}] 📍  Lokasi: {lat}, {lng}")
                data = await scrape_businesses_from_gmaps(keyword, max_scrolls, lat, lng)
                print(f"[{task_id}] ✅  Dapat {len(data)} hasil")

                if set(selected_fields) != {"nama_usaha", "nomor_hp", "alamat", "website"}:
                    data = [{k: v for k, v in row.items() if k in selected_fields} for row in data]
                    print(f"[{task_id}] ✂️  Difilter ke field: {', '.join(selected_fields)}")

                return JSONResponse({
                    "success": True,
                    "task_id": task_id,
                    "keyword": keyword,
                    "total_results": len(data),
                    "data": data,
                })
            except Exception as e:
                print(f"[{task_id}] ❌  Error: {e}")
                return JSONResponse({
                    "success": False,
                    "error": str(e),
                }, status_code=500)
            finally:
                _last_scrape_time = time_mod.time()


@app.get("/api/queue-status")
async def queue_status():
    """Cek status antrian — dipakai frontend untuk tampilkan estimasi."""
    now = time_mod.time()
    cooldown_remaining = max(0, COOLDOWN_SECONDS - (now - _last_scrape_time))
    return JSONResponse({
        "locked": SCRAPE_LOCK.locked(),
        "cooldown_remaining": round(cooldown_remaining, 1),
        "cooldown_total": COOLDOWN_SECONDS,
    })


# ── Run ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print("=" * 55)
    print(f"  🌐  GMaps Scraper AI — buka http://0.0.0.0:{port}")
    print("=" * 55)
    uvicorn.run(app, host="0.0.0.0", port=port)
