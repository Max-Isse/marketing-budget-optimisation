"""Output manifest: a SHA-256 hash of every generated, committed output.

`mbo manifest` (the last step of `mbo all`) writes `reports/manifest.csv`. `mbo verify` re-hashes the files and
reports any that differ, are missing or are not listed, which catches hand edits and stale outputs in
seconds. `mbo reproduce` keeps the committed manifest, rebuilds everything and checks the new outputs against
it, which shows the whole pipeline is deterministic.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from marketing_budget.config import Config

MANIFEST = "manifest.csv"
# generated documents that live outside reports/ and dashboard/data/
GENERATED_DOCS = ("model_card.md", "monitoring_plan.md")
GENERATED_DASHBOARD = ("tieout.csv", "data_dictionary.csv")
BINARY = {".png", ".parquet"}


def output_files(cfg: Config) -> list[Path]:
    reports = cfg.path("reports_dir")
    dash = cfg.path("dashboard_dir")
    files = [p for p in reports.rglob("*") if p.is_file() and p.name != MANIFEST]
    files += [p for p in (dash / "data").glob("*") if p.is_file()]
    files += [dash / f for f in GENERATED_DASHBOARD if (dash / f).exists()]
    files += [cfg.path("docs_dir") / f for f in GENERATED_DOCS if (cfg.path("docs_dir") / f).exists()]
    return sorted(files)


def _content(p: Path) -> bytes:
    """File bytes with text line endings normalised, so Windows and Linux checkouts hash alike (.gitattributes)."""
    data = p.read_bytes()
    return data if p.suffix.lower() in BINARY else data.replace(b"\r\n", b"\n")


def hash_outputs(cfg: Config) -> pd.DataFrame:
    rows = []
    for p in output_files(cfg):
        data = _content(p)
        rows.append(
            {"path": p.relative_to(cfg.root).as_posix(), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )
    return pd.DataFrame(rows, columns=["path", "bytes", "sha256"])


def manifest_path(cfg: Config) -> Path:
    return cfg.path("reports_dir") / MANIFEST


def write_manifest(cfg: Config) -> Path:
    path = manifest_path(cfg)
    hash_outputs(cfg).to_csv(path, index=False, lineterminator="\n")
    return path


def read_manifest(cfg: Config) -> pd.DataFrame:
    path = manifest_path(cfg)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run `mbo all` first")
    return pd.read_csv(path)


def compare(expected: pd.DataFrame, actual: pd.DataFrame) -> pd.DataFrame:
    """Files whose hash differs, that are missing, or that are not in the expected manifest."""
    m = expected.merge(actual, on="path", how="outer", suffixes=("_expected", "_actual"), indicator=True)
    status = pd.Series("changed", index=m.index)
    status[m["_merge"] == "left_only"] = "missing"
    status[m["_merge"] == "right_only"] = "not in manifest"
    out = m.assign(status=status)
    out = out[(out["_merge"] != "both") | (out["sha256_expected"] != out["sha256_actual"])]
    return out[["path", "status"]].sort_values("path").reset_index(drop=True)


def verify(cfg: Config) -> pd.DataFrame:
    return compare(read_manifest(cfg), hash_outputs(cfg))
