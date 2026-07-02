"""
stage5_validate.py — Etapa 5: Validación y control de calidad.

Valida el JSON generado por Stage 4 contra el schema correspondiente
e identifica campos nulos, niveles de confianza bajos e incoherencias básicas.

Usa la librería `jsonschema` para la validación estructural.
"""

import logging
from typing import TypedDict

import jsonschema

from schemas import ABSTRACT_SCHEMA, TABLE_SCHEMA
from stage4_extract import ExtractionResult

logger = logging.getLogger(__name__)

_SCHEMAS = {"abstract": ABSTRACT_SCHEMA, "table": TABLE_SCHEMA}


# ---------------------------------------------------------------------------
# Tipo de salida
# ---------------------------------------------------------------------------
class ValidationResult(TypedDict):
    article_id: str
    extraction_type: str
    status: str             # "valid" | "valid_with_warnings" | "invalid"
    missing_fields: list[str]    # campos con value=null
    low_confidence: list[str]    # campos con confidence="low"
    warnings: list[str]
    errors: list[str]


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def validate(result: ExtractionResult) -> ValidationResult:
    """
    Valida el ExtractionResult de Stage 4.

    Args:
        result: resultado de la extracción LLM

    Returns:
        ValidationResult con el estado de validación y los avisos encontrados.
    """
    article_id = result["article_id"]
    extraction_type = result["extraction_type"]
    extracted = result["extracted"]
    schema = _SCHEMAS.get(extraction_type)

    errors: list[str] = []
    warnings: list[str] = []
    missing_fields: list[str] = []
    low_confidence: list[str] = []

    # 1. Validación estructural contra el JSON Schema
    if schema:
        validator = jsonschema.Draft7Validator(schema)
        for error in validator.iter_errors(extracted):
            errors.append(f"Schema error en '{error.json_path}': {error.message}")
    else:
        warnings.append(f"No hay schema disponible para el tipo '{extraction_type}'")

    # 2. Análisis campo a campo: nulls y confianza baja
    for field_name, field_value in extracted.items():
        if not isinstance(field_value, dict):
            continue
        value = field_value.get("value")
        confidence = field_value.get("confidence", "")
        evidence = field_value.get("evidence")

        if value is None:
            missing_fields.append(field_name)

        if confidence == "low":
            low_confidence.append(field_name)
            warnings.append(f"Campo '{field_name}' tiene confianza baja.")

        # Evidence no debería ser null si value no es null
        if value is not None and not evidence:
            warnings.append(
                f"Campo '{field_name}' tiene valor pero evidence es null o vacío."
            )

    # 3. Determinar estado final
    if errors:
        status = "invalid"
    elif warnings:
        status = "valid_with_warnings"
    else:
        status = "valid"

    logger.info(
        f"Validación {article_id} ({extraction_type}): {status}. "
        f"Nulos: {len(missing_fields)}, confianza baja: {len(low_confidence)}, "
        f"errores: {len(errors)}."
    )

    return ValidationResult(
        article_id=article_id,
        extraction_type=extraction_type,
        status=status,
        missing_fields=missing_fields,
        low_confidence=low_confidence,
        warnings=warnings,
        errors=errors,
    )
