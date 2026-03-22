"""
HindMovie Scraper API 🚀
FastAPI version — ready for Render deployment
"""

import asyncio
import aiohttp
import re
import urllib.parse
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

app = FastAPI(
    title="HindMovie Scraper API",
    description="Search and resolve download links from hindmovie.ltd",
    version="1.0.0",
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
    'Accept-Encoding': 'gzip, deflate',
}

# ── Pydantic models ────────────────────────────────────────────────────────────

class ServerLinks(BaseModel):
    title: str
    quality: str
    servers: dict[str, str]

class SearchResult(BaseModel):
    title: str
    link: str

# ── HTTP Helpers ───────────────────────────────────────────────────────────────

async def fetch(session: aiohttp.ClientSession, url: str) -> str | None:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                return None
            return await resp.text(errors='replace')
    except Exception:
        return None

async def fetch_with_redirect(session: aiohttp.ClientSession, url: str) -> tuple[str | None, str]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15),
                               allow_redirects=True) as resp:
            return await resp.text(errors='replace'), str(resp.url)
    except Exception:
        return None, url

# ── Parsers ────────────────────────────────────────────────────────────────────

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
    for a in soup.find_all('a', href=re.compile(r'mvlink\.site')):
        href = a.get('href')
        text = a.get_text(strip=True)
        combined = text
        parent = a.find_parent()
        if parent:
            combined += " " + parent.get_text(strip=True)
            prev = parent.find_previous_sibling()
            if prev:
                combined += " " + prev.get_text(strip=True)
        m = re.search(r'(480p|720p|1080p|2160p|4K)', combined, re.I)
        links.append({'quality': m.group(1) if m else 'Unknown', 'link': href, 'text': text})
    return links

def parse_episodes(html: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    episodes = []
    for a in soup.find_all('a', string=re.compile(r'Episode\s*\d+', re.I)):
        episodes.append({'title': a.get_text(strip=True), 'link': a.get('href')})
    if not episodes:
        get_links = soup.find('a', string=re.compile(r'Get Links', re.I))
        if get_links:
            episodes.append({'title': 'Movie Link', 'link': get_links.get('href')})
    return episodes

def parse_hshare_from_mvlink(html: str, final_url: str) -> str | None:
    if 'hshare.ink' in final_url:
        return final_url
    soup = BeautifulSoup(html, 'html.parser')
    btn = soup.find('a', string=re.compile(r'Get Links', re.I))
    if btn:
        href = btn.get('href', '')
        if 'hshare.ink' in href:
            return href
    for a in soup.find_all('a', href=re.compile(r'hshare\.ink')):
        return a.get('href')
    return None

def parse_hcloud_from_hshare(html: str) -> str | None:
    soup = BeautifulSoup(html, 'html.parser')
    btn = soup.find('a', string=re.compile(r'HPage', re.I))
    return btn.get('href') if btn else None

def parse_servers(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, 'html.parser')
    servers = {}
    for i in range(1, 6):
        btn = soup.find('a', id=f'download-btn{i}')
        if btn and btn.get('href'):
            servers[f"Server {i}"] = btn.get('href')
    if not servers:
        for a in soup.find_all('a', string=re.compile(r'Server\s*\d+', re.I)):
            servers[a.get_text(strip=True)] = a.get('href')
    return servers

# ── Chain Resolver ─────────────────────────────────────────────────────────────

async def resolve_server_chain(session: aiohttp.ClientSession, url: str) -> dict:
    html, final_url = await fetch_with_redirect(session, url)
    if not html:
        return {}
    hshare_url = final_url if 'hshare.ink' in final_url else parse_hshare_from_mvlink(html, final_url)
    if not hshare_url:
        return {}
    html_hshare = await fetch(session, hshare_url)
    if not html_hshare:
        return {}
    hcloud_url = parse_hcloud_from_hshare(html_hshare)
    if not hcloud_url:
        return {}
    html_hcloud = await fetch(session, hcloud_url)
    if not html_hcloud:
        return {}
    return parse_servers(html_hcloud)

async def process_episode(session, ep: dict, quality: str) -> dict:
    servers = await resolve_server_chain(session, ep['link'])
    return {'title': ep['title'], 'quality': quality, 'servers': servers}

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"message": "HindMovie Scraper API is running 🚀", "docs": "/docs"}


@app.get("/search", response_model=list[SearchResult])
async def search(q: str = Query(..., description="Movie or series name")):
    """Returns a list of search results (title + link)."""
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


@app.get("/links", response_model=list[ServerLinks])
async def get_links(
    q: str = Query(..., description="Movie or series name"),
    season: Optional[int] = Query(None, description="Season number e.g. 1"),
    episode: Optional[int] = Query(None, description="Episode number e.g. 7"),
):
    """
    Resolve final server download links for a movie or a specific episode.

    Example:
    - /links?q=Inception
    - /links?q=Queen+Of+Tears&season=1&episode=7
    """
    target_ep = f"Episode {episode:02d}" if episode else None

    connector = aiohttp.TCPConnector(limit=50, ssl=False)
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        # Step 1: Search
        search_url = f"{BASE_URL}/?s={urllib.parse.quote_plus(q)}"
        html = await fetch(session, search_url)
        if not html:
            raise HTTPException(status_code=502, detail="Search failed")

        results = parse_articles(html)
        if not results:
            raise HTTPException(status_code=404, detail="No results found")

        item = results[0]

        # Step 2: Get movie/series page
        item_html = await fetch(session, item['link'])
        if not item_html:
            raise HTTPException(status_code=502, detail="Could not load item page")

        quality_buttons = parse_download_buttons(item_html)
        if not quality_buttons:
            raise HTTPException(status_code=404, detail="No download buttons found")

        # Step 3: Expand each quality button to find episodes
        mv_tasks = [fetch_with_redirect(session, qb['link']) for qb in quality_buttons]
        mv_results = await asyncio.gather(*mv_tasks)

        all_to_resolve = []
        for i, (mv_html, final_url) in enumerate(mv_results):
            if not mv_html:
                continue
            episodes = parse_episodes(mv_html)
            for ep in episodes:
                if target_ep:
                    if target_ep in ep['title']:
                        all_to_resolve.append((ep, quality_buttons[i]['quality']))
                else:
                    all_to_resolve.append((ep, quality_buttons[i]['quality']))

        if not all_to_resolve:
            raise HTTPException(status_code=404, detail="No matching episodes/links found")

        # Step 4: Resolve all server chains concurrently
        tasks = [process_episode(session, ep, q_) for ep, q_ in all_to_resolve]
        resolved = await asyncio.gather(*tasks)

    return resolved
