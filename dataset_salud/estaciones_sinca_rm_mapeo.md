# Mapeo estación SINCA → comuna → variables (Región Metropolitana)

> **Uso:** referencia para el **enriquecimiento ambiental OPCIONAL**. Define las comunas con
> estación de calidad del aire **propia** (Escenario A, 49 centros) para unir MP2.5 y meteorología
> al panel DEIS `centro × semana` (por la comuna del centro). El modelo base no depende de este
> cruce. Fuente: [SINCA — MMA](https://sinca.mma.gob.cl/index.php/region/index/id/M)
> (calidad del aire) y [DMC — climatología](https://climatologia.meteochile.gob.cl/application/index/menuTematicoEmas)
> (precipitación / respaldo meteorológico). Datos horarios con historial 2004+.

## Decisión: Escenario A — solo comunas con estación propia

Cruce **directo, sin imputación**. Alcanza **11 comunas** de la RM, **todas presentes en el
DEIS**. Muestra DEIS resultante: **308.545 filas · 49 establecimientos · 11 comunas**
(2014–2026, semanal).

## Tabla de mapeo

| Estación SINCA | Comuna (clave de cruce) | MP2.5 | Meteo (T°/HR/viento) | Nº estab. DEIS |
|---|---|:---:|:---:|:---:|
| Parque O'Higgins | Santiago | ✅ | ✅ | 6 |
| Las Condes | Las Condes | ✅ | ✅ | 1 |
| Independencia | Independencia | ✅ | ✅ | 4 |
| Pudahuel | Pudahuel | ✅ | ✅ | 5 |
| Cerro Navia | Cerro Navia | ✅ | ✅ | 4 |
| El Bosque | El Bosque | ✅ | ✅ | 4 |
| Puente Alto | Puente Alto | ✅ | ✅ | 7 |
| Quilicura (I y II) | Quilicura | ✅ | ✅ | 3 |
| Cerrillos (I y II) | Cerrillos | ✅ | ✅ | 2 |
| Talagante | Talagante | ✅ | ✅ | 4 |
| La Florida | La Florida | ✅ | ✅ | 9 |

> **La Florida verificada** (ficha SINCA id 262, consultada 2026-07-05): mide **MP2.5 continuo**
> (datos 2000-01-01 → 2026-07-05), MP10, gases y meteorología (temperatura, humedad, viento).
> El set se mantiene en **11 comunas**.

## Contraste de exposición (útil si se activa el ambiente)

El set garantiza comunas en ambos extremos de MP2.5, medidas **directamente**:

- **Baja exposición a MP2.5:** Las Condes (oriente/precordillera).
- **Alta exposición a MP2.5:** Cerro Navia, Pudahuel, El Bosque, Quilicura, Cerrillos
  (norte-poniente/sur de la cuenca).

Da variación ambiental real entre centros de distinta comuna para la **ablación** (¿mejora el
MP2.5 la predicción de saturación?). No es requisito del modelo base.

## Variables a construir (comuna × semana)

Agregando el dato horario/diario de la estación a la semana estadística del DEIS:

| Variable | Cálculo | Fuente |
|---|---|---|
| `mp25_prom` | promedio semanal de MP2.5 | SINCA |
| `mp25_max` | máximo diario de la semana | SINCA |
| `n_dias_preemergencia` | nº de días de preemergencia/emergencia ambiental | SINCA |
| `temp_min_prom` | temperatura mínima media de la semana | SINCA / DMC |
| `n_dias_helada` | nº de días con T° mínima < 0 °C | SINCA / DMC |
| `precip_acum` | precipitación acumulada de la semana | **DMC** (SINCA irregular) |

## Notas para el cruce

- **Clave de unión:** `ComunaGlosa` (o `ComunaCodigo`) del DEIS × `Anio` × `SemanaEstadistica`.
  Los nombres de estas 11 comunas no tienen tildes/ñ → no hay problema de encoding con el DEIS.
- **Precipitación:** SINCA la reporta de forma irregular; obtenerla de la DMC (estaciones
  automáticas) para estas comunas o la más cercana.
- **Semana estadística:** alinear la definición de semana epidemiológica del DEIS con el
  calendario al agregar el dato ambiental diario.
- **Escenario B (sensibilidad, opcional):** ampliar a ~35 comunas del Gran Santiago imputando
  desde la estación más cercana (<~10 km); excluir las ~15 rurales sin estación próxima.