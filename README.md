# TFG-DGINF | Extracción automatizada de datos clínicos en alergología mediante RAG y grandes modelos de lenguaje

*Trabajo de fin de grado en Ingeniería Informática por CUNEF Universidad (curso 2025-2026).*

Pipeline de extracción estructurada de información clínica y epidemiológica a partir de artículos científicos en el dominio de la alergología. Implementa una arquitectura RAG (Retrieval-Augmented Generation) de 7 etapas con recuperación determinista por sección y extracción mediante la API de Claude con schema forzado.

---

## Requisitos previos

- Python 3.11+
- Docker (para GROBID, solo necesario en modo `table` y `full`)
- Clave de API de Anthropic (`ANTHROPIC_API_KEY`)

---

## Instalación

```bash
git clone https://github.com/<usuario>/TFG-DGINF.git
cd TFG-DGINF/pipeline
pip install -r requirements.txt
```

Crear un archivo `.env` en la raíz del repositorio con las claves:

```bash
ANTHROPIC_API_KEY=sk-ant-...
UNPAYWALL_EMAIL=tu@email.com   # opcional, mejora resolución de PDFs OA
```

Cargar las variables antes de ejecutar:

```bash
export $(cat .env | xargs)
```

---

## Uso

Todos los comandos se ejecutan desde dentro de la carpeta `pipeline/`:

```bash
cd pipeline/
```

**Clasificar el abstract de un artículo por PMID:**
```bash
python pipeline.py --id "PMID:12345678" --mode abstract
```

**Extraer datos de tabla (requiere GROBID corriendo):**
```bash
python pipeline.py --id "PMID:12345678" --mode table
```

**Ejecución completa (abstract + tabla):**
```bash
python pipeline.py --id "PMID:12345678" --mode full
```

**Otras formas de identificar el artículo:**
```bash
# Por DOI
python pipeline.py --id "DOI:10.1016/j.jaci.2024.01.001" --mode abstract

# Desde un PDF local
python pipeline.py --id "/ruta/al/articulo.pdf" --mode table

# Desde un abstract en texto plano
python pipeline.py --id "Background: A randomized controlled trial of SLIT..." --mode abstract
```

**Ver todas las opciones:**
```bash
python pipeline.py --help
```

---

## GROBID (necesario para modo `table` y `full`)

```bash
docker run --rm -p 8070:8070 grobid/grobid:latest
```

Verificar que está corriendo:
```bash
curl http://localhost:8070/api/isalive
```

---

## Salida

Los resultados se guardan en `pipeline/output/` (creado automáticamente):

| Archivo | Contenido |
|---|---|
| `extractions.jsonl` | Un registro JSON por línea, con todos los campos extraídos, evidence y metadatos de auditoría |
| `extractions.csv` | Versión aplanada para análisis tabular |

---

## Schemas de extracción

El pipeline usa dos schemas JSON con forzado de estructura a nivel de API:

**Schema A — Clasificación de abstract** (5 campos categóricos cerrados):
`study_type` · `study_design_temporality` · `sample_size_estimated` · `main_topic` · `clinical_focus`

**Schema B — Extracción de tabla** (4 campos fijos):
`population_description` · `n_total` · `primary_outcome` · `between_group_comparison`

Todos los campos incluyen `value`, `evidence` (texto verbatim del artículo fuente) y `confidence` (`low` / `medium` / `high`). Los campos no localizables devuelven `value: null`.

---

## Estructura del repositorio

```
TFG-DGINF/
├── README.md
├── NOTAS_PROYECTO_INF.md     # fuente de verdad del proyecto (pegar al inicio de cada sesión con Claude)
├── .gitignore
├── pipeline/
│   ├── config.py             # configuración central (modelo, URLs, rutas)
│   ├── schemas.py            # schemas JSON de extracción (A y B)
│   ├── stage0_ingest.py      # ingesta: PMID/DOI/PDF/texto → ArticleRecord
│   ├── stage1_parse.py       # parseo: PDF → secciones + tablas (GROBID)
│   ├── stage2_chunk.py       # chunking: secciones/tablas → lista de Chunk
│   ├── stage3_retrieve.py    # recuperación: reglas por sección IMRAD
│   ├── stage4_extract.py     # extracción: Claude API con tool use forzado
│   ├── stage5_validate.py    # validación: JSON Schema + chequeo de nulls
│   ├── stage6_store.py       # almacenamiento: JSONL + CSV
│   ├── pipeline.py           # orquestador + CLI
│   └── requirements.txt
└── corpus/
    └── ground_truth.json     # anotación manual de referencia (en construcción)
```

---

## Variables de entorno

| Variable | Obligatoria | Descripción |
|---|---|---|
| `ANTHROPIC_API_KEY` | Sí | Clave de API de Anthropic |
| `UNPAYWALL_EMAIL` | No | Email para Unpaywall (mejora resolución de PDFs OA) |
| `GROBID_URL` | No | URL de GROBID (default: `http://localhost:8070`) |
| `PIPELINE_OUTPUT_DIR` | No | Directorio de salida (default: `./output`) |
| `LOG_LEVEL` | No | Nivel de log: `DEBUG`, `INFO`, `WARNING` (default: `INFO`) |
