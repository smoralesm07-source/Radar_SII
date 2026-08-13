from __future__ import annotations

import json
import sys
from pathlib import Path

CORE_SOURCES = {
    "sii_company_year": 3_000_000,
    "sii_names_current": 2_500_000,
    "sii_activities_current": 3_000_000,
    "sii_addresses_history": 4_000_000,
    "sii_ownership_current": 1_000_000,
}
EXPECTED_YEARS = [2020, 2021, 2022, 2023, 2024]
EXPECTED_COMPANY_MEMBERS = {f"PUB_EMPRESAS_PJ_{year}.txt" for year in EXPECTED_YEARS}


def load_json(root: Path, name: str):
    path = root / name
    if not path.exists():
        raise AssertionError(f"Falta artefacto obligatorio: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/data")
    dashboard = load_json(root, "dashboard.json")
    coverage = load_json(root, "coverage.json")
    quality = load_json(root, "quality.json")
    manifest = load_json(root, "snapshot_manifest.json")
    catalog = load_json(root, "source_catalog.json")

    processed = set(coverage.get("sources_processed", []))
    assert set(CORE_SOURCES) <= processed, f"Fuentes core incompletas: {processed}"
    rows = coverage.get("source_rows", {})
    for source_id, minimum in CORE_SOURCES.items():
        observed = int(rows.get(source_id, 0) or 0)
        assert observed >= minimum, f"{source_id}: filas insuficientes {observed:,} < {minimum:,}"

    assert coverage.get("history_complete") is True, "Historia empresa-año marcada incompleta"
    assert coverage.get("company_years") == EXPECTED_YEARS, coverage.get("company_years")
    assert int(coverage.get("company_year_stable_conflict_groups", 1) or 0) == 0, "Conflictos materiales empresa-año"
    assert int(coverage.get("entities_searchable", 0) or 0) >= 2_500_000, "Índice de entidades incompleto"
    assert int(coverage.get("signals", 0) or 0) > 0, "No se generaron señales"
    assert int(coverage.get("ownership_edges", 0) or 0) >= 1_000_000, "Relaciones societarias incompletas"

    cyq = quality.get("company_year", {})
    assert cyq.get("years") == EXPECTED_YEARS, cyq.get("years")
    assert int(cyq.get("duplicate_entity_year_rows", 1) or 0) == 0, "Capa canónica empresa-año no es única"
    assert float(cyq.get("key_coverage", 0) or 0) >= 0.999, "Cobertura de claves empresa-año insuficiente"
    assert float(quality.get("entity_search", {}).get("key_coverage", 0) or 0) >= 0.999, "Índice de búsqueda sin claves suficientes"

    kpis = dashboard.get("kpis", {})
    assert int(kpis.get("entities", 0) or 0) == int(coverage["entities_searchable"]), "KPIs/coverage desalineados: entities"
    assert int(kpis.get("signals", 0) or 0) == int(coverage["signals"]), "KPIs/coverage desalineados: signals"
    assert int(kpis.get("ownership_edges", 0) or 0) == int(coverage["ownership_edges"]), "KPIs/coverage desalineados: ownership"
    assert int(kpis.get("active_as_published", 0) or 0) > 0, "Estado registral activo en cero"

    manifest_by_id = {item.get("source_id"): item for item in manifest}
    for source_id in CORE_SOURCES:
        item = manifest_by_id.get(source_id)
        assert item, f"Falta manifest para {source_id}"
        assert item.get("content_type") == "application/zip", f"Content-Type inesperado para {source_id}"
        assert int(item.get("bytes", 0) or 0) > 1_000_000, f"Descarga sospechosamente pequeña: {source_id}"
        assert len(str(item.get("sha256", ""))) == 64, f"SHA-256 inválido: {source_id}"
        assert int(item.get("normalized_rows", 0) or 0) == int(rows[source_id]), f"Manifest/coverage desalineados: {source_id}"

    cy_members = set(manifest_by_id["sii_company_year"].get("selected_members", []))
    assert cy_members == EXPECTED_COMPANY_MEMBERS, f"ZIP empresa-año incompleto: {sorted(cy_members)}"
    assert len(catalog) >= len(CORE_SOURCES), "Catálogo de fuentes incompleto"

    print("Radar SII publish validation: OK")
    print(json.dumps({
        "entities": kpis["entities"],
        "active": kpis["active_as_published"],
        "signals": kpis["signals"],
        "ownership_edges": kpis["ownership_edges"],
        "company_years": coverage["company_years"],
        "source_rows": rows,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
