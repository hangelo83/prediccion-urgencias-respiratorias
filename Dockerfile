# Build desde la RAÍZ del proyecto (NO desde app_dashboard/).
# La app sirve, además del backend en app_dashboard/, la presentación y entregas/
# que viven en la raíz; por eso el contexto de build es el proyecto completo.
FROM python:3.12-slim

WORKDIR /app

# Dependencias primero (aprovecha la cache de capas de Docker)
COPY app_dashboard/requirements.txt ./app_dashboard/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends build-essential libgomp1 \
    && pip install --no-cache-dir -r app_dashboard/requirements.txt \
    && apt-get remove -y build-essential \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copiamos el proyecto. El .dockerignore excluye datasets/notebooks pesados;
# panel.parquet ya viene pre-construido en app_dashboard/data/.
COPY . .

# El servidor se ejecuta desde app_dashboard/ para que
# 'from modelo import ...' y 'from configuraciones.configuraciones import ...'
# resuelvan. PROJECT_ROOT se calcula desde __file__ y apunta a /app,
# donde están presentacion_resultados_v2.html y entregas/.
WORKDIR /app/app_dashboard

# Cloud Run inyecta $PORT (por defecto 8080).
CMD exec uvicorn serve:app --host 0.0.0.0 --port ${PORT:-8080}
