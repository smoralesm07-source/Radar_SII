from pathlib import Path

import duckdb
import pandas as pd

from radar_sii.query_job import query_parquet


def test_query_ownership_by_partner_and_percent(tmp_path: Path):
    path = tmp_path / "ownership.parquet"
    df = pd.DataFrame([
        {"entity_id": "ENT-RUT-11111111-1", "rut": "11111111-1", "partner_rut": "76086428-5", "partner_entity_id": "ENT-RUT-76086428-5", "partner_id_type": "RUT", "ownership_percent": 60.0, "society_type": "SOCIEDAD", "society_subtype": "SPA"},
        {"entity_id": "ENT-RUT-22222222-2", "rut": "22222222-2", "partner_rut": "", "partner_entity_id": None, "partner_id_type": "NATURAL_PERSONS_AGGREGATE", "ownership_percent": 100.0, "society_type": "SOCIEDAD", "society_subtype": "LTDA"},
    ])
    con = duckdb.connect()
    con.register("df", df)
    con.execute(f"COPY df TO '{str(path)}' (FORMAT PARQUET)")
    out = query_parquet(path, "", {"partner_rut": "76086428-5", "min_ownership_percent": 50}, 100)
    assert len(out) == 1
    assert out.iloc[0]["partner_entity_id"] == "ENT-RUT-76086428-5"
