"""Fetch ESPN fantasy football team info by year."""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _session(espn_s2: str, swid: str) -> requests.Session:
    s = requests.Session()
    s.cookies.set("espn_s2", espn_s2)
    s.cookies.set("swid", swid)
    s.headers["User-Agent"] = "Mozilla/5.0"
    return s


def fetch_teams(
    league_id: str,
    year: int,
    espn_s2: str,
    swid: str,
) -> pd.DataFrame:
    """Fetch team info for a single league/year.

    Returns a DataFrame with one row per team including owner name,
    season record, points, final rank, and transaction totals.
    """
    session = _session(espn_s2, swid)
    r = session.get(
        f"{BASE_URL}/{year}/segments/0/leagues/{league_id}",
        params={"view": "mTeam"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()

    members = {m["id"]: m for m in data.get("members", [])}
    fetched_at = datetime.now(timezone.utc).isoformat()

    rows = []
    for t in data["teams"]:
        overall = t.get("record", {}).get("overall", {})
        tx = t.get("transactionCounter", {})
        primary_owner_id = t.get("primaryOwner")
        base = {
            "team_id": t["id"],
            "team_name": t["name"],
            "abbrev": t.get("abbrev"),
            "wins": overall.get("wins"),
            "losses": overall.get("losses"),
            "ties": overall.get("ties"),
            "points_for": overall.get("pointsFor"),
            "points_against": overall.get("pointsAgainst"),
            "final_rank": t.get("rankCalculatedFinal"),
            "playoff_seed": t.get("playoffSeed") or None,
            "draft_day_projected_rank": t.get("draftDayProjectedRank") or None,
            "waiver_rank": t.get("waiverRank") or None,
            "acquisitions": tx.get("acquisitions"),
            "drops": tx.get("drops"),
            "trades": tx.get("trades"),
            "UpdateTimestamp": fetched_at,
        }
        for owner_id in t.get("owners", [primary_owner_id]):
            owner = members.get(owner_id, {})
            rows.append({
                **base,
                "owner_id": owner_id,
                "owner_first_name": owner.get("firstName"),
                "owner_last_name": owner.get("lastName"),
                "is_primary_owner": owner_id == primary_owner_id,
            })

    df = pd.DataFrame(rows)
    for col in ("team_id", "wins", "losses", "ties", "final_rank",
                "playoff_seed", "draft_day_projected_rank", "waiver_rank",
                "acquisitions", "drops", "trades"):
        df[col] = df[col].astype("Int64")
    df["is_primary_owner"] = df["is_primary_owner"].astype(bool)
    return df


def main():
    espn_s2 = os.environ.get("ESPN_S2", "")
    swid = os.environ.get("ESPN_SWID", "")
    league_id = os.environ.get("ESPN_LEAGUE_ID", "")

    if not all([espn_s2, swid, league_id]):
        raise RuntimeError(
            "Set ESPN_S2, ESPN_SWID, and ESPN_LEAGUE_ID environment variables before running."
        )

    out_dir = Path(__file__).parent.parent / "data" / "raw" / "espn_fantasy_teams"
    out_dir.mkdir(parents=True, exist_ok=True)

    for year in range(2015, 2026):
        log.info("Fetching league %s teams year=%d", league_id, year)
        try:
            df = fetch_teams(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
            df.insert(0, "year", year)
            path = out_dir / f"espn_fantasy_teams_{league_id}_{year}.parquet"
            df.to_parquet(path, index=False)
            log.info("Saved %d teams -> %s", len(df), path)
        except Exception as exc:
            log.warning("Skipped year %d: %s", year, exc)
        time.sleep(0.3)


if __name__ == "__main__":
    main()
