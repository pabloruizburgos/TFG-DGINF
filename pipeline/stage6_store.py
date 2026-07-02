"""
stage6_store.py — Etapa 6: Almacenamiento y explotación.

Persiste los resultados validados en formato JSONL (una línea por artículo)
y exporta un CSV aplanado para análisis posteriores.

Decisión de diseño: JSONL + CSV en lugar de base de datos relacional.
Con un corpus de 15-20 artículos, una BBDD añadiría infraestructura sin
ventaja práctica sobre ficheros planos. Los ficheros son además más
transparentes para inspección manual durante el desarrollo (ver §3/§6 NOTAS).
"""

import csv
import json
import logging
import os
from datetime import datetime, timezone
from typing import TypedDict

from config import CSV_FILENAME, JSONL_FILENAME, OUTPUT_DIR
from stage4_extract import ExtractionResult
from stage5_validate import ValidationResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipo de salida
# ---------------------------------------------------------------------------
class StorageResult(TypedDict):
    jsonl_path: str
    csv_path: str
    record_id: str   # article_id + extraction_type (clave del registro guardado)


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def store(
    extraction: ExtractionResult,
    validation: ValidationResult,
    output_dir: str = OUTPUT_DIR,
) -> StorageResult:
    """
    Guarda el resultado de la extracción en JSONL y actualiza el CSV.

    Args:
        extraction:  resultado de Stage 4
        validation:  resultado de Stage 5
        output_dir:  directorio de salida (se crea si no existe)

    Returns:
        StorageResult con las rutas de los ficheros de salida.
    """
    os.makedirs(output_dir, exist_ok=True)
    jsonl_path = os.path.join(output_dir, JSONL_FILENAME)
    csv_path = os.path.join(output_dir, CSV_FILENAME)

    record = _build_record(extraction, validation)

    _append_jsonl(record, jsonl_path)
    _upsert_csv(record, csv_path)

    record_id = f"{extraction['article_id']}:{extraction['extraction_type']}"
    logger.info(f"Guardado: {record_id} → {jsonl_path}")

    return StorageResult(
        jsonl_path=jsonl_path,
        csv_path=csv_path,
        record_id=record_id,
    )


# ---------------------------------------------------------------------------
# Construcción del registro
# ---------------------------------------------------------------------------
def _build_record(extraction: ExtractionResult, validation: ValidationResult) -> dict:
    """Combina extracción + validación en un dict plano para almacenamiento."""
    return {
        "article_id": extraction["article_id"],
        "extraction_type": extraction["extraction_type"],
        "schema_version": extraction["schema_version"],
        "model_used": extraction["model_used"],
        "validation_status": validation["status"],
        "missing_fields": validation["missing_fields"],
        "low_confidence_fields": validation["low_confidence"],
        "warnings": validation["warnings"],
        "errors": validation["errors"],
        "extracted": extraction["extracted"],
        "input_tokens": extraction["input_tokens"],
        "output_tokens": extraction["output_tokens"],
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# JSONL — un registro por línea
# ---------------------------------------------------------------------------
def _append_jsonl(record: dict, path: str) -> None:
    """Añade el registro al fichero JSONL (una línea JSON por registro)."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# CSV — aplanado de campos extraídos para análisis tabular
# ---------------------------------------------------------------------------
_CSV_BASE_FIELDS = [
    "article_id",
    "extraction_type",
    "validation_status",
    "model_used",
    "timestamp_utc",
    "input_tokens",
    "output_tokens",
]

# Campos extraídos que se "aplanan" en el CSV: field_value, field_confidence
_ABSTRACT_EXTRACTED_FIELDS = [
    "study_type",
    "study_design_temporality",
    "sample_size_estimated",
    "main_topic",
    "clinical_focus",
]

_TABLE_EXTRACTED_FIELDS = [
    "population_description",
    "n_total",
    "primary_outcome",
    "between_group_comparison",
]


def _upsert_csv(record: dict, path: str) -> None:
    """
    Añade el registro al CSV. La fila se aplana: para cada campo extraído
    se crean columnas {campo}_value y {campo}_confidence.
    Los valores anidados (primary_outcome, between_group_comparison) se
    serializan como JSON string dentro de la celda.
    """
    extraction_type = record["extraction_type"]
    extracted = record.get("extracted", {})

    if extraction_type == "abstract":
        field_names = _ABSTRACT_EXTRACTED_FIELDS
    else:
        field_names = _TABLE_EXTRACTED_FIELDS

    # Construir la fila aplanada
    row: dict = {f: record.get(f, "") for f in _CSV_BASE_FIELDS}
    row["missing_fields"] = "|".join(record.get("missing_fields", []))
    row["warnings_count"] = len(record.get("warnings", []))

    for field in field_names:
        field_data = extracted.get(field, {})
        value = field_data.get("value") if isinstance(field_data, dict) else None
        confidence = field_data.get("confidence", "") if isinstance(field_data, dict) else ""

        # Serializar objetos anidados (primary_outcome, between_group_comparison)
        if isinstance(value, dict):
            value = json.dumps(value, ensure_ascii=False)

        row[f"{field}_value"] = value if value is not None else ""
        row[f"{field}_confidence"] = confidence

    # Escribir cabecera si el CSV es nuevo
    fieldnames = list(row.keys())
    write_header = not os.path.exists(path) or os.path.getsize(path) == 0

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# ---------------------------------------------------------------------------
# Utilidades de lectura (para evaluación y análisis)
# ---------------------------------------------------------------------------
def load_jsonl(path: str) -> list[dict]:
    """Carga todos los registros del fichero JSONL."""
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records
