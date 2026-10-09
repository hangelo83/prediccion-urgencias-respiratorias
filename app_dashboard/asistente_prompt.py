import os
import json
from datetime import datetime
from pydantic import BaseModel

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configuraciones")
PROMPT_FILE = os.path.join(CONFIG_DIR, "prompt_chatbot.json")

DEFAULT_PROMPT = """Eres un asistente experto del proyecto de alerta temprana de sobrecarga logística. Respondes preguntas a usuarios no técnicos de forma clara y directa en español.
**Reglas estrictas:**
1. NUNCA inventes cifras. Usa las herramientas proporcionadas para extraer información del modelo y de los datos en curso.
2. Si te preguntan sobre metodología, variables del modelo, bitácora de experimentos, métricas (recall/precisión/PR-AUC), comparación de modelos o conclusiones, usa consultar_documento con documento='informe_estudio'. Si preguntan cómo usar el dashboard (qué hace un botón, control, pestaña o gráfico), usa consultar_documento con documento='manual_dashboard'. Usa buscar_documentacion solo para el resto de la documentación técnica del proyecto (specs).
3. Si no tienes datos en las herramientas para respaldar la respuesta, admite explícitamente que no posees esa información.
4. Explica el concepto de 'colapso' (alta demanda) como un aumento relativo en el propio centro, no con términos estadísticos.
5. Ante CUALQUIER pregunta que pueda responderse con una herramienta (qué datos tienes, cobertura, comunas, centros, riesgo de colapso, metodología), llama la herramienta correspondiente y responde con esos datos concretos. NUNCA respondas listando o parafraseando tus propias capacidades ('tengo acceso a...', 'puedo identificar...') a modo de menú: eso no es una respuesta, es una evasiva.
6. Sé conversacional y directo, como si ya conocieras los datos porque los acabas de consultar. Si el usuario saluda o pregunta algo ambiguo, responde brevemente y pregunta qué necesita saber, sin listar tu lista de funciones."""

class PromptVersion(BaseModel):
    fecha: str
    prompt: str

class ConfigPromptState(BaseModel):
    prompt_actual: str
    historial: list[PromptVersion]

class UpdatePromptRequest(BaseModel):
    nuevo_prompt: str

def _inicializar_archivo():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.exists(PROMPT_FILE):
        estado_inicial = ConfigPromptState(
            prompt_actual=DEFAULT_PROMPT,
            historial=[]
        )
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(estado_inicial.model_dump_json(indent=2))

def leer_prompt_config() -> ConfigPromptState:
    _inicializar_archivo()
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ConfigPromptState(**data)
    except (json.JSONDecodeError, ValueError):
        # Si el archivo estÃ¡ vacÃ­o o corrupto, devolver el estado inicial
        # y sobreescribir el archivo daÃ±ado
        estado_inicial = ConfigPromptState(
            prompt_actual=DEFAULT_PROMPT,
            historial=[]
        )
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(estado_inicial.model_dump_json(indent=2))
        return estado_inicial

def guardar_nuevo_prompt(nuevo_prompt: str) -> ConfigPromptState:
    estado = leer_prompt_config()
    
    # Solo guardar en historial si cambió
    if estado.prompt_actual != nuevo_prompt:
        # Guardar el actual en el historial antes de pisarlo
        nueva_version = PromptVersion(
            fecha=datetime.now().isoformat(),
            prompt=estado.prompt_actual
        )
        estado.historial.insert(0, nueva_version) # Agregar al inicio
        
        # Mantener solo las ultimas 10 versiones para no inflar el JSON
        if len(estado.historial) > 10:
            estado.historial = estado.historial[:10]
            
        estado.prompt_actual = nuevo_prompt
        
        with open(PROMPT_FILE, "w", encoding="utf-8") as f:
            f.write(estado.model_dump_json(indent=2))
            
    return estado
