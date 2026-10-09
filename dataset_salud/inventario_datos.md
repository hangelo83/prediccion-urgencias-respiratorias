# Inventario de datos utilizados (2023–2026)

Volumen de datos por variable y año, tal como los consume el modelo. Ventana del proyecto:
**2023–2026**, Región Metropolitana. Generado sobre los archivos reales (`dataset_salud/`, `dataset_mp25/`).

---

## 1. Atenciones respiratorias — DEIS / SADU (target + inercia)
Panel a nivel **centro × semana**. `n_atenciones` es el volumen de urgencias respiratorias (OrdenCausa 3,
total J00–J98); `alta_demanda` (colapso) se deriva de esta serie.

| Año | Semanas | Registros (centro×semana) | Atenciones (pacientes) | Hospitalizaciones |
|---|---:|---:|---:|---:|
| 2023 | 52 | 2.548 | 602.134 | 12.749 |
| 2024 | 52 | 2.548 | 605.272 | 13.614 |
| 2025 | 53 | 2.597 | 551.947 | 15.144 |
| 2026 (parcial) | 27 | 1.323 | 236.010 | 5.662 |
| **Total** | **184** | **9.016** | **1.995.363** | **47.169** |

- **49 establecimientos** en **11 comunas** de la RM.
- Grupos etarios (predictores): **0–4 años** 388.799 · **5–14** 447.331 · **65+** 193.346 atenciones.

## 2. Señal viral — WHO FluNet (¿cuándo?, nacional)
Positividad semanal nacional de **VRS** e **Influenza** (fuente SENTINEL, consolida el reporte del ISP).

| Año | Semanas |
|---|---:|
| 2023 | 52 |
| 2024 | 52 |
| 2025 | 52 |
| 2026 (parcial) | 26 |
| **Total** | **182** |

- Serie **nacional** (misma para toda la RM cada semana). Se cruza por semana ISO con el panel.

## 3. Clima — DMC, EMA Quinta Normal (ambiental opcional)
Temperatura mínima, precipitación acumulada y días de helada, por semana (clima regional).

| Año | Semanas |
|---|---:|
| 2023 | 52 |
| 2024 | 52 |
| 2025 | 52 |
| 2026 (parcial) | 27 |
| **Total** | **183** |

## 4. Contaminación — MP2.5 / SINCA (ambiental opcional, Escenario A)
Nivel **comuna × semana** para las 10 comunas con estación SINCA propia.

| Año | Registros (comuna×semana) |
|---|---:|
| 2023 | 510 |
| 2024 | 519 |
| 2025 | 479 |
| 2026 (parcial) | 241 |
| **Total 2023–2026** | **1.749** |

- **10 comunas**. Fuente cruda: **13 estaciones**, ~**81.949 registros diarios** agregados a semana.

---

## Resumen

| Fuente | Nivel | Unidad temporal | Volumen 2023–2026 |
|---|---|---|---|
| **Atenciones (DEIS/SADU)** | centro × semana | semanal | 9.016 registros · **~2,0 M atenciones** |
| **Viral (FluNet)** | nacional | semanal | 182 semanas |
| **Clima (DMC)** | regional | semanal | 183 semanas |
| **MP2.5 (SINCA)** | comuna × semana | semanal (de diario) | 1.749 registros (de ~82 k diarios) |

**Nota:** El **núcleo del modelo** son las atenciones (DEIS) + señal viral (FluNet). El **clima y MP2.5**
son enriquecimiento **opcional** evaluado por ablación (resultado nulo — no aportan; ver bitácora §4 y §7).
2026 es parcial (año en curso al momento del análisis).
