"""Fetch FantasyPros Expert Consensus Rankings (ECR) cheatsheet by year and scoring.

Data is embedded as a JSON variable (ecrData) in the page HTML.
"""

import logging
import re
import json
from datetime import datetime, timezone
from pathlib import Path

import requests
import pandas as pd

_SCORING_SLUG = {
    "half_ppr": "half-point-ppr-cheatsheets",
    "ppr":      "ppr-cheatsheets",
    "standard": "cheatsheets",
}

BASE_URL = "https://www.fantasypros.com/nfl/rankings/{slug}.php"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def fetch_ecr(scoring: str = "half_ppr", year: int = 2026) -> pd.DataFrame:
    slug = _SCORING_SLUG[scoring]
    url = BASE_URL.format(slug=slug)
    r = requests.get(url, params={"year": year}, headers=_HEADERS, timeout=30)
    r.raise_for_status()

    m = re.search(r'ecrData\s*=\s*(\{.*?\});\s*\n', r.text, re.DOTALL)
    if not m:
        raise ValueError(f"ecrData not found in page for scoring={scoring} year={year}")
    data = json.loads(m.group(1))

    rows = []
    for p in data["players"]:
        rows.append({
            "fp_id":        p["player_id"],
            "player_name":  p["player_name"],
            "team":         p.get("player_team_id"),
            "position":     p.get("player_position_id"),
            "bye":          p.get("player_bye_week"),
            "rank_ecr":     p.get("rank_ecr"),
            "rank_min":     p.get("rank_min"),
            "rank_max":     p.get("rank_max"),
            "rank_ave":     p.get("rank_ave"),
            "rank_std":     p.get("rank_std"),
            "pos_rank":     p.get("pos_rank"),
            "tier":         p.get("tier"),
        })

    df = pd.DataFrame(rows)
    for col in ("fp_id", "rank_ecr", "rank_min", "rank_max", "tier"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    for col in ("rank_ave", "rank_std"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["bye"] = pd.to_numeric(df["bye"], errors="coerce").astype("Int64")
    df["scoring"] = scoring
    df["year"] = year
    df["UpdateTimestamp"] = datetime.now(timezone.utc).isoformat()
    return df


def main():
    out_dir = Path(__file__).parent.parent / "data" / "raw" / "fantasypros_ecr"
    out_dir.mkdir(parents=True, exist_ok=True)

    scoring = "half_ppr"
    year = 2026
    log.info("Fetching ECR scoring=%s year=%d", scoring, year)
    df = fetch_ecr(scoring=scoring, year=year)
    path = out_dir / f"fantasypros_ecr_{scoring}_{year}.parquet"
    df.to_parquet(path, index=False)
    log.info("Saved %d players -> %s", len(df), path)


if __name__ == "__main__":
    main()
