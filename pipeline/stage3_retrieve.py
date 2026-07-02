"""
stage3_retrieve.py — Etapa 3: Recuperación basada en reglas por sección.

Selecciona los chunks relevantes para un tipo de extracción dado,
aplicando un mapeo determinista: tipo_extracción → secciones_objetivo.

NO se usa búsqueda semántica ni embeddings. El mapeo es posible porque
los artículos de intervención clínica siguen el formato IMRAD de forma
consistente (ver §3 y nota crítica [C] en NOTAS_PROYECTO_INF.md).

Tipos de extracción soportados:
  - "abstract": solo usa el chunk de abstract
  - "table":    usa secciones de Methods + Results + todos los chunks de tabla
"""

import logging
from typing import Literal

from config import ALWAYS_INCLUDE_TABLES_FOR_TABLE_EXTRACTION, SECTION_RULES
from stage2_chunk import Chunk

logger = logging.getLogger(__name__)

ExtractionType = Literal["abstract", "table"]

# Palabras clave para identificar secciones de Methods y Results por variantes léxicas.
# Se compara con la sección normalizada del chunk (minúsculas, sin caracteres especiales).
_METHODS_KEYWORDS = frozenset({
    "method", "methods", "material", "materials",
    "patient", "patients", "participants", "subjects",
    "study_design", "methodology", "design",
    "materials_and_methods", "patients_and_methods",
})
_RESULTS_KEYWORDS = frozenset({
    "result", "results", "finding", "findings",
    "outcome", "outcomes",
})
_ABSTRACT_KEYWORDS = frozenset({"abstract"})


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def retrieve(chunks: list[Chunk], extraction_type: ExtractionType) -> list[Chunk]:
    """
    Filtra y devuelve los chunks relevantes para el tipo de extracción indicado.

    Args:
        chunks:          lista completa de chunks del artículo (salida de Stage 2)
        extraction_type: "abstract" o "table"

    Returns:
        Subconjunto de chunks relevantes, en el orden en que aparecen en el artículo.
    """
    if extraction_type == "abstract":
        return _retrieve_for_abstract(chunks)
    elif extraction_type == "table":
        return _retrieve_for_table(chunks)
    else:
        raise ValueError(f"Tipo de extracción desconocido: '{extraction_type}'")


# ---------------------------------------------------------------------------
# Estrategias por tipo
# ---------------------------------------------------------------------------
def _retrieve_for_abstract(chunks: list[Chunk]) -> list[Chunk]:
    """
    Para clasificación del abstract: devuelve el chunk de abstract.
    Si no hay abstract explícito, usa el chunk de introducción como fallback.
    """
    abstract_chunks = [c for c in chunks if c["section"] == "abstract"]
    if abstract_chunks:
        logger.info(f"Recuperación abstract: {len(abstract_chunks)} chunk(s) de abstract.")
        return abstract_chunks

    # Fallback: si no hay abstract, usar introducción
    intro_chunks = [
        c for c in chunks
        if c["type"] == "text" and _matches_keywords(c["section"], {"introduction", "background"})
    ]
    if intro_chunks:
        logger.warning("No hay chunk de abstract; usando introducción como fallback.")
        return intro_chunks[:1]  # solo el primero

    logger.warning("No se encontró abstract ni introducción.")
    return []


def _retrieve_for_table(chunks: list[Chunk]) -> list[Chunk]:
    """
    Para extracción de tabla: devuelve chunks de Methods + Results + todas las tablas.
    """
    selected: list[Chunk] = []

    for chunk in chunks:
        norm = chunk["section"]
        # Incluir siempre las tablas
        if chunk["type"] == "table" and ALWAYS_INCLUDE_TABLES_FOR_TABLE_EXTRACTION:
            selected.append(chunk)
            continue
        # Incluir secciones de Methods y Results
        if chunk["type"] == "text":
            if _matches_keywords(norm, _METHODS_KEYWORDS) or _matches_keywords(norm, _RESULTS_KEYWORDS):
                selected.append(chunk)

    logger.info(
        f"Recuperación table: {len(selected)} chunks seleccionados "
        f"({sum(1 for c in selected if c['type'] == 'table')} tablas, "
        f"{sum(1 for c in selected if c['type'] == 'text')} texto)."
    )
    return selected


# ---------------------------------------------------------------------------
# Utilidad de matching
# ---------------------------------------------------------------------------
def _matches_keywords(section_normalized: str, keywords: frozenset[str]) -> bool:
    """
    Comprueba si la sección normalizada contiene alguna de las palabras clave.
    Usa contains (no equals) para manejar variantes como "materials_and_methods".
    """
    return any(kw in section_normalized for kw in keywords)


def build_context_text(chunks: list[Chunk]) -> str:
    """
    Concatena el contenido de los chunks recuperados en un texto plano
    para enviar como contexto al LLM en Stage 4.

    Cada chunk incluye un encabezado con su tipo y sección para orientar al modelo.
    """
    parts: list[str] = []
    for chunk in chunks:
        header = f"[{chunk['type'].upper()} — {chunk['section_original']}]"
        parts.append(f"{header}\n{chunk['content']}")
    return "\n\n---\n\n".join(parts)
