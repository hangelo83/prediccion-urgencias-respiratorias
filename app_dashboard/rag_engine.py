import os
import glob
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIRS = [
    os.path.join(PROJECT_ROOT, "specs"),
    os.path.join(PROJECT_ROOT, "entregas")
]

# Documentos "premium": en vez de mandar el archivo entero (miles de tokens de sobra) o
# depender del keyword-match débil de buscar_documentacion() (corta tablas y secciones
# completas), se trocean por sus secciones "## N. Título" — el modelo primero pide el índice
# de un documento (barato) y luego solo la(s) sección(es) que realmente necesita. Cualquier
# .md con ese formato de encabezados puede registrarse aquí sin escribir un parser nuevo.
DOCUMENTOS_INDEXADOS = {
    "informe_estudio": {
        "titulo": "Informe Ampliado de Estudio",
        "descripcion": "Metodología, variables, bitácora de experimentos, métricas y resultados del modelo.",
        "path": os.path.join(PROJECT_ROOT, "entregas", "Informe_Ampliado_Estudio.md"),
    },
    "manual_dashboard": {
        "titulo": "Manual de Uso del Dashboard",
        "descripcion": "Qué hace cada botón, control y gráfico del panel interactivo, y qué pasa al hacer clic o pasar el mouse sobre cada uno.",
        "path": os.path.join(PROJECT_ROOT, "entregas", "Manual_Uso_Dashboard.md"),
    },
}
_secciones_cache: dict[str, list[dict]] = {}


def _parsear_documento(nombre: str) -> list[dict]:
    if nombre in _secciones_cache:
        return _secciones_cache[nombre]

    doc = DOCUMENTOS_INDEXADOS.get(nombre)
    if not doc:
        _secciones_cache[nombre] = []
        return []

    try:
        with open(doc["path"], "r", encoding="utf-8") as f:
            texto = f.read()
    except Exception:
        _secciones_cache[nombre] = []
        return []

    secciones = []
    parte_actual = None
    numero_actual = 0
    titulo_actual = "Introducción"
    buffer = []
    # Entre un "# PARTE..." y la siguiente "## N." hay a veces un párrafo de presentación de
    # la parte (ver PARTE V del informe): no pertenece a la sección numerada anterior ni a la
    # siguiente, así que se descarta en vez de quedar mal atribuido (bug real: sin este flag
    # terminaba duplicando la sección previa con contenido de la parte equivocada).
    esperando_primera_seccion = False

    def _flush():
        contenido = "\n".join(buffer).strip()
        if contenido:
            secciones.append({
                "numero": numero_actual,
                "titulo": titulo_actual,
                "parte": parte_actual,
                "contenido": contenido
            })

    for linea in texto.split("\n"):
        m_parte = re.match(r'^# (PARTE .+)', linea)
        m_seccion = re.match(r'^## (\d+)\.\s*(.+)', linea)
        if m_parte:
            _flush()
            buffer = []
            parte_actual = m_parte.group(1).strip()
            esperando_primera_seccion = True
            continue
        if m_seccion:
            if not esperando_primera_seccion:
                _flush()
            esperando_primera_seccion = False
            numero_actual = int(m_seccion.group(1))
            titulo_actual = m_seccion.group(2).strip()
            buffer = [linea]
            continue
        buffer.append(linea)
    _flush()

    _secciones_cache[nombre] = secciones
    return secciones


def listar_documentos_indexados() -> list[dict]:
    """Catálogo de documentos disponibles vía consultar_documento (nombre + qué contiene)."""
    return [
        {"documento": k, "titulo": v["titulo"], "descripcion": v["descripcion"]}
        for k, v in DOCUMENTOS_INDEXADOS.items()
    ]


def obtener_indice_documento(nombre: str) -> list[dict]:
    """Índice liviano (número, título, parte) de las secciones de un documento — sin contenido."""
    return [
        {"numero": s["numero"], "titulo": s["titulo"], "parte": s["parte"]}
        for s in _parsear_documento(nombre)
    ]


def obtener_seccion_documento(nombre: str, numero: int) -> str | None:
    """Contenido completo de una sección de un documento por su número."""
    for s in _parsear_documento(nombre):
        if s["numero"] == numero:
            return s["contenido"]
    return None

# Cache en memoria de los documentos
_docs_cache = []

def _load_docs():
    global _docs_cache
    if _docs_cache:
        return
    
    for d in DOCS_DIRS:
        if not os.path.exists(d):
            continue
        # Buscar .md en todos los subdirectorios
        for filepath in glob.glob(os.path.join(d, "**", "*.md"), recursive=True):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                    _docs_cache.append({
                        "file": os.path.relpath(filepath, PROJECT_ROOT),
                        "content": content
                    })
            except Exception:
                pass

def buscar_documentacion(query: str, top_k: int = 2) -> list[dict]:
    """Busca en los documentos locales por palabra clave usando regex simple."""
    _load_docs()
    
    # Tokenizar query
    tokens = [t.lower() for t in re.split(r'\W+', query) if len(t) > 3]
    if not tokens:
        return []
    
    resultados = []
    for doc in _docs_cache:
        score = 0
        content_lower = doc["content"].lower()
        for t in tokens:
            # Cuenta ocurrencias del token
            score += content_lower.count(t)
        
        if score > 0:
            # Extraer snippet (primer hallazgo)
            idx = content_lower.find(tokens[0])
            start = max(0, idx - 100)
            end = min(len(content_lower), idx + 200)
            snippet = doc["content"][start:end].replace('\n', ' ')
            
            resultados.append({
                "file": doc["file"],
                "score": score,
                "snippet": f"...{snippet}..."
            })
            
    # Ordenar por score
    resultados = sorted(resultados, key=lambda x: x["score"], reverse=True)
    return resultados[:top_k]
