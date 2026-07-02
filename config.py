"""
config.py — Configuración central del pipeline RAG.

Todas las constantes configurables del sistema están aquí.
Los valores sensibles (API keys) se leen de variables de entorno.
"""

import os

# ---------------------------------------------------------------------------
# API Keys (desde variables de entorno)
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY: str = os.environ.get("ANTHROPIC_API_KEY", "")
UNPAYWALL_EMAIL: str = os.environ.get("UNPAYWALL_EMAIL", "")  # necesario para Unpaywall

# ---------------------------------------------------------------------------
# Modelo LLM
# Cambiar a "claude-opus-4-6" para la evaluación final si el presupuesto lo permite.
# ---------------------------------------------------------------------------
LLM_MODEL: str = "claude-sonnet-4-6"
LLM_MAX_TOKENS: int = 2048

# ---------------------------------------------------------------------------
# GROBID
# Desplegado localmente vía Docker: docker run -p 8070:8070 grobid/grobid:latest
# ---------------------------------------------------------------------------
GROBID_URL: str = os.environ.get("GROBID_URL", "http://localhost:8070")
GROBID_TIMEOUT: int = 120  # segundos; los PDFs largos tardan

# ---------------------------------------------------------------------------
# Europe PMC
# ---------------------------------------------------------------------------
EUROPEPMC_SEARCH_URL: str = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EUROPEPMC_ARTICLE_URL: str = "https://www.ebi.ac.uk/europepmc/webservices/rest"

# ---------------------------------------------------------------------------
# Unpaywall
# ---------------------------------------------------------------------------
UNPAYWALL_URL: str = "https://api.unpaywall.org/v2"

# ---------------------------------------------------------------------------
# Almacenamiento
# ---------------------------------------------------------------------------
OUTPUT_DIR: str = os.environ.get("PIPELINE_OUTPUT_DIR", "./output")
JSONL_FILENAME: str = "extractions.jsonl"
CSV_FILENAME: str = "extractions.csv"

# ---------------------------------------------------------------------------
# Recuperación por reglas (Stage 3)
# Mapeo: tipo de extracción → secciones IMRAD de donde recuperar chunks.
# Las claves se normalizan a minúsculas antes de comparar (ver stage3_retrieve.py).
# ---------------------------------------------------------------------------
SECTION_RULES: dict[str, list[str]] = {
    "abstract": ["abstract"],
    "table": [
        "methods", "materials and methods", "patients and methods",
        "methodology", "materials", "study design",
        "results", "findings", "outcomes",
    ],
}

# Las tablas se incluyen siempre en la recuperación de tipo "table"
ALWAYS_INCLUDE_TABLES_FOR_TABLE_EXTRACTION: bool = True

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
