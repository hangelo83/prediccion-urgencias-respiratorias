import os

# Configuración de Directorios y Rutas
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DATA_PATH = os.path.join(BASE_DIR, "data", "panel.parquet")
MAPPING_PATH = os.path.join(BASE_DIR, "data", "centros_mapping.json")
GRID_PATH = os.path.join(BASE_DIR, "data", "grid_results.json")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Configuración del Servidor
SERVER_HOST = "0.0.0.0"
SERVER_PORT = int(os.environ.get("PORT", 8080))
SERVER_RELOAD = True

# Credenciales de Autenticación (con fallbacks para pruebas locales)
AUTH_USER_PRESENTACION = os.environ.get("USER_PRESENTACION", "presentacion")
AUTH_PASS_PRESENTACION = os.environ["PASS_PRESENTACION"]

AUTH_USER_DASHBOARD = os.environ.get("USER_DASHBOARD", "dashboard")
AUTH_PASS_DASHBOARD = os.environ["PASS_DASHBOARD"]

# Configuraciones por defecto del modelo (Dashboard)
MODELO_DEFAULTS = {
    "tipo": "aumento_reciente",
    "k": 1.0,
    "ventana": 12,
    "severidad": 0.0,
    "features": {
        "clima": False,
        "red": False,
        "viral": False,
        "z_rob8": True
    }
}
