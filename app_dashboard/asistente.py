import os
import logging
from google.auth import default
import vertexai
from vertexai.generative_models import (
    GenerativeModel,
    Tool,
    FunctionDeclaration,
    Content,
    Part
)
from pydantic import BaseModel
from typing import List

from rag_engine import (
    buscar_documentacion,
    listar_documentos_indexados,
    obtener_indice_documento,
    obtener_seccion_documento,
)
from modelo import get_resumen_datos, get_top_centros_atenciones, get_top_comunas_riesgo, get_colapsos_por_periodo

logger = logging.getLogger(__name__)

# --- 1. Inicialización de Vertex AI ---
def get_project_id():
    try:
        _, project = default()
        return project
    except Exception:
        return os.environ.get("GOOGLE_CLOUD_PROJECT", "proyecto-generico")

try:
    vertexai.init(project=get_project_id(), location=os.environ.get("VERTEX_LOCATION", "us-central1"))
except Exception as e:
    logger.warning(f"No se pudo inicializar Vertex AI. Error: {e}")

MODEL_NAME = "gemini-2.5-flash"

# --- 2. Herramientas ---

top_comunas_func = FunctionDeclaration(
    name="top_comunas_colapso",
    description="Devuelve las comunas con mayor riesgo o probabilidad de colapso logístico.",
    parameters={
        "type": "object",
        "properties": {
            "top_n": {"type": "integer", "description": "Cantidad de comunas a retornar (por defecto 3)."}
        }
    }
)

top_centros_func = FunctionDeclaration(
    name="top_centros_atenciones",
    description="Devuelve los centros de salud con mayor volumen de atenciones respiratorias históricas. Acepta filtrar por mes y/o año específico (ej. 'junio', 2026); sin esos parámetros suma todo el histórico 2023-2026.",
    parameters={
        "type": "object",
        "properties": {
            "top_n": {"type": "integer", "description": "Cantidad de centros a retornar (por defecto 3)."},
            "mes": {"type": "string", "description": "Mes a filtrar, en español (ej. 'junio') o número 1-12. Opcional."},
            "anio": {"type": "integer", "description": "Año a filtrar (ej. 2026). Opcional."}
        }
    }
)

buscar_doc_func = FunctionDeclaration(
    name="buscar_documentacion",
    description=(
        "Busca por palabra clave en las specs técnicas del proyecto (diseño de la ETL, arquitectura, "
        "decisiones de ingeniería). Devuelve solo un fragmento corto, no el documento completo. "
        "NO la uses para preguntas sobre metodología del modelo, variables, bitácora de experimentos, "
        "métricas (recall/precisión/PR-AUC) o resultados/comparación de modelos: para eso existe "
        "consultar_informe_estudio, que trae el informe completo y es la fuente correcta."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Pregunta o término a buscar en la documentación."}
        },
        "required": ["query"]
    }
)

resumen_datos_func = FunctionDeclaration(
    name="resumen_datos_cargados",
    description="Devuelve un resumen del dataset actualmente cargado: cuántos centros y comunas cubre, período de años, total histórico de atenciones y cuándo se actualizó por última vez. Úsala cuando te pregunten qué datos tienes, de dónde vienen o qué tan actualizados están.",
    parameters={"type": "object", "properties": {}}
)

documento_func = FunctionDeclaration(
    name="consultar_documento",
    description=(
        "ES LA HERRAMIENTA POR DEFECTO para dos tipos de pregunta: (1) sobre el estudio en sí "
        "— el problema, fuentes de datos, definición de 'colapso', las 26 variables, los tres "
        "algoritmos comparados, la bitácora de experimentos, métricas (recall/precisión/PR-AUC), "
        "resultados, SHAP y glosario — documento 'informe_estudio'; (2) sobre CÓMO USAR el "
        "dashboard mismo — qué hace cada botón, control, pestaña o gráfico, qué pasa al hacer "
        "clic o pasar el mouse sobre algo — documento 'manual_dashboard'. "
        "Uso en 3 pasos: si no sabes qué documento corresponde, llama sin argumentos para ver el "
        "catálogo; con 'documento' pero sin 'seccion' para ver el índice de secciones de ese "
        "documento; con 'documento' Y 'seccion' para traer el contenido completo de esa sección. "
        "No adivines el número de sección sin haber visto el índice. Si la pregunta toca más de "
        "un tema, llama esta herramienta una vez por cada sección relevante dentro del mismo "
        "turno, antes de responder — no le preguntes al usuario si quieres revisar otra sección, "
        "simplemente revísala. Prioriza esta herramienta sobre buscar_documentacion para "
        "cualquier pregunta de metodología, variables, métricas, resultados o uso del panel."
    ),
    parameters={
        "type": "object",
        "properties": {
            "documento": {"type": "string", "description": "Nombre del documento: 'informe_estudio' o 'manual_dashboard'. Omite este parámetro para ver el catálogo de documentos disponibles."},
            "seccion": {"type": "integer", "description": "Número de sección a consultar (ver el índice del documento, que se devuelve al llamar sin este parámetro)."}
        }
    }
)

colapsos_periodo_func = FunctionDeclaration(
    name="colapsos_por_periodo",
    description=(
        "Devuelve la distribución de colapsos REALES (alertas correctas + colapsos no "
        "detectados; no incluye falsas alarmas) agrupada por estación del año y por mes, sobre "
        "el período de prueba del modelo (2026). Es el mismo cálculo que las gráficas de dona "
        "'Colapsos por Estación' y 'Colapsos por Mes' del panel. Úsala para preguntas como "
        "'¿en qué mes/estación hay más colapsos?' o '¿el otoño concentra más sobrecargas que "
        "el invierno?'. No sirve para volumen de atenciones (para eso usa top_centros_atenciones)."
    ),
    parameters={"type": "object", "properties": {}}
)

gemini_tools = Tool(
    function_declarations=[
        top_comunas_func,
        top_centros_func,
        buscar_doc_func,
        resumen_datos_func,
        documento_func,
        colapsos_periodo_func,
    ]
)

# --- 3. Ejecución de herramientas (Dispatcher) ---

def ejecutar_tool(name: str, args: dict) -> dict:
    if name == "top_comunas_colapso":
        top_n = int(args.get("top_n", 3))
        resultado = get_top_comunas_riesgo(top_n)
        if not resultado:
            return {"resultado": "El pronóstico vigente (T+1) no detecta comunas en alerta de colapso."}
        return {"resultado": resultado}

    elif name == "top_centros_atenciones":
        top_n = int(args.get("top_n", 3))
        resultado = get_top_centros_atenciones(top_n, mes=args.get("mes"), anio=args.get("anio"))
        if not resultado:
            return {"resultado": "No hay atenciones registradas para ese período."}
        return {"resultado": resultado}

    elif name == "buscar_documentacion":
        query = args.get("query", "")
        docs = buscar_documentacion(query)
        if not docs:
            return {"resultado": "No se encontraron documentos relevantes."}
        return {"resultado": docs}

    elif name == "resumen_datos_cargados":
        return {"resultado": get_resumen_datos()}

    elif name == "colapsos_por_periodo":
        return {"resultado": get_colapsos_por_periodo()}

    elif name == "consultar_documento":
        documento = args.get("documento")
        if not documento:
            return {"resultado": {"documentos_disponibles": listar_documentos_indexados()}}

        seccion = args.get("seccion")
        if seccion is None:
            indice = obtener_indice_documento(documento)
            if not indice:
                return {"error": f"No existe el documento '{documento}'. Consulta el catálogo llamando sin argumentos."}
            return {"resultado": {"indice_secciones": indice}}

        contenido = obtener_seccion_documento(documento, int(seccion))
        if not contenido:
            return {"error": f"No existe la sección {seccion} en '{documento}'. Consulta el índice llamando solo con 'documento'."}
        return {"resultado": contenido}

    return {"error": f"Herramienta {name} no implementada."}

# --- 4. Interfaz Principal ---
class MensajeChat(BaseModel):
    role: str
    content: str

def procesar_chat(historial: List[MensajeChat], system_prompt: str) -> str:
    """Envía el historial al modelo, maneja function calling y retorna la respuesta final."""
    model = GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=[system_prompt],
        tools=[gemini_tools],
    )
    
    vertex_history = []
    if len(historial) > 1:
        for msg in historial[:-1]:
            role = "user" if msg.role == "user" else "model"
            vertex_history.append(Content(role=role, parts=[Part.from_text(msg.content)]))
            
    # response_validation=False: evita que el SDK aborte la sesión con un 500 cuando el modelo
    # encadena varias llamadas a herramientas seguidas (ver bucle abajo) — es la mitigación que
    # el propio error del SDK sugiere para ese caso.
    chat = model.start_chat(history=vertex_history, response_validation=False)
    ultimo_mensaje = historial[-1].content

    try:
        response = chat.send_message(ultimo_mensaje)

        # Con 6 herramientas disponibles el modelo puede pedir varias funciones en PARALELO
        # dentro del mismo turno (ej. una pregunta con dos partes) — Vertex exige que se le
        # responda con un function_response por cada function_call de ese turno, todos juntos
        # en un solo mensaje, o rechaza la petición ("number of function response parts...").
        # También puede encadenar turnos completos uno tras otro (ej. buscar_documentacion y
        # luego consultar_documento) — de ahí el loop, con un tope de seguridad.
        for _ in range(5):
            parts = response.candidates[0].content.parts if response.candidates else []
            llamadas = [p.function_call for p in parts if p.function_call]
            if not llamadas:
                break

            response_parts = []
            for llamada in llamadas:
                f_args = {k: v for k, v in llamada.args.items()}
                tool_result = ejecutar_tool(llamada.name, f_args)
                response_parts.append(
                    Part.from_function_response(
                        name=llamada.name,
                        response={"content": tool_result}
                    )
                )

            response = chat.send_message(response_parts)

        return response.text
    except Exception as e:
        logger.error(f"Error procesando chat: {e}")
        return f"Error en Vertex AI (GCP): {e}"
