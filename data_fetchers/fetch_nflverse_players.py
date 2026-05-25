"""Fetch NFLVerse player data."""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.parquet"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def fetch_players() -> pd.DataFrame:
    df = pd.read_parquet(URL)
    df["UpdateTimestamp"] = datetime.now(timezone.utc).isoformat()
    return df


def main():
    out_dir = Path(__file__).parent.parent / "data" / "raw" / "nflverse"
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Fetching NFLVerse players from %s", URL)
    df = fetch_players()
    path = out_dir / "nflverse_players.parquet"
    df.to_parquet(path, index=False)
    log.info("Saved %d players -> %s", len(df), path)


if __name__ == "__main__":
    main()
