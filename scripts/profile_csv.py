from pathlib import Path
from ingestion.sources.csv_contracts import CONTRACTS, read_checked_csv

def build_inventory(input_dir: Path):
    inventory = []
    for table in CONTRACTS:
        records, metadata = read_checked_csv(input_dir / f"{table}.csv", table)
        inventory.append(metadata)
        del records
    return inventory