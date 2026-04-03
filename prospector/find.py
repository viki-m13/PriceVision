"""Prospect finder — discover businesses to audit.

Finds local businesses and web properties that are likely
candidates for revenue leak audits.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from models import Prospect


# Niche keywords that tend to have high-value leads
HIGH_VALUE_NICHES = [
    "plumber", "electrician", "hvac", "roofing", "landscaping",
    "dentist", "chiropractor", "lawyer", "attorney", "realtor",
    "real estate agent", "contractor", "auto repair", "mechanic",
    "pest control", "cleaning service", "moving company",
    "personal injury lawyer", "divorce lawyer", "dui lawyer",
    "home inspector", "insurance agent", "financial advisor",
    "orthodontist", "dermatologist", "plastic surgeon",
    "veterinarian", "dog grooming", "salon", "spa",
    "restaurant", "catering", "photographer", "wedding planner",
]


def load_prospects_from_csv(path: str) -> list[Prospect]:
    """Load prospects from a CSV file.

    Expected columns: name, url, niche, location
    """
    prospects = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            prospects.append(Prospect(
                name=row.get("name", ""),
                url=row.get("url", "").strip(),
                niche=row.get("niche", ""),
                location=row.get("location", ""),
                source="csv",
            ))
    return [p for p in prospects if p.url]


def save_prospects_to_csv(prospects: list[Prospect], path: str) -> None:
    """Save prospects to a CSV file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "url", "niche", "location", "has_ads", "source"])
        writer.writeheader()
        for p in prospects:
            writer.writerow({
                "name": p.name,
                "url": p.url,
                "niche": p.niche,
                "location": p.location,
                "has_ads": p.has_ads,
                "source": p.source,
            })


def generate_search_queries(niche: str, location: str) -> list[str]:
    """Generate Google search queries to find prospects.

    These queries are designed to find businesses that are likely
    spending money on advertising but may have broken funnels.
    """
    queries = [
        f"{niche} {location}",
        f"{niche} near {location}",
        f"best {niche} in {location}",
        f"{niche} {location} reviews",
        f"{niche} {location} free quote",
        f"{niche} {location} free estimate",
    ]
    return queries


def load_prospects_from_json(path: str) -> list[Prospect]:
    """Load prospects from a JSON file."""
    with open(path) as f:
        data = json.load(f)
    return [
        Prospect(
            name=item.get("name", ""),
            url=item.get("url", "").strip(),
            niche=item.get("niche", ""),
            location=item.get("location", ""),
            has_ads=item.get("has_ads", False),
            source=item.get("source", "json"),
        )
        for item in data
        if item.get("url")
    ]


def create_sample_prospects_file(path: str = "sample_prospects.csv") -> str:
    """Create a sample prospects CSV for testing."""
    prospects = [
        Prospect(name="Example Plumber", url="https://example.com", niche="plumber", location="Austin TX"),
        Prospect(name="Example Dentist", url="https://example.com", niche="dentist", location="Austin TX"),
    ]
    save_prospects_to_csv(prospects, path)
    return path


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3:
        niche = sys.argv[1]
        location = sys.argv[2]
    else:
        niche = "plumber"
        location = "Austin TX"

    print(f"\nSearch queries for: {niche} in {location}")
    print("=" * 50)
    for q in generate_search_queries(niche, location):
        print(f"  {q}")

    print(f"\nHigh-value niches to target:")
    for n in HIGH_VALUE_NICHES:
        print(f"  - {n}")
