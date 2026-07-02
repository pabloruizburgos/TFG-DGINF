"""
stage1_parse.py — Etapa 1: Parseo estructural del documento.

Convierte un PDF en una representación estructurada usando GROBID:
  - Lista de secciones con su título y texto concatenado
  - Lista de tablas con caption y contenido parseado

GROBID debe estar corriendo como servicio Docker:
    docker run --rm -p 8070:8070 grobid/grobid:latest

La salida de esta etapa alimenta directamente Stage 2 (chunking).
"""

import logging
import re
import xml.etree.ElementTree as ET
from typing import TypedDict

import requests

from config import GROBID_TIMEOUT, GROBID_URL

logger = logging.getLogger(__name__)

# Namespace TEI que GROBID usa en su XML de salida
TEI_NS = "http://www.tei-c.org/ns/1.0"
NS = {"tei": TEI_NS}


# ---------------------------------------------------------------------------
# Tipos de salida
# ---------------------------------------------------------------------------
class ParsedTable(TypedDict):
    columns: list[str]
    rows: list[list[str]]


class TableRecord(TypedDict):
    table_id: str        # "Table 1", "Table 2", etc.
    caption: str
    section: str         # sección donde aparece la tabla
    raw_content: str     # texto plano de la tabla (para evidencia)
    parsed_table: ParsedTable


class SectionRecord(TypedDict):
    section: str    # título de la sección tal como aparece en el artículo
    text: str       # texto concatenado de todos los párrafos de la sección


class ParsedDocument(TypedDict):
    article_id: str
    abstract: str | None    # abstract extraído por GROBID (si no venía de Stage 0)
    sections: list[SectionRecord]
    tables: list[TableRecord]


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def parse(article_id: str, pdf_path: str, existing_abstract: str | None = None) -> ParsedDocument:
    """
    Llama a GROBID para parsear el PDF y construye un ParsedDocument.

    Args:
        article_id:         identificador del artículo (para los chunk_ids)
        pdf_path:           ruta local al PDF a procesar
        existing_abstract:  abstract ya obtenido en Stage 0 (se usa si GROBID no extrae uno)

    Returns:
        ParsedDocument con secciones y tablas estructuradas.

    Raises:
        ConnectionError: si GROBID no está disponible
        requests.RequestException: en errores HTTP
    """
    logger.info(f"Parseando PDF con GROBID: {pdf_path}")
    tei_xml = _call_grobid(pdf_path)
    return _parse_tei_xml(article_id, tei_xml, existing_abstract)


# ---------------------------------------------------------------------------
# Comunicación con GROBID
# ---------------------------------------------------------------------------
def _call_grobid(pdf_path: str) -> str:
    """
    Envía el PDF al endpoint /api/processFulltextDocument de GROBID.
    Devuelve el TEI XML como string.
    """
    endpoint = f"{GROBID_URL}/api/processFulltextDocument"
    try:
        with open(pdf_path, "rb") as f:
            resp = requests.post(
                endpoint,
                files={"input": (pdf_path, f, "application/pdf")},
                data={"consolidateHeader": "1", "consolidateCitations": "0"},
                timeout=GROBID_TIMEOUT,
            )
        resp.raise_for_status()
        return resp.text
    except requests.exceptions.ConnectionError:
        raise ConnectionError(
            f"No se puede conectar a GROBID en {GROBID_URL}. "
            "¿Está corriendo el contenedor Docker? "
            "Ejecute: docker run --rm -p 8070:8070 grobid/grobid:latest"
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Error en la llamada a GROBID: {e}")


def check_grobid_health() -> bool:
    """Comprueba que GROBID está disponible. Útil para tests y diagnóstico."""
    try:
        resp = requests.get(f"{GROBID_URL}/api/isalive", timeout=5)
        return resp.status_code == 200
    except requests.RequestException:
        return False


# ---------------------------------------------------------------------------
# Parseo del TEI XML
# ---------------------------------------------------------------------------
def _parse_tei_xml(article_id: str, tei_xml: str, existing_abstract: str | None) -> ParsedDocument:
    """Parsea el TEI XML de GROBID y extrae secciones y tablas."""
    try:
        root = ET.fromstring(tei_xml)
    except ET.ParseError as e:
        raise ValueError(f"TEI XML malformado recibido de GROBID: {e}")

    abstract = _extract_abstract(root) or existing_abstract
    sections = _extract_sections(root)
    tables = _extract_tables(root)

    logger.info(
        f"Parseado completado para {article_id}: "
        f"{len(sections)} secciones, {len(tables)} tablas."
    )
    return ParsedDocument(
        article_id=article_id,
        abstract=abstract,
        sections=sections,
        tables=tables,
    )


def _extract_abstract(root: ET.Element) -> str | None:
    """Extrae el abstract del TEI header."""
    abstract_el = root.find(".//tei:profileDesc/tei:abstract", NS)
    if abstract_el is None:
        return None
    return _element_text(abstract_el).strip() or None


def _extract_sections(root: ET.Element) -> list[SectionRecord]:
    """Extrae las secciones del body del TEI."""
    body = root.find(".//tei:text/tei:body", NS)
    if body is None:
        return []

    sections: list[SectionRecord] = []
    for div in body.findall("tei:div", NS):
        head_el = div.find("tei:head", NS)
        section_name = head_el.text.strip() if head_el is not None and head_el.text else "Unknown"

        # Concatenar texto de todos los párrafos del div (excluyendo figuras/tablas)
        paragraphs: list[str] = []
        for p in div.findall("tei:p", NS):
            text = _element_text(p).strip()
            if text:
                paragraphs.append(text)

        section_text = "\n\n".join(paragraphs)
        if section_text:
            sections.append(SectionRecord(section=section_name, text=section_text))

    return sections


def _extract_tables(root: ET.Element) -> list[TableRecord]:
    """Extrae las tablas del body del TEI."""
    body = root.find(".//tei:text/tei:body", NS)
    if body is None:
        return []

    tables: list[TableRecord] = []
    table_counter = 0

    for div in body.findall(".//tei:div", NS):
        # Sección a la que pertenece esta tabla
        head_el = div.find("tei:head", NS)
        parent_section = head_el.text.strip() if head_el is not None and head_el.text else "Unknown"

        for figure in div.findall("tei:figure[@type='table']", NS):
            table_counter += 1

            # Caption / título de la tabla
            fig_head = figure.find("tei:head", NS)
            fig_desc = figure.find("tei:figDesc", NS)
            head_text = fig_head.text.strip() if fig_head is not None and fig_head.text else ""
            desc_text = _element_text(fig_desc).strip() if fig_desc is not None else ""
            caption = f"{head_text} {desc_text}".strip()
            table_id = head_text or f"Table {table_counter}"

            # Contenido de la tabla
            table_el = figure.find("tei:table", NS)
            parsed, raw = _parse_table_element(table_el)

            tables.append(TableRecord(
                table_id=table_id,
                caption=caption,
                section=parent_section,
                raw_content=raw,
                parsed_table=parsed,
            ))

    return tables


def _parse_table_element(table_el: ET.Element | None) -> tuple[ParsedTable, str]:
    """
    Parsea un elemento <table> de TEI en columnas + filas.
    Devuelve (ParsedTable, raw_text).
    """
    if table_el is None:
        return ParsedTable(columns=[], rows=[]), ""

    rows_raw: list[list[str]] = []
    for row in table_el.findall("tei:row", NS):
        cells = [_element_text(c).strip() for c in row.findall("tei:cell", NS)]
        if any(cells):
            rows_raw.append(cells)

    # La primera fila no vacía se considera cabecera
    columns: list[str] = rows_raw[0] if rows_raw else []
    data_rows: list[list[str]] = rows_raw[1:] if len(rows_raw) > 1 else []

    # Texto plano para evidencia
    raw = "\n".join([" | ".join(r) for r in rows_raw])

    return ParsedTable(columns=columns, rows=data_rows), raw


# ---------------------------------------------------------------------------
# Utilidad: extrae texto plano de un elemento XML incluyendo colas de hijos
# ---------------------------------------------------------------------------
def _element_text(el: ET.Element) -> str:
    """
    Extrae texto completo de un elemento XML (incluyendo texto de subelementos).
    Equivalente a inner_text en HTML.
    """
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        parts.append(_element_text(child))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"\s+", " ", " ".join(parts))
