"""
pipeline.py — Orquestador del pipeline RAG.

Coordina la ejecución secuencial de las 7 etapas (0 a 6) para un artículo dado.
Soporta tres modos de operación:
  - "abstract": clasifica el abstract (Etapas 0, 4, 5, 6)
  - "table":    extrae datos de tabla (Etapas 0, 1, 2, 3, 4, 5, 6)
  - "full":     ejecuta ambos modos y almacena dos registros

Uso básico:
    python pipeline.py --id "PMID:12345678" --mode full
"""

import argparse
import logging
import os
import sys
from typing import Literal

from config import LOG_LEVEL, LLM_MODEL, OUTPUT_DIR
from stage0_ingest import ingest
from stage1_parse import parse
from stage2_chunk import chunk
from stage3_retrieve import retrieve
from stage4_extract import extract
from stage5_validate import validate
from stage6_store import store

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

PipelineMode = Literal["abstract", "table", "full"]


# ---------------------------------------------------------------------------
# Función principal del pipeline
# ---------------------------------------------------------------------------
def run(
    identifier: str,
    mode: PipelineMode = "full",
    model: str = LLM_MODEL,
    output_dir: str = OUTPUT_DIR,
    download_pdf: bool = True,
) -> dict:
    """
    Ejecuta el pipeline completo para un artículo.

    Args:
        identifier:   PMID, DOI, ruta a PDF, o texto de abstract
        mode:         "abstract" | "table" | "full"
        model:        modelo de Claude a usar
        output_dir:   directorio de salida para JSONL y CSV
        download_pdf: si True, intenta descargar el PDF en Stage 0

    Returns:
        Dict con los resultados de cada etapa ejecutada.
    """
    results: dict = {"identifier": identifier, "mode": mode, "stages": {}}

    # ── Etapa 0: Ingesta ──────────────────────────────────────────────────
    logger.info(f"═══ Etapa 0 — Ingesta: {identifier} ═══")
    article = ingest(identifier, download_pdf=download_pdf, output_dir=os.path.join(output_dir, "pdfs"))
    results["stages"]["stage0"] = {"article_id": article["article_id"], "source": article["source"]}
    logger.info(f"Article ID: {article['article_id']} | Fuente: {article['source']}")

    # ── Extracción del abstract ────────────────────────────────────────────
    if mode in ("abstract", "full"):
        _run_abstract_pipeline(article, model, output_dir, results)

    # ── Extracción de tabla ────────────────────────────────────────────────
    if mode in ("table", "full"):
        _run_table_pipeline(article, model, output_dir, results)

    logger.info(f"Pipeline completado para {article['article_id']} (modo: {mode})")
    return results


# ---------------------------------------------------------------------------
# Sub-pipelines por modo
# ---------------------------------------------------------------------------
def _run_abstract_pipeline(article, model, output_dir, results):
    """Ejecuta Etapas 4–6 para el modo abstract (sin GROBID)."""
    article_id = article["article_id"]

    if not article.get("abstract"):
        logger.warning(f"No hay abstract disponible para {article_id}. Omitiendo modo abstract.")
        results["stages"]["abstract"] = {"skipped": True, "reason": "no abstract available"}
        return

    # Stage 4: Extracción — usando el abstract directamente como chunk único
    logger.info(f"═══ Etapa 4 — Extracción abstract: {article_id} ═══")
    from stage2_chunk import Chunk
    abstract_chunk = Chunk(
        chunk_id=f"{article_id}_abstract_direct",
        article_id=article_id,
        type="text",
        section="abstract",
        section_original="Abstract",
        content=article["abstract"],
        content_structured=None,
    )
    extraction = extract(article_id, [abstract_chunk], "abstract", model=model)

    # Stage 5: Validación
    logger.info(f"═══ Etapa 5 — Validación abstract: {article_id} ═══")
    validation = validate(extraction)

    # Stage 6: Almacenamiento
    logger.info(f"═══ Etapa 6 — Almacenamiento abstract: {article_id} ═══")
    storage = store(extraction, validation, output_dir)

    results["stages"]["abstract"] = {
        "validation_status": validation["status"],
        "missing_fields": validation["missing_fields"],
        "storage": storage,
    }


def _run_table_pipeline(article, model, output_dir, results):
    """Ejecuta Etapas 1–6 para el modo table (requiere PDF y GROBID)."""
    article_id = article["article_id"]

    if not article.get("pdf_path"):
        logger.warning(f"No hay PDF disponible para {article_id}. Omitiendo modo table.")
        results["stages"]["table"] = {"skipped": True, "reason": "no PDF available"}
        return

    # Stage 1: Parseo
    logger.info(f"═══ Etapa 1 — Parseo GROBID: {article_id} ═══")
    parsed_doc = parse(article_id, article["pdf_path"], existing_abstract=article.get("abstract"))

    # Stage 2: Chunking
    logger.info(f"═══ Etapa 2 — Chunking: {article_id} ═══")
    chunks = chunk(parsed_doc)

    # Stage 3: Recuperación
    logger.info(f"═══ Etapa 3 — Recuperación: {article_id} ═══")
    retrieved = retrieve(chunks, "table")

    if not retrieved:
        logger.warning(f"No se recuperaron chunks para extracción de tabla en {article_id}.")
        results["stages"]["table"] = {"skipped": True, "reason": "no relevant chunks found"}
        return

    # Stage 4: Extracción
    logger.info(f"═══ Etapa 4 — Extracción tabla: {article_id} ═══")
    extraction = extract(article_id, retrieved, "table", model=model)

    # Stage 5: Validación
    logger.info(f"═══ Etapa 5 — Validación tabla: {article_id} ═══")
    validation = validate(extraction)

    # Stage 6: Almacenamiento
    logger.info(f"═══ Etapa 6 — Almacenamiento tabla: {article_id} ═══")
    storage = store(extraction, validation, output_dir)

    results["stages"]["table"] = {
        "chunks_total": len(chunks),
        "chunks_retrieved": len(retrieved),
        "validation_status": validation["status"],
        "missing_fields": validation["missing_fields"],
        "storage": storage,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pipeline RAG para extracción de información de artículos de alergología"
    )
    parser.add_argument(
        "--id",
        required=True,
        help="Identificador del artículo: PMID:xxx, DOI:xxx, ruta a PDF, o abstract de texto",
    )
    parser.add_argument(
        "--mode",
        choices=["abstract", "table", "full"],
        default="full",
        help="Modo de extracción (default: full)",
    )
    parser.add_argument(
        "--model",
        default=LLM_MODEL,
        help=f"Modelo de Claude a usar (default: {LLM_MODEL})",
    )
    parser.add_argument(
        "--output-dir",
        default=OUTPUT_DIR,
        help=f"Directorio de salida (default: {OUTPUT_DIR})",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="No descargar el PDF aunque esté disponible",
    )

    args = parser.parse_args()

    result = run(
        identifier=args.id,
        mode=args.mode,
        model=args.model,
        output_dir=args.output_dir,
        download_pdf=not args.no_download,
    )

    import json
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
