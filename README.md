# Alerta temprana de sobrecarga en urgencias respiratorias

Sistema que anticipa, con una semana de antelación, qué centros de urgencia de la Región
Metropolitana van a superar su propia carga habitual de atenciones respiratorias.

Proyecto Capstone del Diploma en Ciencia de Datos e Inteligencia Artificial,
Universidad de Chile.

## El problema

Cada invierno las urgencias respiratorias saturan la red pública, y eso se planifica: la
campaña de invierno, el refuerzo de turnos y las camas adicionales son decisiones anuales.
Lo que no está previsto es la sobrecarga excepcional, la semana en que un centro concreto se
dispara muy por encima de lo que maneja habitualmente.

La saturación además es despareja. En una misma semana un establecimiento opera sobre
capacidad mientras otro de la misma comuna tiene holgura, y el reparto cambia semana a
semana. La gestión de red opera hoy de forma reactiva, sobre información consolidada que
llega cuando la sobrecarga ya ocurrió.

El modelo no predice el alza estacional, que es conocida. Predice el cruce del umbral propio
de cada centro.

## Cómo está planteado

Clasificación binaria sobre un panel de centro × semana epidemiológica, con 9.456
observaciones de 48 establecimientos entre 2023 y 2026.

La etiqueta es dinámica: un centro está en colapso cuando sus atenciones superan la mediana
móvil de sus doce semanas previas. La referencia es el propio centro y no un umbral común,
porque un umbral absoluto marcaría como colapso la operación normal de los
establecimientos grandes.

Las variables predictoras se agrupan en tres familias: historial propio (cuánto se despegó el
centro de su base, si venía subiendo, hospitalizaciones), presión de la red (qué tan cargados
vienen los centros vecinos, calculado dejando fuera al propio centro) y época del año
(semana epidemiológica codificada en seno y coseno).

## Resultados

Partición temporal: entrenamiento 2023 y 2024, prueba sobre años que el modelo nunca vio.

| Modelo | PR-AUC |
| :--- | :--: |
| Regresión logística (Lasso) | 0,924 |
| Random Forest | 0,942 |
| **XGBoost (elegido)** | **0,948** |

En el punto de operación elegido, con recall objetivo de 83%: precisión 89%, 1.640 colapsos
detectados de 1.976 reales, 209 falsas alarmas. Las falsas alarmas son un costo aceptado,
porque perder una emergencia real cuesta más que preparar un turno de más.

El modelo transfiere a establecimientos que no vio en el entrenamiento. Una validación con
doble holdout, espacial y temporal a la vez, da PR-AUC de 0,881 frente a 0,884 sobre centros
conocidos.

## Tres hallazgos

**Los peaks están en otoño, no en invierno.** La prevalencia de colapso es de 0,92 entre las
semanas 12 y 24, y baja a 0,39 entre la 25 y la 38. Se repite los cuatro años. La causa está
en la etiqueta: la base móvil son las doce semanas previas, así que en marzo la referencia
viene del verano y cualquier alza la supera, mientras que en julio la base ya absorbió el
otoño alto. La etiqueta mide despegue, no carga absoluta.

**Manda el propio centro; el vecindario quedó eclipsado.** Por SHAP, el factor dominante es
cuánto se despegó el centro de su valor típico, con peso 1,81 contra 0,56 de la época del
año. La presión de los centros vecinos fue importante en versiones preliminares, pero al
perfeccionar la señal de calor reciente quedó absorbida por ella y salió del modelo final.

**El ambiente no aporta.** Clima y material particulado no mejoraron las predicciones una vez
que el modelo considera el historial del centro y la época del año.

## Estructura

```
src/                     pipeline de datos
  download_data.py       descarga DEIS y FluNet
  build_dataset.py       construye el panel centro × semana
app_dashboard/           servicio FastAPI
  build_artifacts.py     consolida el panel enriquecido que lee el dashboard
  modelo.py              etiqueta dinámica, features y entrenamiento
  serve.py               API y rutas
  grid_search.py         barrido de configuraciones
  rag_engine.py          recuperación para el asistente
  asistente.py           asistente conversacional sobre Vertex AI
notebooks/               EDA, modelado y ablación ambiental
  historico/             las 28 versiones intermedias del modelado
dataset_salud/           datos ambientales y de clima, más documentación de fuentes
configuraciones/         rutas y constantes compartidas por el pipeline
presentacion_resultados_v2.html    presentación de resultados que sirve la raíz
Dockerfile               imagen del servicio, se construye desde la raíz
```

## Puesta en marcha

Requiere Python 3.11 o superior. El entorno de desarrollo usa 3.13 y la imagen Docker 3.12.

```bash
pip install -r app_dashboard/requirements.txt
```

El dashboard lee `app_dashboard/data/panel.parquet`, que no está versionado. Hay que
construirlo antes, y son tres pasos encadenados:

```bash
python src/download_data.py      # crudo DEIS y FluNet -> dataset_salud/
python src/build_dataset.py      # panel de salud -> dataset_salud/urg_resp_centro_semana.parquet
cd app_dashboard && python build_artifacts.py   # panel enriquecido -> app_dashboard/data/panel.parquet
```

El tercer paso no es opcional: el dashboard lee el panel enriquecido con salud, ambiente y
clima, no el intermedio que produce el segundo.

Después, desde `app_dashboard/`:

```bash
python serve.py
```

El servicio queda en `http://localhost:8080`. La raíz sirve la presentación de resultados y
`/dashboard` el panel interactivo, donde se puede alterar la definición de colapso, la
ventana, la severidad y las variables activas, y ver el efecto en la misma sesión. El
entrenamiento ocurre en la petición y se memoriza en caché; con 4.606 observaciones y 26
variables, XGBoost tarda 0,3 segundos.

## Variables de entorno

Copiar `app_dashboard/.env.example` a `.env` y completar. Las contraseñas no tienen valor por
defecto: el servicio no arranca sin ellas.

| Variable | Para qué |
| :--- | :--- |
| `USER_PRESENTACION`, `PASS_PRESENTACION` | acceso a la presentación en `/` |
| `USER_DASHBOARD`, `PASS_DASHBOARD` | acceso al panel y a la API |
| `GEMINI_API_KEY` | asistente conversacional |
| `GOOGLE_CLOUD_PROJECT`, `VERTEX_LOCATION` | proyecto y región de Vertex AI |

El asistente es opcional. Sin esas tres últimas el resto del panel funciona igual.

## Datos

| Fuente | Qué aporta |
| :--- | :--- |
| DEIS, Ministerio de Salud | atenciones de urgencia por establecimiento y semana |
| FluNet (OMS) e ISP | positividad viral |
| SINCA | material particulado MP2.5 |
| Dirección Meteorológica de Chile | temperatura mínima y precipitación |

Todos son datos abiertos y agregados por establecimiento o comuna y semana. No hay
información de pacientes individuales. El detalle de cada fuente, con su cobertura y su
procedimiento de descarga, está en `dataset_salud/`.

## Qué no está en este repositorio

No están las credenciales ni la configuración de despliegue: ni identificadores de proyecto
en la nube, ni región, ni los archivos de Cloud Build o Firebase. Es deliberado. Para
levantar el proyecto basta con lo documentado más arriba, y el despliegue depende de la
infraestructura de cada quien.

Tampoco están los documentos del curso ni los datasets pesados intermedios.

## Stack

FastAPI y Uvicorn para el servicio, XGBoost y scikit-learn para los modelos, pandas y pyarrow
para los datos, SHAP para interpretabilidad, y Vertex AI para el asistente. Las versiones
exactas están en `app_dashboard/requirements.txt`.
