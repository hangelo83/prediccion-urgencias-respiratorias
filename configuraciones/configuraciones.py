import os

# ─────────────────────────────────────────────────────────
# Configuración central del proyecto
# Alerta Temprana de Sobrecarga Localizada — urgencias respiratorias (Diplomado ML V2)
#
# Aprendizaje supervisado tabular a nivel ESTABLECIMIENTO (centro) × semana en la RM.
# Dos tareas sobre la misma serie:
#   (A) Regresión     → n_atenciones (volumen de urgencias respiratorias de la próxima semana).
#   (B) Clasificación → alta_demanda / "sobrecarga": salto brusco sobre la línea base reciente
#                       del propio centro (media móvil 4 sem + k·σ) = estrés agudo.
# FluNet (viral nacional) aporta el "¿cuándo?"; MP2.5/clima + historia del centro, el "¿dónde?".
# Ambiente (SINCA/DMC) = enriquecimiento OPCIONAL medido por ablación. Ver specs/ (constitution,
# 002-eda-dataset). Enmienda 2026-07-05: target (B) rolling μ₄+k·σ (reemplaza el p90 histórico).
# ─────────────────────────────────────────────────────────

# === Rutas base ===
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(BASE_DIR, 'dataset')
DATASET_SALUD_DIR = os.path.join(BASE_DIR, 'dataset_salud')

# Salida del pipeline 002 (panel analítico centro × semana)
PANEL_PARQUET = os.path.join(DATASET_SALUD_DIR, 'urg_resp_centro_semana.parquet')

# === Ventana temporal del proyecto ===
ANIO_INICIO = 2023
ANIO_FIN = 2026
# Split temporal para train/test (sin fuga — Art. II)
ANIO_TRAIN_FIN = 2024    # Train: 2023–2024
ANIO_TEST_INICIO = 2025  # Test:  2025–2026

# === Unidad de análisis ===
UNIDAD_ANALISIS = 'establecimiento'  # EstablecimientoCodigo × Anio × SemanaEstadistica

# === Región y comunas del Escenario A (11 comunas RM con estación SINCA propia) ===
# El núcleo (solo-DEIS) puede escalar a toda la RM; el Escenario A acota el cruce ambiental opcional.
REGION_CODIGO_RM = 13
COMUNAS_ESCENARIO_A = [
    "Santiago",
    "Las Condes",
    "Independencia",
    "Pudahuel",
    "Cerro Navia",
    "El Bosque",
    "Puente Alto",
    "Quilicura",
    "Cerrillos",
    "Talagante",
    "La Florida",
]

# === Fuente 1: DEIS / SADU — targets + predictores de la red (EN MANO) ===
DEIS_PARQUET = os.path.join(DATASET_SALUD_DIR, 'at_urg_respiratorio_semanal.parquet')
DEIS_DICCIONARIO = os.path.join(DATASET_SALUD_DIR, 'diccionario-de-datos-urgenciasrespiratoriasporsemana.xlsx')

# Target A (regresión): TOTAL respiratorio J00-J98, Sección 1 (consultas de urgencia).
# OrdenCausa=3 = "TOTAL CAUSA SISTEMA RESPIRATORIO J00-J98" (suma que YA calcula el sistema).
# ¡Filtrar por el código, no por la glosa! (mojibake). No sumar subcausas (evita doble conteo).
ORDENCAUSA_TARGET = 3
# Grupos etarios que se conservan como PREDICTORES (estructura de la demanda), no como target:
GRUPOS_EDAD_PREDICTORES = {
    "n_0a4": ["NumMenor1Anio", "Num1a4Anios"],
    "n_5a14": ["Num5a14Anios"],
    "n_65mas": ["Num65oMas"],
}

# Target B (clasificación): alta_demanda = sobrecarga / estrés agudo (rolling, sin fuga — Art. II).
# Enmienda 2026-07-06 — LÍNEA BASE ROBUSTA: se reemplaza la media±σ de 4 semanas (ruidosa: σ sobre
# 4 puntos es inestable y la media persigue a la propia serie) por MEDIANA + k·MAD de 8 semanas.
# alta_demanda = 1 si n_atenciones(w) > mediana(w-8..w-1) + K_SIGMA * (1.4826 * MAD(w-8..w-1)) del centro.
# El factor 1.4826 escala el MAD para que k mantenga la misma interpretación que un múltiplo de σ
# en datos ~normales, así k=1.5 sigue siendo comparable. Sube el techo del modelo (PR-AUC 0.57→0.69,
# validado en scratchpad/diag_ceiling). Registrado en specs/bitacora/bitacora_experimentos.md.
K_SIGMA = 1.5        # margen del umbral, ahora multiplica el MAD escalado (barrer {1.0,1.5,2.0} en train — D9)
VENTANA_BASE = 8     # nº de semanas previas para la línea base móvil robusta (antes 4)
MAD_SCALE = 1.4826   # escala MAD→σ (consistencia normal); umbral = mediana + K_SIGMA*MAD_SCALE*MAD

# === Fuente 2: WHO FluNet — señal viral nacional (feature "¿cuándo?", EN MANO) ===
# Serie semanal nacional de positividad VRS + influenza (consolida el reporte del ISP).
# Reemplaza el scraping de ~181 PDFs del ISP. Doc: dataset_salud/fuentes_datos_flunet.md
FLUNET_CSV = os.path.join(DATASET_SALUD_DIR, 'flunet_chile_viral_semanal.csv')
FLUNET_ENDPOINT = "https://xmart-api-public.who.int/FLUMART/VIW_FNT?$format=csv&$filter=COUNTRY_CODE eq 'CHL'"
# Positividad = detecciones / procesadas (elegir un ORIGIN_SOURCE, no mezclar denominadores):
#   pos_vrs = RSV / RSV_PROCESSED  ·  pos_flu = INF_ALL / SPEC_PROCESSED_NB
# Caveat: RSV_PROCESSED vacío en 2023 → usar SPEC_PROCESSED_NB (ver fuentes_datos_flunet.md §4 — D8).
FLUNET_ORIGIN_SOURCE = "SENTINEL"  # estándar OMS; NONSENTINEL es alternativa (muestra mayor)

# === Fuente 3: SINCA (MP2.5) — enriquecimiento ambiental OPCIONAL (Art. V) ===
SINCA_BASE_URL = "https://sinca.mma.gob.cl"
# Mapeo estación → comuna documentado en dataset_salud/estaciones_sinca_rm_mapeo.md

# === Fuente 4: DMC (temp. mínima, precipitación) — enriquecimiento ambiental OPCIONAL (Art. V) ===
DMC_BASE_URL = "https://climatologia.meteochile.gob.cl"

# === Atributos de red ===
RADIO_VECINDAD_KM = 3.0  # radio para n_centros_vecinos (haversine desde lat/long — D5)

# === Rutas de archivos legacy (dataset asistencia) ===
ASISTENCIA_CRUDA_DICIEMBRE_2025 = os.path.join(DATASET_DIR, '20260107_Asistencia_DICIEMBRE_2025_20260106_WEB.csv')
ASISTENCIA_SANTIAGO_DICIEMBRE_2025 = os.path.join(DATASET_DIR, '20260107_Asistencia_DICIEMBRE_2025_20260106_WEB_SANTIAGO.csv')
COD_PRO_SANTIAGO = 131

# ─────────────────────────────────────────────────────────
# LEGACY — track "valor incremental del MP2.5 sobre la crisis obstructiva pediátrica" (comuna × semana).
# Parqueado (README dataset_salud: "disponible si se reincorpora"). NO usado por el proyecto actual.
# Se conserva como referencia; descomentar solo si se retoma esa línea de trabajo.
# ─────────────────────────────────────────────────────────
# UNIDAD_ANALISIS_LEGACY = 'comuna'            # ComunaCodigo × Anio × SemanaEstadistica
# ORDENCAUSA_TARGET_LEGACY = 8                 # Crisis obstructiva bronquial J40-J46 (pediátrico)
# ORDENCAUSA_SENSIBILIDAD_0A4 = [8, 7]         # + bronquiolitis J20-J21
# TARGET_FOCO_LEGACY = "0a4"                   # target de TASA pediátrica 0–4 (5a14 para contraste)
# INE_BASE_URL = "https://www.ine.gob.cl"      # denominador poblacional para la TASA (proyecciones)
