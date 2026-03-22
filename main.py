"""
HindMovie Scraper API 🚀
FastAPI version — ready for Render deployment
"""

import asyncio
import aiohttp
import re
import urllib.parse
import logging
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hindapi")

app = FastAPI(
    title="HindMovie Scraper API",
    description="Search and resolve download links from hindmovie.ltd",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_URL = "https://hindmovie.ltd"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                  '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://hindmovie.ltd/',
}

# ── Pydantic models ──────────────────────────────────────────────────────────

class ServerLinks(BaseModel):
    title: str
    quality: str
    servers: dict[str, str]

class SearchResult(BaseModel):
    title: str
    link: str

class DebugChain(BaseModel):
    mvlink_url: str
    final_url_after_redirect: str
    hshare_url: Optional[str] = None
    hcloud_url: Optional[str] = None
    servers: dict[str, str]
    error: Optional[str] = None

# ── HTTP Helpers ─────────────────────────────────────────────────────────────

async def fetch(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            log.info(f"GET {url} -> {resp.status}")
            if resp.status != 200:
                return None
            return await resp.text(errors='replace')
    except Exception as e:
        log.warning(f"fetch failed {url}: {e}")
        return None

async def fetch_with_redirect(session: aiohttp.ClientSession, url: str) -> tuple[str | None, str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=20),
                               allow_redirects=True) as resp:
            log.info(f"REDIRECT {url} -> {resp.url} (status {resp.status})")
            return await resp.text(errors='replace'), str(resp.url)
    except Exception as e:
        log.warning(f"fetch_with_redirect failed {url}: {e}")
        return None, url

# ── Parsers ──────────────────────────────────────────────────────────────────

def parse_articles(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    movies = []
    for article in soup.find_all('article'):
        tag = article.find('h2', class_='entry-title') or article.find('a', rel='bookmark')
        if not tag:
            continue
        title = tag.get_text(strip=True)
        a = tag if tag.name == 'a' else tag.find('a')
        if a:
            movies.append({'title': title, 'link': a.get('href')})
    return movies


def parse_download_buttons(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    links = []
    all_mvlinks = soup.find_all('a', href=re.compile(r'mvlink\.site'))
    for a in all_mvlinks:
        href = a.get('href')
        quality = "Unknown"
        # Walk up DOM tree 6 levels collecting text
        search_text = a.get_text(strip=True)
        node = a
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            search_text += " " + node.get_text(separator=" ", strip=True)
        m = re.search(r'(2160p|4K|1080p|720p|480p|360p)', search_text, re.I)
        if m:
            quality = m.group(1).upper().replace('P', 'p')
        log.info(f"Button href={href} quality={quality}")
        links.append({'quality': quality, 'link': href, 'text': a.get_text(strip=True)})
    return links


def parse_episodes(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    episodes = []
    # Pattern 1: exact string match
    for a in soup.find_all('a', string=re.compile(r'Episode\s*\d+', re.I)):
        href = a.get('href', '')
        if href:
            episodes.append({'title': a.get_text(strip=True), 'link': href})
    # Pattern 2: partial text match
    if not episodes:
        for a in soup.find_all('a', href=True):
            txt = a.get_text(strip=True)
            if re.search(r'Episode\s*\d+', txt, re.I):
                episodes.append({'title': txt, 'link': a['href']})
    # Pattern 3: movie single button
    if not episodes:
        for pattern in [r'Get\s*Links', r'Download', r'Click\s*Here']:
            btn = soup.find('a', string=re.compile(pattern, re.I))
            if btn and btn.get('href'):
                episodes.append({'title': 'Movie Link', 'link': btn['href']})
                break
    log.info(f"parse_episodes: {len(episodes)} items")
    return episodes


def _find_any_link(html: str, domain: str) -> str | None:
    soup = BeautifulSoup(html, 'html.parser')
    for a in soup.find_all('a', href=re.compile(re.escape(domain))):
        return a.get('href')
    return None


def parse_hshare_from_mvlink(html: str, final_url: str) -> str | None:
    if 'hshare.ink' in final_url:
        return final_url
    soup = BeautifulSoup(html, 'html.parser')
    # Try button labels
    for pattern in [r'Get\s*Links', r'Download\s*Now', r'Continue']:
        btn = soup.find('a', string=re.compile(pattern, re.I))
        if btn and btn.get('href'):
            log.info(f"hshare via button '{pattern}': {btn.get('href')}")
            return btn.get('href')
    # Try domain patterns
    for domain in ['hshare.ink', 'hlinkz', 'hublinks', 'hlink', 'hpage']:
        r = _find_any_link(html, domain)
        if r:
            log.info(f"hshare via domain '{domain}': {r}")
            return r
    return None


def parse_hcloud_from_hshare(html: str) -> str | None:
    soup = BeautifulSoup(html, 'html.parser')
    for pattern in [r'HPage', r'HCloud', r'Get\s*File', r'Download', r'Continue', r'Click\s*Here']:
        btn = soup.find('a', string=re.compile(pattern, re.I))
        if btn and btn.get('href'):
            log.info(f"hcloud via '{pattern}': {btn.get('href')}")
            return btn.get('href')
    # Fallback: any external link that isn't hshare
    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.startswith('http') and 'hshare' not in href:
            log.info(f"hcloud fallback: {href}")
            return href
    return None


def parse_servers(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, 'html.parser')
    servers = {}
    # Pattern 1: id="download-btnN"
    for i in range(1, 8):
        btn = soup.find('a', id=f'download-btn{i}')
        if btn and btn.get('href'):
            servers[f"Server {i}"] = btn['href']
    # Pattern 2: text "Server N"
    if not servers:
        for a in soup.find_all('a', href=True):
            if re.search(r'Server\s*\d+', a.get_text(strip=True), re.I):
                servers[a.get_text(strip=True)] = a['href']
    # Pattern 3: known hosting domains
    if not servers:
        HOSTERS = ['drive.google', 'mega.nz', 'mediafire', 'pixeldrain',
                   'gofile', 'streamtape', 'filelions', 'doodstream',
                   'streamvid', 'vido', 'mixdrop']
        for a in soup.find_all('a', href=True):
            if any(h in a['href'] for h in HOSTERS):
                servers[a.get_text(strip=True) or a['href']] = a['href']
    log.info(f"parse_servers: {servers}")
    return servers

# ── Chain Resolver ───────────────────────────────────────────────────────────

async def resolve_server_chain(session: aiohttp.ClientSession, url: str) -> dict:
    log.info(f"=== chain START: {url}")
    html, final_url = await fetch_with_redirect(session, url)
    if not html:
        log.warning("chain FAIL step1")
        return {}

    # Short-circuit: servers already on this page
    quick = parse_servers(html)
    if quick:
        return quick

    hshare_url = parse_hshare_from_mvlink(html, final_url)
    log.info(f"chain step2 hshare_url={hshare_url}")
    if not hshare_url:
        log.warning("chain FAIL step2")
        return {}

    html_hshare = await fetch(session, hshare_url)
    if not html_hshare:
        log.warning(f"chain FAIL step3 fetch {hshare_url}")
        return {}

    quick = parse_servers(html_hshare)
    if quick:
        return quick

    hcloud_url = parse_hcloud_from_hshare(html_hshare)
    log.info(f"chain step4 hcloud_url={hcloud_url}")
    if not hcloud_url:
        log.warning("chain FAIL step4")
        return {}

    html_hcloud = await fetch(session, hcloud_url)
    if not html_hcloud:
        log.warning(f"chain FAIL step5 fetch {hcloud_url}")
        return {}

    servers = parse_servers(html_hcloud)
    log.info(f"=== chain END: {len(servers)} servers")
    return servers


async def process_episode(session, ep: dict, quality: str) -> dict:
    servers = await resolve_server_chain(session, ep['link'])
    return {'title': ep['title'], 'quality': quality, 'servers': servers}

# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "HindMovie Scraper API is running 🚀", "docs": "/docs"}


@app.get("/search", response_model=list[SearchResult])
async def search(q: str = Query(..., description="Movie or series name")):
    """Returns list of search results."""
    connector = aiohttp.TCPConnector(limit=20, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        url = f"{BASE_URL}/?s={urllib.parse.quote_plus(q)}"
        html = await fetch(session, url)
        if not html:
            raise HTTPException(status_code=502, detail="Search request failed")
        results = parse_articles(html)
        if not results:
            raise HTTPException(status_code=404, detail="No results found")
        return results


@app.get("/debug/chain", response_model=DebugChain)
async def debug_chain(url: str = Query(..., description="An mvlink.site episode URL to trace")):
    """Trace every step of the link chain — use when servers:{} is empty."""
    connector = aiohttp.TCPConnector(limit=5, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        html, final_url = await fetch_with_redirect(session, url)
        if not html:
            return DebugChain(mvlink_url=url, final_url_after_redirect=url, servers={},
                              error="Step 1 failed: could not fetch mvlink URL")
        hshare_url = parse_hshare_from_mvlink(html, final_url)
        if not hshare_url:
            return DebugChain(mvlink_url=url, final_url_after_redirect=final_url, servers={},
                              error="Step 2 failed: no intermediate link found on mvlink page")
        html_hshare = await fetch(session, hshare_url)
        if not html_hshare:
            return DebugChain(mvlink_url=url, final_url_after_redirect=final_url,
                              hshare_url=hshare_url, servers={},
                              error=f"Step 3 failed: could not fetch {hshare_url}")
        quick = parse_servers(html_hshare)
        if quick:
            return DebugChain(mvlink_url=url, final_url_after_redirect=final_url,
                              hshare_url=hshare_url, hcloud_url="(servers on hshare page)", servers=quick)
        hcloud_url = parse_hcloud_from_hshare(html_hshare)
        if not hcloud_url:
            return DebugChain(mvlink_url=url, final_url_after_redirect=final_url,
                              hshare_url=hshare_url, servers={},
                              error="Step 4 failed: no hcloud link on hshare page")
        html_hcloud = await fetch(session, hcloud_url)
        if not html_hcloud:
            return DebugChain(mvlink_url=url, final_url_after_redirect=final_url,
                              hshare_url=hshare_url, hcloud_url=hcloud_url, servers={},
                              error=f"Step 5 failed: could not fetch {hcloud_url}")
        servers = parse_servers(html_hcloud)
        return DebugChain(mvlink_url=url, final_url_after_redirect=final_url,
                          hshare_url=hshare_url, hcloud_url=hcloud_url, servers=servers,
                          error=None if servers else "Fetched hcloud but found no server links")


@app.get("/debug/page")
async def debug_page(url: str = Query(..., description="Any URL — lists all links found")):
    """Returns every <a> tag on a page. Use to inspect what the site actually shows."""
    connector = aiohttp.TCPConnector(limit=5, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        html, final_url = await fetch_with_redirect(session, url)
        if not html:
            raise HTTPException(status_code=502, detail="Could not fetch page")
        soup = BeautifulSoup(html, 'html.parser')
        links = [{"text": a.get_text(strip=True), "href": a.get('href')}
                 for a in soup.find_all('a', href=True)]
        return {"final_url": final_url, "total_links": len(links), "links": links}


@app.get("/links", response_model=list[ServerLinks])
async def get_links(
    q: str = Query(..., description="Movie or series name"),
    season: Optional[int] = Query(None, description="Season number e.g. 1"),
    episode: Optional[int] = Query(None, description="Episode number e.g. 7"),
):
    """
    Resolve final server download links.
    Examples:
      /links?q=Inception
      /links?q=Queen+Of+Tears&season=1&episode=7
    """
    target_ep = f"Episode {episode:02d}" if episode else None
    connector = aiohttp.TCPConnector(limit=50, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        search_url = f"{BASE_URL}/?s={urllib.parse.quote_plus(q)}"
        html = await fetch(session, search_url)
        if not html:
            raise HTTPException(status_code=502, detail="Search failed")
        results = parse_articles(html)
        if not results:
            raise HTTPException(status_code=404, detail="No results found")
        item = results[0]
        log.info(f"Top result: {item['title']} -> {item['link']}")
        item_html = await fetch(session, item['link'])
        if not item_html:
            raise HTTPException(status_code=502, detail="Could not load item page")
        quality_buttons = parse_download_buttons(item_html)
        if not quality_buttons:
            raise HTTPException(status_code=404, detail="No download buttons found")
        log.info(f"Buttons: {[(b['quality'], b['link']) for b in quality_buttons]}")
        mv_tasks = [fetch_with_redirect(session, qb['link']) for qb in quality_buttons]
        mv_results = await asyncio.gather(*mv_tasks)
        all_to_resolve = []
        for i, (mv_html, final_url) in enumerate(mv_results):
            if not mv_html:
                continue
            episodes = parse_episodes(mv_html)
            log.info(f"Button {i} ({quality_buttons[i]['quality']}): {len(episodes)} episodes")
            for ep in episodes:
                if target_ep:
                    if target_ep in ep['title']:
                        all_to_resolve.append((ep, quality_buttons[i]['quality']))
                else:
                    all_to_resolve.append((ep, quality_buttons[i]['quality']))
        if not all_to_resolve:
            raise HTTPException(status_code=404, detail="No matching episodes/links found")
        log.info(f"Resolving {len(all_to_resolve)} links...")
        tasks = [process_episode(session, ep, q_) for ep, q_ in all_to_resolve]
        resolved = await asyncio.gather(*tasks)
    return list(resolved)
