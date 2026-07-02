"""
stage4_extract.py — Etapa 4: Extracción con LLM (structured output).

Llama a la API de Claude usando tool use con schema forzado para extraer
información estructurada de los chunks recuperados.

Decisiones de diseño:
  - Tool use + schema forzado: garantiza validez sintáctica del JSON sin post-procesamiento
  - strict=True: la salida del modelo respeta el schema exactamente
  - Evidence obligatorio: cada campo lleva verbatim del texto fuente
  - Null-flagging: si no hay información disponible, value=null (no se alucina)
  - Proveedor como parámetro: el modelo es configurable, no incrustado

El campo `llm_provider` está reservado para extensión futura (ej. OpenAI, Gemini).
En este TFG, solo se usa Claude.
"""

import logging
from typing import Any, TypedDict

import anthropic

from config import ANTHROPIC_API_KEY, LLM_MAX_TOKENS, LLM_MODEL
from schemas import (
    ABSTRACT_SCHEMA,
    ABSTRACT_TOOL_DESCRIPTION,
    ABSTRACT_TOOL_NAME,
    TABLE_SCHEMA,
    TABLE_TOOL_DESCRIPTION,
    TABLE_TOOL_NAME,
)
from stage2_chunk import Chunk
from stage3_retrieve import ExtractionType, build_context_text

logger = logging.getLogger(__name__)

# Sistema de instrucciones compartido para ambos modos de extracción
_SYSTEM_PROMPT = """Eres un extractor experto de información clínica y epidemiológica 
de artículos científicos en el dominio de la alergología clínica.

Reglas estrictas:
1. Extrae información ÚNICAMENTE del texto proporcionado. No uses conocimiento externo.
2. El campo `evidence` debe contener el fragmento textual VERBATIM del texto fuente 
   que justifica el valor extraído. No parafrasees.
3. Si la información para un campo no está presente en el texto, devuelve value=null.
   Nunca inventes ni inferencias valores no explícitos en el texto.
4. Asigna `confidence` según tu certeza:
   - "high":   la información es explícita y sin ambigüedad en el texto
   - "medium": la información es inferible con razonable certeza
   - "low":    la información es ambigua o requires interpretación significativa
5. Usa siempre la herramienta disponible para devolver tu respuesta. No respondas en texto libre.
"""


# ---------------------------------------------------------------------------
# Tipos de salida
# ---------------------------------------------------------------------------
class ExtractionResult(TypedDict):
    article_id: str
    extraction_type: str        # "abstract" | "table"
    schema_version: str         # "v1.0"
    model_used: str
    extracted: dict             # los campos extraídos según el schema
    context_text: str           # texto enviado al LLM (para auditoría)
    input_tokens: int
    output_tokens: int


# ---------------------------------------------------------------------------
# Función principal
# ---------------------------------------------------------------------------
def extract(
    article_id: str,
    chunks: list[Chunk],
    extraction_type: ExtractionType,
    model: str = LLM_MODEL,
) -> ExtractionResult:
    """
    Extrae información estructurada de los chunks usando la Claude API.

    Args:
        article_id:      identificador del artículo
        chunks:          chunks recuperados por Stage 3
        extraction_type: "abstract" o "table"
        model:           modelo de Claude a usar (configurable)

    Returns:
        ExtractionResult con los campos extraídos y metadatos de auditoría.

    Raises:
        ValueError: si no hay chunks disponibles para extraer
        anthropic.APIError: si la API de Claude devuelve un error
    """
    if not chunks:
        raise ValueError(f"No hay chunks disponibles para extraer ({article_id}, {extraction_type})")

    context_text = build_context_text(chunks)

    if extraction_type == "abstract":
        return _extract_with_tool(
            article_id=article_id,
            context_text=context_text,
            extraction_type="abstract",
            tool_name=ABSTRACT_TOOL_NAME,
            tool_description=ABSTRACT_TOOL_DESCRIPTION,
            tool_schema=ABSTRACT_SCHEMA,
            model=model,
        )
    elif extraction_type == "table":
        return _extract_with_tool(
            article_id=article_id,
            context_text=context_text,
            extraction_type="table",
            tool_name=TABLE_TOOL_NAME,
            tool_description=TABLE_TOOL_DESCRIPTION,
            tool_schema=TABLE_SCHEMA,
            model=model,
        )
    else:
        raise ValueError(f"Tipo de extracción desconocido: '{extraction_type}'")


# ---------------------------------------------------------------------------
# Llamada a la API de Claude con tool use forzado
# ---------------------------------------------------------------------------
def _extract_with_tool(
    article_id: str,
    context_text: str,
    extraction_type: str,
    tool_name: str,
    tool_description: str,
    tool_schema: dict,
    model: str,
) -> ExtractionResult:
    """
    Hace la llamada a la Claude API con tool use y schema forzado.
    Devuelve el ExtractionResult con el JSON extraído.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_message = (
        f"A continuación se proporciona el texto extraído de un artículo científico "
        f"de alergología clínica. Extrae la información solicitada usando la herramienta "
        f"disponible.\n\n"
        f"TEXTO DEL ARTÍCULO:\n"
        f"{'=' * 60}\n"
        f"{context_text}\n"
        f"{'=' * 60}"
    )

    logger.info(f"Llamando a Claude ({model}) para {article_id} — modo {extraction_type}")
    logger.debug(f"Longitud del contexto: {len(context_text)} caracteres")

    response = client.messages.create(
        model=model,
        max_tokens=LLM_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        tools=[
            {
                "name": tool_name,
                "description": tool_description,
                "input_schema": tool_schema,
                "strict": True,   # Schema enforcement en la API
            }
        ],
        tool_choice={"type": "tool", "name": tool_name},  # Forzar uso del tool
        messages=[{"role": "user", "content": user_message}],
    )

    # Extraer el resultado del tool_use block
    extracted = _parse_tool_response(response, tool_name)

    logger.info(
        f"Extracción completada para {article_id} ({extraction_type}): "
        f"{response.usage.input_tokens} tokens entrada, "
        f"{response.usage.output_tokens} tokens salida."
    )

    return ExtractionResult(
        article_id=article_id,
        extraction_type=extraction_type,
        schema_version="v1.0",
        model_used=model,
        extracted=extracted,
        context_text=context_text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
    )


def _parse_tool_response(response: Any, expected_tool_name: str) -> dict:
    """
    Extrae el dict de resultado del bloque tool_use en la respuesta de Claude.

    Raises:
        RuntimeError: si la respuesta no contiene un bloque tool_use válido.
    """
    for block in response.content:
        if block.type == "tool_use" and block.name == expected_tool_name:
            return block.input

    # Si llegamos aquí, Claude no usó la herramienta (no debería pasar con tool_choice forzado)
    raise RuntimeError(
        f"La respuesta de Claude no contiene el bloque tool_use esperado "
        f"('{expected_tool_name}'). Stop reason: {response.stop_reason}"
    )
