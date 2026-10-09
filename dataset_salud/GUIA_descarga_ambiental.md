# Guía de Descarga Manual — Datos Ambientales (SINCA + DMC)

> ## ✅ Estado (2026-07-06) — Ablación ambiental COMPLETA
> - **MP2.5 (SINCA): LISTO.** 10 comunas → `ambiente_comuna_semana.parquet`.
> - **Clima (DMC): LISTO.** Temp + precipitación de Quinta Normal (EMA 330020), 84 ZIP mensuales
>   2023–2026 (por minuto) en `dmc_raw/` → `clima_dmc_semana.parquet` (tmín, n_días_helada, precip).
> - **Ablación completa** en `notebooks/004_ablacion_ambiental.ipynb`: A base → B +MP2.5 → C
>   +MP2.5+clima → D +clima. **Veredicto: el ambiente NO mejora el modelo** (ΔGKF-AP ≈ +0.008,
>   dentro del ruido). **Resultado nulo honesto y completo (Art. VIII)** — el base solo-DEIS basta.
>
> *(Las instrucciones de descarga de abajo quedan como referencia reproducible.)*


> **Flujo acordado:** tú bajas los CSV/Excel crudos desde los portales (esta guía te dice
> exactamente qué, de dónde y con qué nombre), los dejas en las carpetas indicadas, y **yo hago la
> agregación semanal + rezagos + cruce + ablación**. Reproducible por archivo, sin scraping frágil.
> Contexto: Plan `specs/004-ablacion-ambiental/plan.md`, Escenario A (11 comunas), ventana **2023–2026**.

---

## Parte A — SINCA (MP2.5 + temperatura), por comuna

Portal: <https://sinca.mma.gob.cl>. Abre la ficha de cada estación (URLs abajo) y descarga, para
cada una, la serie **2023–2026** de:
1. **MP 2,5 — registro diario** (obligatorio).
2. **Temperatura — registro horario/diario** (para temp mínima y heladas; si el portal lo permite).

Guardar en **`dataset_salud/sinca_raw/`** con este nombre: `<comuna>_<param>.csv`
(ej. `la_florida_pm25.csv`, `la_florida_temp.csv`). El formato que entregue el portal (CSV o Excel)
me sirve igual — yo adapto el parser.

### Estaciones (Escenario A, 11 comunas)

| Comuna | Estación SINCA | Ficha (URL) |
|---|---|---|
| Santiago | Parque O'Higgins | https://sinca.mma.gob.cl/index.php/estacion/index/id/273 |
| Las Condes | Las Condes (Acreditada) | …/estacion/index/id/239 |
| Independencia | Independencia | …/estacion/index/id/272 |
| Pudahuel | Pudahuel (Acreditada) | …/estacion/index/id/190 |
| Cerro Navia | Cerro Navia | …/estacion/index/id/228 |
| El Bosque | El Bosque (Acreditada) | …/estacion/index/id/260 |
| Puente Alto | Puente Alto | …/estacion/index/id/233 |
| Quilicura | Quilicura I (o Quilicura) | …/estacion/index/id/149 (alt. 271) |
| Cerrillos | Cerrillos I (o II) | …/estacion/index/id/116 (alt. 290) |
| Talagante | Talagante | …/estacion/index/id/197 |
| La Florida | La Florida (Acreditada) | …/estacion/index/id/262 |

> Para Quilicura y Cerrillos hay dos estaciones: elige la que tenga **MP2.5 continuo** en 2023–2026
> (si dudas, baja ambas y yo me quedo con la de mejor cobertura).

⚠️ **Nota honesta:** el portal SINCA es antiguo (gráfico interactivo). En el navegador, al abrir un
parámetro deberías poder **ver/exportar la serie**; por HTTP no logré confirmar el botón exacto de
export. Si un método no te da el dato, prueba: (a) el ícono de tabla/Excel en el gráfico, o (b)
copiar la tabla a un `.csv`. Si SINCA no deja exportar cómodo, avísame y pasamos al **plan B**
(scraper Python o Playwright) sin problema.

---

## Parte B — DMC (precipitación), regional

Portal: <https://climatologia.meteochile.gob.cl/application/index/menuTematicoEmas> → pestaña
**"Descarga de datos" / "Diarios EMAs"**. La lluvia no varía mucho dentro de la ciudad a escala
semanal, así que basta **1–2 estaciones EMA** para toda la RM:

- **Quinta Normal** (EMA 330020) — serie larga, referencia clásica RM.
- *(opcional)* **Pudahuel / Aeropuerto** como respaldo.

Descargar, período **2023–2026**, la variable **"Agua Caída / Precipitación diaria"** (y si está,
**temperatura mínima**). Guardar en **`dataset_salud/dmc_raw/`** como
`quinta_normal_precip.csv` (y opcional `..._tmin.csv`).

> La temperatura mínima por comuna la tomo de SINCA (Parte A). DMC solo aporta la precipitación
> regional; por eso basta con 1–2 EMAs.

---

## Qué haré yo al recibir los archivos (contrato de procesamiento)

Cuando dejes los CSV en `sinca_raw/` y `dmc_raw/` y me avises, ejecuto:

1. **Parseo** robusto (cualquier formato SINCA/DMC: detecto columna de fecha + valor).
2. **Agregación a `comuna × Anio × SemanaEstadistica`** (alineando la semana epidemiológica del DEIS):
   `mp25_prom`, `mp25_max`, `n_dias_preemergencia` (MP2.5≥110 µg/m³ diario), `temp_min_prom`,
   `n_dias_helada` (T°mín<0), `precip_acum`.
3. **Rezagos `t-1…t-4`** de cada variable (sin fuga, Art. II/VIII).
4. Genero **`dataset_salud/ambiente_comuna_semana.parquet`** y **reporto la cobertura** (% de
   comunas-semana con dato) antes de modelar.
5. **Cruce** con `urg_resp_centro_semana.parquet` por `ComunaCodigo × Anio × SemanaEstadistica`.
6. **Ablación A vs B** (mismo split temporal + GroupKFold que 003), ΔPR-AUC/ΔF1 + SHAP de B →
   veredicto honesto (mejora / no mejora) para la bitácora.

---

## Checklist para ti

- [ ] Bajar MP2.5 diario 2023–2026 de las 11 estaciones → `sinca_raw/<comuna>_pm25.csv`
- [ ] *(si el portal lo permite)* Temperatura de las 11 estaciones → `sinca_raw/<comuna>_temp.csv`
- [ ] Bajar precipitación diaria 2023–2026 (Quinta Normal) → `dmc_raw/quinta_normal_precip.csv`
- [ ] Avisarme → yo corro el pipeline de agregación + ablación

---

## ⚠️ Corrección tras tu primera descarga (2026-07-06)

**El formato de tus CSV es correcto** (separador `;`, coma decimal, encabezado de 4 líneas con el
código de estación, horario con MP10/MP2.5/gases). **Pero solo traen 24 horas** (2026-07-05 08:00 →
2026-07-06 07:00): el export salió con el **rango por defecto (último día)**. Para el proyecto
necesito **2023–2026 completo**.

**Acción:** en el mismo diálogo de exportación, **fija el rango de fechas** `2023-01-01` →
`2026-07-06` y vuelve a descargar. Si el portal limita el rango, hazlo **por año** (4 archivos por
estación) y yo los concateno. Un archivo por estación con MP2.5 basta (no necesitas separar por
parámetro).

**Códigos de datos reales** (leídos de la 1ª línea `"Estacion";Dxx` de tus CSV):

| Comuna | Estación | Código | Nota |
|---|---|---|---|
| Santiago | Parque O'Higgins | D14 | ✅ |
| Las Condes | Las Condes | D13 | ✅ |
| Independencia | Independencia | — | ❌ falta bajar |
| Pudahuel | Pudahuel | D15 | ✅ |
| Cerro Navia | Cerro Navia | D18 | ✅ |
| El Bosque | El Bosque | D17 | ✅ |
| Puente Alto | Puente Alto | D27 | ✅ |
| Quilicura | Quilicura II | D30 | verificar MP2.5 continuo |
| Cerrillos | Cerrillos MÓVIL2 | D35 | ⚠️ estación **móvil** → probar Cerrillos I (fija) |
| Talagante | Talagante | — | ❌ falta bajar |
| La Florida | La Florida | D12 | ✅ |

**Temperatura:** estos export traen solo contaminantes, **sin meteo**. La temp mínima la tomaré de
**DMC** (o bajas el parámetro "Met/Temperatura" de SINCA aparte). No bloquea: **MP2.5 es la variable
estrella de la ablación** → partimos con eso.
