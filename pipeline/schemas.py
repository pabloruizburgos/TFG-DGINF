"""
schemas.py — Schemas JSON de extracción del pipeline RAG.

Contiene los dos schemas definitivos (ver §4.1 de NOTAS_PROYECTO_INF.md):
  - ABSTRACT_SCHEMA: clasificación del abstract (5 campos categóricos cerrados)
  - TABLE_SCHEMA:    extracción de tabla (4 campos fijos)

Estos dicts se usan directamente como `input_schema` en el tool use de la API de Claude
(Stage 4) y como schema de validación en jsonschema (Stage 5).

Todos los campos incluyen el envoltorio {value, evidence, confidence}.
El campo `evidence` debe contener texto verbatim del artículo fuente.
Cualquier campo no localizable se devuelve con value=null.
"""

# ---------------------------------------------------------------------------
# Schema A — Clasificación del abstract
# ---------------------------------------------------------------------------
ABSTRACT_TOOL_NAME = "extract_abstract_classification"
ABSTRACT_TOOL_DESCRIPTION = (
    "Extrae una clasificación estructurada del abstract de un artículo científico "
    "de alergología clínica. Devuelve cinco campos categóricos cerrados. "
    "Para cada campo incluye: el valor extraído, el fragmento textual verbatim del "
    "abstract que justifica la clasificación, y el nivel de confianza. "
    "Si la información no está disponible en el texto, devuelve value=null."
)

ABSTRACT_SCHEMA: dict = {
    "type": "object",
    "required": [
        "study_type",
        "study_design_temporality",
        "sample_size_estimated",
        "main_topic",
        "clinical_focus",
    ],
    "properties": {
        "study_type": {
            "type": "object",
            "description": "Tipo de diseño del estudio.",
            "required": ["value", "evidence", "confidence"],
            "properties": {
                "value": {
                    "type": ["string", "null"],
                    "enum": [
                        "case_report",
                        "case_series",
                        "retrospective_cohort",
                        "prospective_cohort",
                        "randomized_controlled_trial",
                        "cross_sectional",
                        "systematic_review",
                        "meta_analysis",
                        "narrative_review",
                        "other",
                        None,
                    ],
                    "description": "Tipo de estudio clasificado.",
                },
                "evidence": {
                    "type": ["string", "null"],
                    "description": "Fragmento textual verbatim del abstract que justifica la clasificación.",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Nivel de confianza en la clasificación.",
                },
            },
        },
        "study_design_temporality": {
            "type": "object",
            "description": "Temporalidad del diseño del estudio.",
            "required": ["value", "evidence", "confidence"],
            "properties": {
                "value": {
                    "type": ["string", "null"],
                    "enum": ["retrospective", "prospective", "not_applicable", "unclear", None],
                },
                "evidence": {"type": ["string", "null"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        "sample_size_estimated": {
            "type": "object",
            "description": "Número estimado de sujetos/pacientes incluidos en el estudio.",
            "required": ["value", "evidence", "confidence"],
            "properties": {
                "value": {
                    "type": ["integer", "null"],
                    "description": "Tamaño muestral como entero. null si no se menciona.",
                },
                "evidence": {"type": ["string", "null"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        "main_topic": {
            "type": "object",
            "description": "Tema clínico principal del estudio.",
            "required": ["value", "evidence", "confidence"],
            "properties": {
                "value": {
                    "type": ["string", "null"],
                    "enum": [
                        "food_allergy",
                        "drug_allergy",
                        "venom_allergy",
                        "allergic_rhinitis",
                        "asthma",
                        "atopic_dermatitis",
                        "anaphylaxis",
                        "refractory_anaphylaxis",
                        "immunotherapy",
                        "biologics",
                        "epidemiology",
                        "diagnostic_methods",
                        "other",
                        None,
                    ],
                },
                "evidence": {"type": ["string", "null"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        "clinical_focus": {
            "type": "object",
            "description": "Enfoque clínico principal del estudio.",
            "required": ["value", "evidence", "confidence"],
            "properties": {
                "value": {
                    "type": ["string", "null"],
                    "enum": [
                        "severity",
                        "prevalence",
                        "incidence",
                        "treatment_efficacy",
                        "safety",
                        "risk_factors",
                        "diagnostic_accuracy",
                        "pathophysiology",
                        "other",
                        None,
                    ],
                },
                "evidence": {"type": ["string", "null"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
    },
}

# ---------------------------------------------------------------------------
# Schema B — Extracción de tabla
# Cuatro campos fijos. `primary_outcome` y `between_group_comparison` tienen
# estructura interna porque una medida clínica o una comparación no son
# representables fielmente como escalar simple.
# ---------------------------------------------------------------------------
TABLE_TOOL_NAME = "extract_table_data"
TABLE_TOOL_DESCRIPTION = (
    "Extrae información estructurada de las tablas y secciones de Métodos/Resultados "
    "de un artículo científico de alergología clínica. Devuelve cuatro campos fijos. "
    "Para cada campo incluye: el valor extraído, el fragmento textual verbatim que "
    "justifica el valor, y el nivel de confianza. "
    "Si la información no está disponible en el texto proporcionado, devuelve value=null."
)

TABLE_SCHEMA: dict = {
    "type": "object",
    "required": [
        "population_description",
        "n_total",
        "primary_outcome",
        "between_group_comparison",
    ],
    "properties": {
        "population_description": {
            "type": "object",
            "description": "Descripción de la población del estudio.",
            "required": ["value", "evidence", "confidence"],
            "properties": {
                "value": {
                    "type": ["string", "null"],
                    "description": (
                        "Descripción de la población: criterios de inclusión clave, "
                        "rango de edad, condición clínica principal."
                    ),
                },
                "evidence": {"type": ["string", "null"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        "n_total": {
            "type": "object",
            "description": "Número total de sujetos incluidos en el análisis.",
            "required": ["value", "evidence", "confidence"],
            "properties": {
                "value": {"type": ["integer", "null"]},
                "evidence": {"type": ["string", "null"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        "primary_outcome": {
            "type": "object",
            "description": "Medida de resultado primario del estudio.",
            "required": ["value", "evidence", "confidence"],
            "properties": {
                "value": {
                    "type": ["object", "null"],
                    "description": "Objeto con los campos de la medida de resultado.",
                    "required": ["variable_name", "measure_type", "measure_value"],
                    "properties": {
                        "variable_name": {
                            "type": "string",
                            "description": "Nombre de la variable de resultado (p.ej. 'Total Nasal Symptom Score').",
                        },
                        "measure_type": {
                            "type": "string",
                            "enum": [
                                "count",
                                "percentage",
                                "mean_sd",
                                "median_iqr",
                                "odds_ratio",
                                "relative_risk",
                                "hazard_ratio",
                                "incidence_rate",
                                "other",
                            ],
                        },
                        "measure_value": {
                            "type": ["string", "number", "null"],
                            "description": "Valor numérico o string con el resultado (p.ej. '35.2 ± 12.1').",
                        },
                        "unit": {"type": ["string", "null"]},
                        "confidence_interval": {"type": ["string", "null"]},
                        "p_value": {"type": ["number", "null"]},
                    },
                },
                "evidence": {"type": ["string", "null"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
        "between_group_comparison": {
            "type": "object",
            "description": "Comparación estadística entre los grupos del estudio.",
            "required": ["value", "evidence", "confidence"],
            "properties": {
                "value": {
                    "type": ["object", "null"],
                    "description": "Objeto con los campos de la comparación entre grupos.",
                    "required": ["groups_compared", "effect_measure"],
                    "properties": {
                        "groups_compared": {
                            "type": "string",
                            "description": "Grupos comparados (p.ej. 'SLIT vs Placebo').",
                        },
                        "effect_measure": {
                            "type": "string",
                            "enum": [
                                "mean_difference",
                                "odds_ratio",
                                "relative_risk",
                                "hazard_ratio",
                                "percentage_difference",
                                "other",
                            ],
                        },
                        "effect_value": {"type": ["string", "number", "null"]},
                        "confidence_interval": {"type": ["string", "null"]},
                        "p_value": {"type": ["number", "null"]},
                        "statistically_significant": {"type": ["boolean", "null"]},
                    },
                },
                "evidence": {"type": ["string", "null"]},
                "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
            },
        },
    },
}
