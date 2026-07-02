"""
stage2_chunk.py — Etapa 2: Chunking e indexación.

Divide la salida de Stage 1 en unidades recuperables (chunks).
Cada sección del artículo → un chunk de tipo "text".
Cada tabla → un chunk de tipo "table".

No hay embeddings ni índice vectorial: la recuperación es determinista por sección
(Stage 3). La ausencia de embeddings es una decisión de diseño explícita —
justificada en §3 de NOTAS_PROYECTO_INF.md.
"""

import json
import logging
import re
from typing import TypedDict

from stage1_parse import ParsedDocument, SectionRecord, TableRecord

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipo de salida
# ---------------------------------------------------------------------------
class Chunk(TypedDict):
    chunk_id: str        # único en el corpus, p.ej. "PMID12345_methods_0"
    article_id: str
    type: str            # "text" | "table"
    section: str         # nombre de sección normalizado (minúsculas)
    section_original: str  # nombre tal como aparece en el artículo
    content: str         # texto plano (para chunks de tipo "text")
    content_structured: dict | None  # parsed_table (para chunks de tipo "table"), None si es texto


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def chunk(doc: ParsedDocument) -> list[Chunk]:
    """
    Convierte un ParsedDocument en una lista de Chunk.

    Args:
        doc: salida de Stage 1.

    Returns:
        Lista de chunks con metadatos. Si el abstract está disponible,
        se genera también un chunk de tipo "text" con sección "abstract".
    """
    chunks: list[Chunk] = []
    article_id = doc["article_id"]
    safe_id = _safe_id(article_id)

    # Chunk del abstract (si está disponible desde Stage 0 o Stage 1)
    if doc.get("abstract"):
        chunks.append(Chunk(
            chunk_id=f"{safe_id}_abstract",
            article_id=article_id,
            type="text",
            section="abstract",
            section_original="Abstract",
            content=doc["abstract"],
            content_structured=None,
        ))

    # Chunks de secciones de texto
    section_counters: dict[str, int] = {}
    for sec in doc["sections"]:
        norm = _normalize_section(sec["section"])
        idx = section_counters.get(norm, 0)
        section_counters[norm] = idx + 1
        suffix = f"_{idx}" if idx > 0 else ""

        chunks.append(Chunk(
            chunk_id=f"{safe_id}_{norm}{suffix}",
            article_id=article_id,
            type="text",
            section=norm,
            section_original=sec["section"],
            content=sec["text"],
            content_structured=None,
        ))

    # Chunks de tablas
    for i, table in enumerate(doc["tables"]):
        table_norm = f"table_{i + 1}"
        # El contenido de texto de una tabla es: caption + raw_content
        content_text = f"[{table['table_id']}] {table['caption']}\n\n{table['raw_content']}"

        chunks.append(Chunk(
            chunk_id=f"{safe_id}_{table_norm}",
            article_id=article_id,
            type="table",
            section=_normalize_section(table["section"]),
            section_original=table["section"],
            content=content_text,
            content_structured={
                "table_id": table["table_id"],
                "caption": table["caption"],
                "parsed_table": table["parsed_table"],
            },
        ))

    logger.info(
        f"Chunking completado para {article_id}: "
        f"{len(chunks)} chunks ({sum(1 for c in chunks if c['type'] == 'text')} texto, "
        f"{sum(1 for c in chunks if c['type'] == 'table')} tabla)."
    )
    return chunks


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def _normalize_section(name: str) -> str:
    """
    Normaliza el nombre de sección a minúsculas sin caracteres especiales.
    Facilita el matching en Stage 3.
    """
    return re.sub(r"[^a-z0-9_]", "_", name.lower().strip()).strip("_")


def _safe_id(article_id: str) -> str:
    """Convierte un article_id en un string seguro para chunk_ids."""
    return re.sub(r"[^a-zA-Z0-9]", "", article_id)
