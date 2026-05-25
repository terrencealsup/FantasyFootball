"""Fetch ADP data from FantasyPros."""

import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
import pandas as pd
from bs4 import BeautifulSoup

BASE_URL = "https://www.fantasypros.com/nfl/adp/{slug}.php"

SCORING_PREFIX = {
    "standard": "",
    "ppr": "ppr-",
    "half_ppr": "half-point-ppr-",
}

POSITIONS = ["overall", "qb", "rb", "wr", "te", "k", "dst"]

# These positions have no scoring variant on FantasyPros
_NO_SCORING_POSITIONS = {"qb", "k", "dst"}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

# Maps raw header text (lowercased) to normalized column names.
# Position-specific rank headers (qb, rb, etc.) all map to pos_rank.
_HEADER_MAP = {
    "rank": "rank",
    "overall": "overall_rank",
    "pos": "pos",
    "avg": "avg",
    "real-time": "realtime",
    "rtsports": "rtsports",
    **{p: "pos_rank" for p in POSITIONS if p != "overall"},
    "espn": "espn",
    "yahoo": "yahoo",
    "cbs": "cbs",
    "fantrax": "fantrax",
    "sleeper": "sleeper",
}

# Columns that are logically integers but may have missing values.
# Platform ADP picks are always whole numbers; avg is a true average so stays float.
_INT_COLUMNS = {
    "fp_id", "bye", "rank", "overall_rank", "pos_rank",
    "espn", "yahoo", "cbs", "fantrax", "sleeper", "rtsports", "realtime",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def _normalize_header(text: str) -> str:
    key = text.lower().strip()
    return _HEADER_MAP.get(key, key.replace(" ", "_").replace("-", "_"))


def _float(value) -> float | None:
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def _parse_cell(header: str, td) -> float | str | None:
    if header == "realtime":
        return _float(td.get("data-sort-value"))
    if header == "pos":  # "WR1", "RB2", etc. on the overall page
        return td.text.strip()
    return _float(td.text)


def fetch_adp(
    position: str = "overall",
    scoring: str = "half_ppr",
    year: int = 2025,
) -> pd.DataFrame:
    """Fetch ADP data from FantasyPros.

    Args:
        position: "overall", "qb", "rb", "wr", "te", "k", or "dst"
        scoring:  "standard", "ppr", or "half_ppr"
        year:     Season year

    Returns:
        DataFrame with player info, platform ADPs, and metadata columns
        fp_id and UpdateTimestamp. Columns vary by position.
    """
    position = position.lower()
    if scoring not in SCORING_PREFIX:
        raise ValueError(f"scoring must be one of {list(SCORING_PREFIX)}")

    prefix = "" if position in _NO_SCORING_POSITIONS else SCORING_PREFIX[scoring]
    url = BASE_URL.format(slug=f"{prefix}{position}")

    resp = requests.get(url, params={"year": year}, headers=_HEADERS, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", id="data")
    if table is None:
        raise ValueError(f"ADP table not found at {resp.url}")

    # Parse column headers; locate the player column by its CSS class.
    ths = table.thead.find_all("th")
    player_col_idx = next(
        (i for i, th in enumerate(ths) if "player-label" in th.get("class", [])),
        None,
    )
    if player_col_idx is None:
        raise ValueError("Could not find player column in table header")

    def _th_text(th) -> str:
        # Prefer the anchor text (e.g. Real-Time link); fall back to first text node
        # to avoid picking up tooltip <span> content.
        a = th.find("a")
        if a:
            return a.get_text()
        return th.find(string=True, recursive=False) or th.get_text()

    data_headers = [
        _normalize_header(_th_text(th)) for i, th in enumerate(ths) if i != player_col_idx
    ]

    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for tr in table.tbody.find_all("tr"):
        tds = tr.find_all("td")

        player_td = tds[player_col_idx]
        a = player_td.find("a", class_="player-name")
        if a is None:
            continue

        player_name = a.text.strip()
        fp_id = next(
            (int(c.split("-")[-1]) for c in a.get("class", []) if c.startswith("fp-id-")),
            None,
        )
        smalls = player_td.find_all("small")
        # DST pages only have a bye <small>(N)</small> with no team abbreviation.
        # Detect by checking whether the first <small> looks like "(N)" vs "ABC".
        if smalls and smalls[0].text.strip().startswith("("):
            team = None
            bye_text = smalls[0].text.strip("()")
        else:
            team = smalls[0].text.strip() if smalls else None
            bye_text = smalls[1].text.strip("()") if len(smalls) > 1 else None
        bye = int(bye_text) if bye_text and bye_text.isdigit() else None

        data_tds = [td for i, td in enumerate(tds) if i != player_col_idx]
        row: dict = {
            "player": player_name,
            "fp_id": fp_id,
            "team": team,
            "bye": bye,
        }
        for header, td in zip(data_headers, data_tds):
            row[header] = _parse_cell(header, td)

        row["UpdateTimestamp"] = fetched_at
        rows.append(row)

    df = pd.DataFrame(rows)
    for col in _INT_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype("Int64")
    return df


def main():
    out_dir = Path(__file__).parent.parent / "data" / "raw" / "fantasypros_adp"
    out_dir.mkdir(parents=True, exist_ok=True)

    years = range(2015, 2027)

    for scoring in SCORING_PREFIX:
        for position in POSITIONS:
            for year in years:
                log.info("Fetching %s %s year=%d", scoring, position, year)
                try:
                    df = fetch_adp(position=position, scoring=scoring, year=year)
                    df.insert(0, "year", year)
                    df.insert(0, "position", position)
                    df.insert(0, "scoring", scoring)
                    path = out_dir / f"fantasypros_adp_{scoring}_{position}_{year}.parquet"
                    df.to_parquet(path, index=False)
                    log.info("Saved %d rows -> %s", len(df), path)
                except Exception as exc:
                    log.warning("Skipped %s %s %d: %s", scoring, position, year, exc)
                time.sleep(0.5)


if __name__ == "__main__":
    main()
