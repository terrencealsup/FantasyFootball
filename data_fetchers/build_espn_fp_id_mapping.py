"""Build a mapping between ESPN player IDs and FantasyPros player IDs.

Matches on normalized player name + position. DST is handled separately
by matching the team nickname (e.g. "Browns" from ESPN's "Browns D/ST"
against the last word of FP's full team name "Cleveland Browns").

Output: data/processed/espn_fp_id_mapping.parquet
"""

import glob
import logging
import re
from difflib import get_close_matches
from pathlib import Path

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "data"

_SUFFIX_RE = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b\.?\s*$")
_PUNCT_RE = re.compile(r"[^a-z0-9 ]")


def _normalize(name: str) -> str:
    if not isinstance(name, str):
        return ""
    name = name.lower().strip()
    name = _PUNCT_RE.sub(" ", name)
    name = _SUFFIX_RE.sub("", name)
    return re.sub(r"\s+", " ", name).strip()


def _dst_key(name: str) -> str:
    """Extract team nickname for DST matching.

    ESPN: "Browns D/ST" -> "browns"
    FP:   "Cleveland Browns" -> "browns"
    """
    name = re.sub(r"d/st", "", name, flags=re.IGNORECASE).strip()
    return _normalize(name.split()[-1]) if name else ""


def load_espn_players() -> pd.DataFrame:
    files = sorted(glob.glob(str(DATA_DIR / "raw/espn_projections/espn_projections_season_*.parquet")))
    df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    # Keep the most recent year's record for each espn_id
    df = df.sort_values("year").drop_duplicates("espn_id", keep="last")
    df = df[["espn_id", "player_name", "position"]].copy()
    return df.reset_index(drop=True)


def load_fp_players() -> pd.DataFrame:
    # Use positional pages: qb/k/dst only have standard; rb/wr/te use half_ppr
    specs = [
        ("standard", ["qb", "k", "dst"]),
        ("half_ppr", ["rb", "wr", "te"]),
    ]
    frames = []
    for scoring, positions in specs:
        for pos in positions:
            files = sorted(glob.glob(
                str(DATA_DIR / f"raw/fantasypros_adp/fantasypros_adp_{scoring}_{pos}_*.parquet")
            ))
            for f in files:
                df = pd.read_parquet(f)
                if "year" not in df.columns:
                    df["year"] = int(Path(f).stem.rsplit("_", 1)[-1])
                df = df[["fp_id", "player", "year"]]
                df["position"] = pos.upper()
                frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values("year").drop_duplicates("fp_id", keep="last")
    return df[["fp_id", "player", "position"]].rename(columns={"player": "player_name"}).reset_index(drop=True)


def build_mapping(espn: pd.DataFrame, fp: pd.DataFrame) -> pd.DataFrame:
    espn_dst = espn[espn["position"] == "DST"].copy()
    espn_skill = espn[espn["position"] != "DST"].copy()
    fp_dst = fp[fp["position"] == "DST"].copy()
    fp_skill = fp[fp["position"] != "DST"].copy()

    rows = []

    # --- Skill players: normalize name + match on (norm_name, position) ---
    espn_skill["norm"] = espn_skill["player_name"].map(_normalize)
    fp_skill["norm"] = fp_skill["player_name"].map(_normalize)

    fp_by_name_pos = {(r.norm, r.position): r for r in fp_skill.itertuples()}
    fp_by_name = {}
    for r in fp_skill.itertuples():
        fp_by_name.setdefault(r.norm, r)

    # Build per-position norm lists for fuzzy matching (same-position only)
    fp_norms_by_pos = fp_skill.groupby("position")["norm"].apply(list).to_dict()
    unmatched = []

    for e in espn_skill.itertuples():
        if (e.norm, e.position) in fp_by_name_pos:
            f = fp_by_name_pos[(e.norm, e.position)]
            rows.append((e.espn_id, f.fp_id, e.player_name, e.position, "exact"))
        elif e.norm in fp_by_name:
            f = fp_by_name[e.norm]
            rows.append((e.espn_id, f.fp_id, e.player_name, e.position, "exact_name_only"))
        else:
            unmatched.append(e)

    # Fuzzy fallback: same position only, higher cutoff to avoid false positives
    for e in unmatched:
        candidates = fp_norms_by_pos.get(e.position, [])
        hits = get_close_matches(e.norm, candidates, n=1, cutoff=0.92)
        if hits:
            f = fp_skill[(fp_skill["norm"] == hits[0]) & (fp_skill["position"] == e.position)].iloc[0]
            rows.append((e.espn_id, f.fp_id, e.player_name, e.position, "fuzzy"))
        else:
            rows.append((e.espn_id, None, e.player_name, e.position, "unmatched"))

    # --- DST: match on team nickname ---
    espn_dst["dst_key"] = espn_dst["player_name"].map(_dst_key)
    fp_dst["dst_key"] = fp_dst["player_name"].map(_dst_key)
    fp_dst_by_key = {r.dst_key: r for r in fp_dst.itertuples()}

    for e in espn_dst.itertuples():
        if e.dst_key in fp_dst_by_key:
            f = fp_dst_by_key[e.dst_key]
            rows.append((e.espn_id, f.fp_id, e.player_name, "DST", "exact_dst"))
        else:
            rows.append((e.espn_id, None, e.player_name, "DST", "unmatched"))

    df = pd.DataFrame(rows, columns=["espn_id", "fp_id", "player_name", "position", "match_type"])
    df["espn_id"] = df["espn_id"].astype("Int64")
    df["fp_id"] = df["fp_id"].astype("Int64")
    return df.sort_values(["position", "player_name"]).reset_index(drop=True)


def main():
    log.info("Loading ESPN players...")
    espn = load_espn_players()
    log.info("  %d unique ESPN players", len(espn))

    log.info("Loading FantasyPros players...")
    fp = load_fp_players()
    log.info("  %d unique FP players", len(fp))

    log.info("Matching...")
    mapping = build_mapping(espn, fp)

    counts = mapping["match_type"].value_counts()
    log.info("Match results:\n%s", counts.to_string())

    unmatched = mapping[mapping["match_type"] == "unmatched"]
    if len(unmatched):
        log.info("Unmatched ESPN players (%d):\n%s", len(unmatched),
                 unmatched[["player_name", "position"]].to_string(index=False))

    out_dir = DATA_DIR / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "espn_fp_id_mapping.parquet"
    mapping.to_parquet(path, index=False)
    log.info("Saved %d rows -> %s", len(mapping), path)


if __name__ == "__main__":
    main()
