"""
stage0_ingest.py — Etapa 0: Ingesta de artículos.

Recibe un identificador de artículo (PMID, DOI, ruta a PDF, o texto de abstract)
y devuelve un ArticleRecord normalizado con todos los campos que el pipeline necesita.

Fuentes soportadas:
  - PMID / DOI → consulta Europe PMC para metadatos + URL del PDF en acceso abierto
  - PDF (ruta local) → el PDF ya está disponible, se extrae solo el abstract si es posible
  - Abstract (texto plano) → se almacena directamente sin PDF

Dependencias externas:
  - requests (HTTP)
  - Europe PMC REST API (sin autenticación)
  - Unpaywall API (requiere email en UNPAYWALL_EMAIL)
"""

import logging
import os
import re
from pathlib import Path
from typing import TypedDict

import requests

from config import EUROPEPMC_SEARCH_URL, UNPAYWALL_EMAIL, UNPAYWALL_URL

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tipo de salida de esta etapa
# ---------------------------------------------------------------------------
class ArticleRecord(TypedDict):
    article_id: str           # "PMID:12345678" | "DOI:10.xxx/..." | "LOCAL:filename"
    source: str               # "europepmc" | "pdf_file" | "abstract_text"
    pdf_path: str | None      # ruta local al PDF descargado o proporcionado
    abstract: str | None      # texto del abstract
    title: str | None
    year: int | None
    doi: str | None


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def ingest(
    identifier: str,
    download_pdf: bool = True,
    output_dir: str = "./output/pdfs",
) -> ArticleRecord:
    """
    Punto de entrada de la Etapa 0.

    Args:
        identifier: puede ser "PMID:12345678", "DOI:10.xxx/...",
                    una ruta a un PDF local, o un texto de abstract.
        download_pdf: si True, intenta descargar el PDF cuando se resuelve
                      un PMID/DOI y hay versión open access disponible.
        output_dir: directorio donde guardar los PDFs descargados.

    Returns:
        ArticleRecord con todos los campos disponibles rellenados.
    """
    identifier = identifier.strip()

    if identifier.upper().startswith("PMID:"):
        pmid = identifier.split(":", 1)[1].strip()
        return _ingest_from_pmid(pmid, download_pdf, output_dir)

    if identifier.upper().startswith("DOI:"):
        doi = identifier.split(":", 1)[1].strip()
        return _ingest_from_doi(doi, download_pdf, output_dir)

    # Si parece una ruta a un archivo existente
    if os.path.isfile(identifier):
        return _ingest_from_pdf(identifier)

    # En cualquier otro caso lo tratamos como texto de abstract
    logger.info("Identificador no reconocido como PMID/DOI/ruta; tratando como abstract de texto plano.")
    return _ingest_from_abstract_text(identifier)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------
def _ingest_from_pmid(pmid: str, download_pdf: bool, output_dir: str) -> ArticleRecord:
    """Consulta Europe PMC por PMID y resuelve metadatos + PDF."""
    logger.info(f"Consultando Europe PMC para PMID:{pmid}")
    params = {
        "query": f"EXT_ID:{pmid} AND SRC:MED",
        "resultType": "core",
        "format": "json",
        "pageSize": 1,
    }
    try:
        resp = requests.get(EUROPEPMC_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"Error consultando Europe PMC: {e}")
        raise

    results = data.get("resultList", {}).get("result", [])
    if not results:
        raise ValueError(f"PMID:{pmid} no encontrado en Europe PMC.")

    article = results[0]
    record = _parse_europepmc_result(article, f"PMID:{pmid}", "europepmc")

    if download_pdf:
        pdf_path = _try_download_pdf(record, output_dir)
        record["pdf_path"] = pdf_path

    return record


def _ingest_from_doi(doi: str, download_pdf: bool, output_dir: str) -> ArticleRecord:
    """Consulta Europe PMC por DOI; si no hay PDF OA, intenta Unpaywall."""
    logger.info(f"Consultando Europe PMC para DOI:{doi}")
    params = {
        "query": f"DOI:{doi}",
        "resultType": "core",
        "format": "json",
        "pageSize": 1,
    }
    try:
        resp = requests.get(EUROPEPMC_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        logger.error(f"Error consultando Europe PMC: {e}")
        raise

    results = data.get("resultList", {}).get("result", [])
    record: ArticleRecord

    if results:
        record = _parse_europepmc_result(results[0], f"DOI:{doi}", "europepmc")
    else:
        logger.warning(f"DOI:{doi} no encontrado en Europe PMC. Creando registro mínimo.")
        record = ArticleRecord(
            article_id=f"DOI:{doi}",
            source="doi_only",
            pdf_path=None,
            abstract=None,
            title=None,
            year=None,
            doi=doi,
        )

    if download_pdf and record["pdf_path"] is None:
        pdf_url = _resolve_oa_pdf_via_unpaywall(doi)
        if pdf_url:
            record["pdf_path"] = _download_pdf(pdf_url, output_dir, doi.replace("/", "_"))

    return record


def _ingest_from_pdf(pdf_path: str) -> ArticleRecord:
    """Ingesta directa de un PDF local; abstract pendiente de extraer por GROBID."""
    logger.info(f"Ingesta de PDF local: {pdf_path}")
    filename = Path(pdf_path).stem
    return ArticleRecord(
        article_id=f"LOCAL:{filename}",
        source="pdf_file",
        pdf_path=pdf_path,
        abstract=None,  # GROBID lo extraerá en Stage 1
        title=None,
        year=None,
        doi=None,
    )


def _ingest_from_abstract_text(text: str) -> ArticleRecord:
    """Ingesta de un abstract en texto plano. No hay PDF asociado."""
    # Genera un ID estable basado en las primeras palabras
    slug = re.sub(r"\W+", "_", text[:40]).strip("_").lower()
    return ArticleRecord(
        article_id=f"TEXT:{slug}",
        source="abstract_text",
        pdf_path=None,
        abstract=text,
        title=None,
        year=None,
        doi=None,
    )


def _parse_europepmc_result(article: dict, article_id: str, source: str) -> ArticleRecord:
    """Convierte un resultado de Europe PMC en ArticleRecord."""
    abstract = article.get("abstractText") or article.get("abstract")
    title = article.get("title")
    year_str = article.get("pubYear")
    year = int(year_str) if year_str and year_str.isdigit() else None
    doi = article.get("doi")

    # Buscar URL de PDF OA en la respuesta de Europe PMC
    pdf_url: str | None = None
    fulltext_urls = article.get("fullTextUrlList", {}).get("fullTextUrl", [])
    for url_entry in fulltext_urls:
        if url_entry.get("documentStyle") == "pdf" and url_entry.get("availability") == "Open access":
            pdf_url = url_entry.get("url")
            break

    return ArticleRecord(
        article_id=article_id,
        source=source,
        pdf_path=pdf_url,   # se rellena con ruta local tras la descarga
        abstract=abstract,
        title=title,
        year=year,
        doi=doi,
    )


def _try_download_pdf(record: ArticleRecord, output_dir: str) -> str | None:
    """Intenta descargar el PDF si hay una URL disponible en el record."""
    pdf_url = record.get("pdf_path")
    if not pdf_url or not pdf_url.startswith("http"):
        return None
    filename = record["article_id"].replace(":", "_").replace("/", "_")
    return _download_pdf(pdf_url, output_dir, filename)


def _download_pdf(url: str, output_dir: str, filename: str) -> str | None:
    """Descarga un PDF desde `url` y lo guarda en `output_dir/filename.pdf`."""
    os.makedirs(output_dir, exist_ok=True)
    dest = os.path.join(output_dir, f"{filename}.pdf")

    if os.path.exists(dest):
        logger.info(f"PDF ya descargado: {dest}")
        return dest

    logger.info(f"Descargando PDF desde {url}")
    try:
        resp = requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"PDF guardado en {dest}")
        return dest
    except requests.RequestException as e:
        logger.warning(f"No se pudo descargar el PDF: {e}")
        return None


def _resolve_oa_pdf_via_unpaywall(doi: str) -> str | None:
    """Consulta Unpaywall para obtener la URL del PDF en acceso abierto."""
    if not UNPAYWALL_EMAIL:
        logger.warning("UNPAYWALL_EMAIL no configurado; omitiendo consulta a Unpaywall.")
        return None
    url = f"{UNPAYWALL_URL}/{doi}?email={UNPAYWALL_EMAIL}"
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            best = data.get("best_oa_location") or {}
            return best.get("url_for_pdf")
    except requests.RequestException as e:
        logger.warning(f"Error consultando Unpaywall: {e}")
    return None
