# Fuentes de Datos — Índice General

> Documentación técnica de todas las fuentes de datos del proyecto.
> Última actualización: 2026-07-05.

## Fuentes del proyecto

Plan actual: **saturación de urgencias respiratorias por centro × semana** (regresión del volumen
+ clasificación de **sobrecarga**, rolling μ₄+k·σ). El **núcleo va con DEIS/SADU + FluNet** (señal
viral nacional, el "¿cuándo?"); el ambiente (SINCA/DMC) es opcional.

| # | Fuente | Tipo | Archivo de doc. | Rol / Estado |
|---|---|---|---|---|
| 1 | **DEIS / SADU** (urgencias respiratorias) | Parquet (ya descargado) | `diccionario-de-datos-urgenciasrespiratoriasporsemana.xlsx` | 🟢 **Núcleo — en mano** |
| 2 | **WHO FluNet** (viral nacional: VRS + influenza) | CSV (ya descargado) | [`fuentes_datos_flunet.md`](fuentes_datos_flunet.md) | 🟢 **Señal temporal — en mano** |
| 3 | **SINCA** (calidad del aire: MP2.5, temp) | API / descarga web | `estaciones_sinca_rm_mapeo.md` | 🟡 **Opcional** (enriquecimiento) — pendiente |
| 4 | **DMC** (meteorología: temp/precipitación) | API / descarga web | (pendiente documentar) | 🟡 **Opcional** (enriquecimiento) — pendiente |
| 5 | ~~**ISP** (vigilancia viral centinela por región)~~ | PDFs semanales (scraping) | [`fuentes_datos_isp.md`](fuentes_datos_isp.md) | ⚪ **Fuera de alcance** (FluNet lo reemplaza a nivel nacional) |

## Archivos en esta carpeta

| Archivo | Descripción |
|---|---|
| `at_urg_respiratorio_semanal.parquet` | Base DEIS/SADU cruda (~3,56M filas, nacional, 2014-2026) |
| `flunet_chile_viral_semanal.csv` | Serie viral nacional VRS+influenza (FluNet/OMS, 1997-2026) — en mano |
| `diccionario-de-datos-urgenciasrespiratoriasporsemana.xlsx` | Diccionario oficial DEIS |
| `Manual Registro Atenciones Diarias de Urgencia 17122025.pdf` | Manual del sistema SADU |
| `estaciones_sinca_rm_mapeo.md` | Mapeo estación SINCA → comuna (Escenario A, 11 comunas) |
| `fuentes_datos_flunet.md` | **Doc técnica FluNet**: endpoint OMS, estructura, positividad, caveats |
| `fuentes_datos_isp.md` | **Doc técnica ISP**: URLs, estructura PDF, mapeo centinela→SS→comuna, pipeline |

## Configuración centralizada

Todos los endpoints, rutas, parámetros y mapeos están en:
```
configuraciones/configuraciones.py
```

Incluye: ventana temporal (2023–2026), split train/test, comunas Escenario A,
target de regresión (`OrdenCausa=3`) y umbral de clasificación (p90 por centro),
URLs base de las fuentes ambientales opcionales (SINCA, DMC).
