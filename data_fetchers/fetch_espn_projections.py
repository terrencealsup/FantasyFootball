"""Fetch ESPN fantasy football projections by year.

Two datasets:
  - Season totals: projected season points per player at the start of each season
  - Weekly:        projected points per player before each week
"""

import json
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

# NFL weeks per fantasy season (weeks 1-17 covers all years safely)
WEEKS = range(1, 18)

_POSITION_MAP = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}

# Slot IDs covering all fantasy-relevant positions
_ALL_SLOTS = list(range(20)) + [23, 24]

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _session(espn_s2: str, swid: str) -> requests.Session:
    s = requests.Session()
    s.cookies.set("espn_s2", espn_s2)
    s.cookies.set("swid", swid)
    s.headers["User-Agent"] = "Mozilla/5.0"
    return s


def _iter_players(
    session: requests.Session,
    league_id: str,
    year: int,
    scoring_period: int,
    sort_key: str,
    page_size: int = 300,
):
    """Paginate through all players for a given scoring period."""
    offset = 0
    while True:
        filt = json.dumps({
            "players": {
                "filterSlotIds": {"value": _ALL_SLOTS},
                "filterStatsForCurrentSeasonScoringPeriodId": {"value": [scoring_period]},
                "sortAppliedStatTotal": {"sortAsc": False, "sortPriority": 1, "value": sort_key},
                "limit": page_size,
                "offset": offset,
            }
        })
        r = session.get(
            f"{BASE_URL}/{year}/segments/0/leagues/{league_id}",
            headers={"X-Fantasy-Filter": filt},
            params={"scoringPeriodId": scoring_period, "view": "kona_player_info"},
            timeout=30,
        )
        r.raise_for_status()
        players = r.json().get("players", [])
        yield from players
        if len(players) < page_size:
            break
        offset += page_size


def _to_rows(players, stat_source: int, split_type: int, fetched_at: str) -> list[dict]:
    rows = []
    for p in players:
        pl = p["player"]
        stat = next(
            (s for s in pl.get("stats", [])
             if s["statSourceId"] == stat_source and s["statSplitTypeId"] == split_type),
            None,
        )
        rows.append({
            "espn_id": pl["id"],
            "player_name": pl.get("fullName"),
            "position": _POSITION_MAP.get(pl.get("defaultPositionId"), "UNK"),
            "nfl_team_id": pl.get("proTeamId"),
            "status": p.get("status"),
            "fantasy_team_id": p.get("onTeamId") or None,
            "projected_points": stat["appliedTotal"] if stat else None,
            "UpdateTimestamp": fetched_at,
        })
    return rows


def fetch_season_projections(
    league_id: str,
    year: int,
    espn_s2: str,
    swid: str,
) -> pd.DataFrame:
    """Return projected season totals for all players (rostered + FA)."""
    session = _session(espn_s2, swid)
    sort_key = f"10{year}"
    players = list(_iter_players(session, league_id, year, 0, sort_key))
    fetched_at = datetime.now(timezone.utc).isoformat()
    df = pd.DataFrame(_to_rows(players, stat_source=1, split_type=0, fetched_at=fetched_at))
    df["espn_id"] = df["espn_id"].astype("Int64")
    df["nfl_team_id"] = df["nfl_team_id"].astype("Int64")
    df["fantasy_team_id"] = df["fantasy_team_id"].astype("Int64")
    return df


def fetch_weekly_projections(
    league_id: str,
    year: int,
    week: int,
    espn_s2: str,
    swid: str,
) -> pd.DataFrame:
    """Return projected points for all players for a single week."""
    session = _session(espn_s2, swid)
    sort_key = f"11{year}{week}"
    players = list(_iter_players(session, league_id, year, week, sort_key))
    fetched_at = datetime.now(timezone.utc).isoformat()
    df = pd.DataFrame(_to_rows(players, stat_source=1, split_type=1, fetched_at=fetched_at))
    df["espn_id"] = df["espn_id"].astype("Int64")
    df["nfl_team_id"] = df["nfl_team_id"].astype("Int64")
    df["fantasy_team_id"] = df["fantasy_team_id"].astype("Int64")
    return df


def main():
    espn_s2 = os.environ.get("ESPN_S2", "")
    swid = os.environ.get("ESPN_SWID", "")
    league_id = os.environ.get("ESPN_LEAGUE_ID", "")

    if not all([espn_s2, swid, league_id]):
        raise RuntimeError(
            "Set ESPN_S2, ESPN_SWID, and ESPN_LEAGUE_ID environment variables before running."
        )

    out_dir = Path(__file__).parent.parent / "data" / "raw" / "espn_projections"
    out_dir.mkdir(parents=True, exist_ok=True)

    for year in range(2019, 2027):
        # --- Season total projections ---
        log.info("Fetching season projections year=%d", year)
        try:
            df = fetch_season_projections(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
            df.insert(0, "year", year)
            path = out_dir / f"espn_projections_season_{league_id}_{year}.parquet"
            df.to_parquet(path, index=False)
            log.info("  Saved %d players -> %s", len(df), path.name)
        except Exception as exc:
            log.warning("  Skipped season %d: %s", year, exc)
        time.sleep(0.5)

        # --- Weekly projections ---
        weekly_frames = []
        for week in WEEKS:
            log.info("Fetching weekly projections year=%d week=%d", year, week)
            try:
                df = fetch_weekly_projections(league_id=league_id, year=year, week=week, espn_s2=espn_s2, swid=swid)
                if df["projected_points"].isna().all():
                    log.info("  Week %d: no projections, stopping", week)
                    break
                df.insert(0, "week", week)
                df.insert(0, "year", year)
                weekly_frames.append(df)
                log.info("  Week %d: %d players", week, len(df))
            except Exception as exc:
                log.warning("  Skipped year=%d week=%d: %s", year, week, exc)
            time.sleep(0.3)

        if weekly_frames:
            combined = pd.concat(weekly_frames, ignore_index=True)
            path = out_dir / f"espn_projections_weekly_{league_id}_{year}.parquet"
            combined.to_parquet(path, index=False)
            log.info("Saved weekly %d (%d rows) -> %s", year, len(combined), path.name)


if __name__ == "__main__":
    main()
