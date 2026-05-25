"""Fetch historical ESPN fantasy football draft results by year."""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

import pandas as pd
import requests

BASE_URL = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons"

# ESPN position ID -> abbreviation
_POSITION_MAP = {
    1: "QB",
    2: "RB",
    3: "WR",
    4: "TE",
    5: "K",
    16: "DST",
}

# Known draft pick corrections: {year: [(team_name_a, team_name_b), ...]}
# Each pair indicates that all picks for team_a and team_b should be swapped.
_PICK_SWAPS: dict[int, list[tuple[str, str]]] = {
    2025: [("The Brain Trust", "The Fraud")],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _session(espn_s2: str, swid: str) -> requests.Session:
    s = requests.Session()
    s.cookies.set("espn_s2", espn_s2)
    s.cookies.set("swid", swid)
    s.headers["User-Agent"] = "Mozilla/5.0"
    return s


def _fetch_teams(session: requests.Session, league_id: str, year: int) -> dict[int, str]:
    """Return {team_id: team_name}."""
    r = session.get(
        f"{BASE_URL}/{year}/segments/0/leagues/{league_id}",
        params={"view": "mTeam"},
        timeout=15,
    )
    r.raise_for_status()
    return {t["id"]: t["name"] for t in r.json()["teams"]}


def _fetch_player_info(
    session: requests.Session, year: int, player_ids: list[int]
) -> dict[int, dict]:
    """Return {player_id: {name, position, nfl_team_id}} for the given IDs."""
    filt = json.dumps({"players": {"filterIds": {"value": player_ids}, "limit": len(player_ids)}})
    r = session.get(
        f"{BASE_URL}/{year}/players",
        params={"scoringPeriodId": 1, "view": "kona_player_info"},
        headers={"X-Fantasy-Filter": filt},
        timeout=15,
    )
    r.raise_for_status()
    return {
        p["id"]: {
            "player_name": p.get("fullName"),
            "position": _POSITION_MAP.get(p.get("defaultPositionId"), "UNK"),
            "nfl_team_id": p.get("proTeamId"),
        }
        for p in r.json()
    }


def fetch_draft(
    league_id: str,
    year: int,
    espn_s2: str,
    swid: str,
) -> pd.DataFrame:
    """Fetch draft picks for a single league/year.

    Returns a DataFrame with one row per pick, enriched with player name,
    position, and fantasy team name.
    """
    session = _session(espn_s2, swid)

    r = session.get(
        f"{BASE_URL}/{year}/segments/0/leagues/{league_id}",
        params={"view": "mDraftDetail"},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()

    draft = data.get("draftDetail", {})
    if not draft.get("drafted") or not draft.get("picks"):
        raise ValueError(f"No completed draft found for league {league_id} year {year}")

    picks = draft["picks"]
    teams = _fetch_teams(session, league_id, year)

    player_ids = list({p["playerId"] for p in picks})
    player_info = _fetch_player_info(session, year, player_ids)

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for pick in picks:
        pid = pick["playerId"]
        info = player_info.get(pid, {})
        rows.append({
            "overall_pick": pick["overallPickNumber"],
            "round": pick["roundId"],
            "round_pick": pick["roundPickNumber"],
            "player_id": pid,
            "player_name": info.get("player_name"),
            "position": info.get("position"),
            "nfl_team_id": info.get("nfl_team_id"),
            "team_id": pick["teamId"],
            "team_name": teams.get(pick["teamId"]),
            "UpdateTimestamp": fetched_at,
        })

    df = pd.DataFrame(rows)
    for col in ("overall_pick", "round", "round_pick", "player_id", "nfl_team_id", "team_id"):
        df[col] = df[col].astype("Int64")

    swap_cols = ["player_id", "player_name", "position", "nfl_team_id", "team_id", "team_name"]
    for name_a, name_b in _PICK_SWAPS.get(year, []):
        # ESPN recorded both the player and the team assignment incorrectly for
        # these two teams. Swap all pick content (player + team) round-by-round
        # while keeping overall_pick, round, and round_pick in place.
        idx_a = df[df["team_name"] == name_a].sort_values("overall_pick").index
        idx_b = df[df["team_name"] == name_b].sort_values("overall_pick").index
        if len(idx_a) > 0 and len(idx_b) > 0 and len(idx_a) == len(idx_b):
            vals_a = df.loc[idx_a, swap_cols].values.copy()
            vals_b = df.loc[idx_b, swap_cols].values.copy()
            df.loc[idx_a, swap_cols] = vals_b
            df.loc[idx_b, swap_cols] = vals_a
            log.info("Swapped picks: %s <-> %s", name_a, name_b)

    return df


def main():
    espn_s2 = os.environ.get("ESPN_S2", "")
    swid = os.environ.get("ESPN_SWID", "")
    league_id = os.environ.get("ESPN_LEAGUE_ID", "")

    if not all([espn_s2, swid, league_id]):
        raise RuntimeError(
            "Set ESPN_S2, ESPN_SWID, and ESPN_LEAGUE_ID environment variables before running."
        )

    out_dir = Path(__file__).parent.parent / "data" / "raw" / "espn_fantasy_drafts"
    out_dir.mkdir(parents=True, exist_ok=True)

    for year in range(2015, 2026):
        log.info("Fetching league %s draft year=%d", league_id, year)
        try:
            df = fetch_draft(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
            df.insert(0, "year", year)
            path = out_dir / f"espn_fantasy_draft_{league_id}_{year}.parquet"
            df.to_parquet(path, index=False)
            log.info("Saved %d picks -> %s", len(df), path)
        except Exception as exc:
            log.warning("Skipped year %d: %s", year, exc)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
