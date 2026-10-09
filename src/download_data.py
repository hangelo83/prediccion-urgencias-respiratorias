import os
import sys
import json
import logging
import unicodedata
import urllib.request
import urllib.parse
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configuraciones.configuraciones import (
    DEIS_PARQUET,
    FLUNET_CSV,
    FLUNET_ENDPOINT,
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Paquete oficial en datos.gob.cl (CKAN): "Atenciones de urgencias de causas
# respiratorias por semana epidemiológica". Se resuelve por búsqueda para que
# el pipeline sobreviva a cambios en la URL interna del recurso.
CKAN_SEARCH_URL = "https://datos.gob.cl/api/3/action/package_search"
CKAN_QUERY = "Atenciones de urgencias de causas respiratorias por semana epidemiologica"


def _norm(text):
    """Minúsculas sin acentos, para comparar nombres de recursos de forma robusta."""
    text = str(text or "").lower()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text


def _find_deis_parquet_url():
    """Consulta CKAN y devuelve la URL del recurso Parquet respiratorio semanal más relevante."""
    params = urllib.parse.urlencode({"q": CKAN_QUERY, "rows": 10})
    url = f"{CKAN_SEARCH_URL}?{params}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})

    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode())

    results = data.get('result', {}).get('results', [])
    # Recorre en orden de relevancia CKAN y devuelve el primer Parquet cuyo
    # nombre indique urgencias respiratorias.
    for pkg in results:
        for res in pkg.get('resources', []):
            if _norm(res.get('format')) != 'parquet':
                continue
            nombre = _norm(res.get('name')) + ' ' + _norm(res.get('url'))
            if 'respiratori' in nombre and ('urg' in nombre or 'urgencia' in nombre):
                return res.get('url')
    # Segundo intento más laxo: cualquier Parquet dentro de un paquete respiratorio.
    for pkg in results:
        if 'respiratori' not in _norm(pkg.get('title')):
            continue
        for res in pkg.get('resources', []):
            if _norm(res.get('format')) == 'parquet':
                return res.get('url')
    return None


def download_deis_data(output_path):
    """
    Se conecta a la API de Datos Abiertos de Chile (CKAN) y descarga el archivo más
    reciente de 'Atenciones de Urgencia respiratorias' en formato Parquet.
    """
    logging.info("Buscando recursos del DEIS en datos.gob.cl...")
    try:
        parquet_url = _find_deis_parquet_url()
    except Exception as e:
        logging.error(f"Error consultando la API de datos.gob.cl: {e}")
        return False

    if not parquet_url:
        logging.error("No se encontró ningún recurso Parquet del DEIS que coincida.")
        return False

    logging.info(f"Archivo encontrado: {parquet_url}")
    logging.info(f"Descargando datos del DEIS a {output_path}...")
    tmp_path = f"{output_path}.tmp"
    try:
        req = urllib.request.Request(parquet_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=600) as response, open(tmp_path, 'wb') as f:
            while True:
                chunk = response.read(1 << 20)  # 1 MiB
                if not chunk:
                    break
                f.write(chunk)
        os.replace(tmp_path, output_path)  # descarga atómica: no dejar parquet a medias
        logging.info("Descarga de DEIS completada exitosamente.")
        return True
    except Exception as e:
        logging.error(f"Error descargando el archivo Parquet: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


def download_flunet_data(output_path, url):
    """
    Descarga la serie viral nacional (VRS + influenza) desde el endpoint OData de la OMS (FluNet).
    """
    logging.info(f"Descargando datos de FluNet desde {url}...")
    tmp_path = f"{output_path}.tmp"
    try:
        # El filtro OData en configuraciones.py trae espacios sin codificar (legible para humanos);
        # quote() los codifica sin tocar los separadores de la URL (: / ? & = $ ').
        safe_url = urllib.parse.quote(url, safe=":/?&=$'")
        req = urllib.request.Request(safe_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=300) as response:
            content = response.read()
        with open(tmp_path, 'wb') as f:
            f.write(content)
        os.replace(tmp_path, output_path)
        logging.info("Descarga de FluNet completada exitosamente.")
        return True
    except Exception as e:
        logging.error(f"Error descargando el archivo FluNet: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False


if __name__ == "__main__":
    # Escribe directamente en las rutas que consume build_dataset.py (según configuraciones.py).
    Path(DEIS_PARQUET).parent.mkdir(parents=True, exist_ok=True)

    # El endpoint OData de la OMS puede sobreescribirse por variable de entorno si cambia.
    flunet_url = os.environ.get("FLUNET_URL", FLUNET_ENDPOINT)

    exito_deis = download_deis_data(DEIS_PARQUET)
    exito_flunet = download_flunet_data(FLUNET_CSV, flunet_url)

    if exito_deis and exito_flunet:
        logging.info("¡Todas las extracciones automáticas fueron completadas!")
        sys.exit(0)
    else:
        logging.error("Alguna descarga falló. Revisa los logs. El pipeline se detiene.")
        sys.exit(1)  # corta el Cloud Build: no reconstruir el dashboard con datos incompletos
