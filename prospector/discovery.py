"""Automated prospect discovery.

Finds businesses via Google Custom Search API, SerpAPI, or
by scraping public business directories.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from models import Prospect


async def search_google_cse(
    query: str,
    api_key: str,
    cse_id: str,
    num_results: int = 10,
) -> list[Prospect]:
    """Search Google Custom Search Engine API for businesses."""
    prospects = []
    async with httpx.AsyncClient() as client:
        for start in range(1, min(num_results, 100), 10):
            resp = await client.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": api_key,
                    "cx": cse_id,
                    "q": query,
                    "start": start,
                    "num": min(10, num_results - start + 1),
                },
                timeout=15,
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            for item in data.get("items", []):
                url = item.get("link", "")
                title = item.get("title", "")
                # Skip aggregator sites
                if _is_aggregator(url):
                    continue
                prospects.append(Prospect(
                    name=title,
                    url=url,
                    source="google_cse",
                ))

    return prospects


async def search_serpapi(
    query: str,
    api_key: str,
    num_results: int = 20,
) -> list[Prospect]:
    """Search using SerpAPI (supports Google, Bing, etc.)."""
    prospects = []
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://serpapi.com/search.json",
            params={
                "api_key": api_key,
                "q": query,
                "num": num_results,
                "engine": "google",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            return prospects

        data = resp.json()

        # Organic results
        for item in data.get("organic_results", []):
            url = item.get("link", "")
            title = item.get("title", "")
            if _is_aggregator(url):
                continue
            prospects.append(Prospect(
                name=title,
                url=url,
                source="serpapi",
            ))

        # Local results (gold mine — these are actual businesses)
        for item in data.get("local_results", []):
            website = item.get("website", "")
            title = item.get("title", "")
            if website:
                prospects.append(Prospect(
                    name=title,
                    url=website,
                    has_ads=False,
                    source="serpapi_local",
                ))

        # Ads (businesses actively spending money = best targets)
        for item in data.get("ads", []):
            url = item.get("link", "")
            title = item.get("title", "")
            if url and not _is_aggregator(url):
                prospects.append(Prospect(
                    name=title,
                    url=url,
                    has_ads=True,
                    source="serpapi_ads",
                ))

    return prospects


async def scrape_yellowpages(
    query: str,
    location: str,
    max_results: int = 20,
) -> list[Prospect]:
    """Scrape YellowPages for business listings."""
    prospects = []
    search_url = f"https://www.yellowpages.com/search"
    params = {"search_terms": query, "geo_location_terms": location}

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    ) as client:
        try:
            resp = await client.get(search_url, params=params, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                return prospects

            soup = BeautifulSoup(resp.text, "lxml")
            results = soup.find_all("div", class_="result")

            for result in results[:max_results]:
                name_tag = result.find("a", class_="business-name")
                if not name_tag:
                    continue
                name = name_tag.get_text(strip=True)

                # Try to find website link
                website_link = result.find("a", class_="track-visit-website")
                url = ""
                if website_link:
                    url = website_link.get("href", "")

                # Extract phone
                phone_tag = result.find("div", class_="phones")
                phone = phone_tag.get_text(strip=True) if phone_tag else ""

                if url:
                    prospects.append(Prospect(
                        name=name,
                        url=url,
                        niche=query,
                        location=location,
                        source="yellowpages",
                    ))
        except httpx.HTTPError:
            pass

    return prospects


async def scrape_yelp(
    query: str,
    location: str,
    max_results: int = 20,
) -> list[Prospect]:
    """Scrape Yelp for business listings."""
    prospects = []
    search_url = "https://www.yelp.com/search"
    params = {"find_desc": query, "find_loc": location}

    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    ) as client:
        try:
            resp = await client.get(search_url, params=params, timeout=15, follow_redirects=True)
            if resp.status_code != 200:
                return prospects

            soup = BeautifulSoup(resp.text, "lxml")

            # Yelp business links typically contain /biz/
            biz_links = soup.find_all("a", href=re.compile(r"/biz/"))
            seen_names = set()

            for link in biz_links:
                name = link.get_text(strip=True)
                if not name or len(name) < 3 or name in seen_names:
                    continue
                seen_names.add(name)

                # We get the Yelp page — actual website needs a second fetch
                biz_url = urljoin("https://www.yelp.com", link.get("href", ""))
                if "/biz/" in biz_url and len(prospects) < max_results:
                    prospects.append(Prospect(
                        name=name,
                        url=biz_url,  # Yelp URL — we'll resolve actual website later
                        niche=query,
                        location=location,
                        source="yelp",
                    ))
        except httpx.HTTPError:
            pass

    return prospects


async def resolve_yelp_websites(prospects: list[Prospect]) -> list[Prospect]:
    """For Yelp prospects, fetch the actual business website from the Yelp page."""
    resolved = []
    async with httpx.AsyncClient(
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    ) as client:
        for p in prospects:
            if p.source != "yelp" or "yelp.com" not in p.url:
                resolved.append(p)
                continue

            try:
                resp = await client.get(p.url, timeout=15, follow_redirects=True)
                soup = BeautifulSoup(resp.text, "lxml")

                # Look for external website link
                biz_website = soup.find("a", href=re.compile(r"biz_redir"))
                if biz_website:
                    actual_url = biz_website.get("href", "")
                    if actual_url:
                        p.url = actual_url
                        resolved.append(p)
                        continue

                # Alternative: look for "Business website" text
                for link in soup.find_all("a", href=True):
                    if "business" in link.get_text(strip=True).lower() and "website" in link.get_text(strip=True).lower():
                        p.url = link["href"]
                        resolved.append(p)
                        break
            except httpx.HTTPError:
                pass

            await asyncio.sleep(1)  # Be polite to Yelp

    return resolved


async def discover_prospects(
    niche: str,
    location: str,
    google_api_key: str = "",
    google_cse_id: str = "",
    serpapi_key: str = "",
    max_per_source: int = 20,
) -> list[Prospect]:
    """Run all discovery methods and return deduplicated prospects.

    Priority: SerpAPI > Google CSE > YellowPages > Yelp
    At least one method will be tried (directory scraping needs no API key).
    """
    all_prospects: list[Prospect] = []
    query = f"{niche} {location}"

    tasks = []

    # API-based methods (faster, more reliable)
    if serpapi_key:
        tasks.append(search_serpapi(query, serpapi_key, max_per_source))
    if google_api_key and google_cse_id:
        tasks.append(search_google_cse(query, google_api_key, google_cse_id, max_per_source))

    # Scraping methods (no API key needed)
    from prospector.scraper import discover_via_search
    tasks.append(discover_via_search(niche, location, max_per_source))
    tasks.append(scrape_yellowpages(niche, location, max_per_source))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, list):
            all_prospects.extend(result)

    # Deduplicate by domain
    seen_domains: set[str] = set()
    unique: list[Prospect] = []
    for p in all_prospects:
        domain = urlparse(p.url).netloc.lower().replace("www.", "")
        if domain and domain not in seen_domains:
            seen_domains.add(domain)
            p.niche = niche
            p.location = location
            unique.append(p)

    return unique


def _is_aggregator(url: str) -> bool:
    """Check if a URL belongs to an aggregator site (not an actual business)."""
    aggregators = [
        "yelp.com", "yellowpages.com", "bbb.org", "facebook.com",
        "instagram.com", "twitter.com", "linkedin.com", "mapquest.com",
        "google.com", "angieslist.com", "homeadvisor.com", "thumbtack.com",
        "nextdoor.com", "manta.com", "superpages.com", "whitepages.com",
        "tripadvisor.com", "foursquare.com", "wikipedia.org",
        "youtube.com", "pinterest.com", "tiktok.com",
    ]
    domain = urlparse(url).netloc.lower().replace("www.", "")
    return any(domain == agg or domain.endswith("." + agg) for agg in aggregators)
