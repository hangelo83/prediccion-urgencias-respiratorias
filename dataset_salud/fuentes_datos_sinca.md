# Fuente: SINCA (MMA) — Calidad del aire (MP2.5) y meteorología

> 🟡 **PARCIALMENTE CONFIRMADO (2026-07-06).** Se confirmaron los identificadores de estación,
> parámetros y el patrón de URL (responden HTTP 200), pero **SINCA es un portal legacy de frames +
> gráfico servido como imagen**: no expone un CSV limpio por los endpoints obvios. La ruta de
> extracción "en limpio" queda como **decisión abierta** (ver §4). Documentado para no perder el
> hallazgo. Estándar espejo de `fuentes_datos_flunet.md`.

## 1. Qué es y rol en el proyecto

Calidad del aire (MP2.5, MP10, gases) y meteorología (T°, HR, viento) de la red **SINCA — MMA**.
Es el **enriquecimiento ambiental OPCIONAL** (Constitución Art. V y VIII): se une al panel DEIS
`centro × semana` por la **comuna del centro**, para la **ablación** (¿el MP2.5/clima mejora sobre
el control viral + inercia?). El modelo base **no** depende de este cruce.

## 2. Identificadores confirmados (estación piloto: La Florida)

- Ficha portal: <https://sinca.mma.gob.cl/index.php/estacion/index/id/262> (el `id/262` es solo la
  página; **no** es el código de datos).
- **Código de datos SINCA:** región `RM`, estación **`D12`**. Base de datos:
  `https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.htmlindico2.cgi`
- **Macros por parámetro** (`macropath` + `macro`):

| Parámetro | macropath | macro (diario / horario) |
|---|---|---|
| MP2.5 | `./RM/D12/Cal/PM25` | `PM25.diario.diario` / `PM25.horario.horario` |
| MP10 | `./RM/D12/Cal/PM10` | `PM10.diario.diario` / `PM10.horario.horario` |
| Temperatura | `./RM/D12/Met/TEMP` | `horario_000` (y variantes `horario_003…`) |
| Humedad rel. | `./RM/D12/Met/RHUM` | `horario_000` |

- **Fechas:** `from` / `to` en formato **`YYMMDD`** (p.ej. `260101`=2026-01-01). Para el frame de
  datos se anexan horas: `from=YYMMDD00&to=YYMMDD23`.
- **URL que responde 200** (menú + gráfico de la serie):
  ```
  https://sinca.mma.gob.cl/cgi-bin/APUB-MMA/apub.htmlindico2.cgi?page=pageLeft&macro=PM25.diario.diario&macropath=./RM/D12/Cal/PM25&from=260101&to=260131
  ```
  El valor real de cada opción del menú es un macro `.ic`, p.ej. `./RM/D12/Cal/PM25//PM25.diario.diario.ic`.

## 3. Obstáculo verificado

- El portal usa **frameset**: `page=pageFrame` → `pageLeft` (menú + gráfico) + `right` (datos).
- El frame de datos (`page=pageRight`) devuelve el **gráfico como imagen server-side** (ZMAP /
  image-map), **no** una tabla ni un arreglo JS de valores.
- `apub.mostrarSerieAcextendida.cgi` → **HTTP 404**. La ficha **no** tiene enlace de
  descarga Excel/CSV. → No hay export limpio evidente.

## 4. Decisión abierta: ruta de extracción (pendiente)

Opciones (a elegir antes de escalar a las 11 estaciones):
1. **Paquete/endpoint comunitario** (p.ej. R `rsinca` o scraper Python conocido) — probado por
   terceros; dependencia externa.
2. **Descarga semi-manual** por estación desde el portal (11 estaciones × pocos parámetros,
   *one-time*) → guardar CSV crudos versionados en `dataset_salud/`. Simple y apto para un diplomado.
3. **Render headless** (Playwright) para forzar la tabla — robusto pero agrega dependencia pesada.
4. **Parseo del gráfico/frames** APUB — frágil, no recomendado.

## 5. Pendiente para las otras 10 comunas

Falta mapear el **código `D-xx`** de cada estación (se lee en su ficha, igual que `D12` para La
Florida): Santiago/Parque O'Higgins, Las Condes, Independencia, Pudahuel, Cerro Navia, El Bosque,
Puente Alto, Quilicura, Cerrillos, Talagante. Ver `estaciones_sinca_rm_mapeo.md`.

## 6. DMC (precipitación) — pendiente

`climatologia.meteochile.gob.cl` responde (HTTP 200) pero el endpoint de datos **no** es el
probado (`/application/datos/getDatosRecientesEma/<cod>` → 404). Falta identificar la API real de
datos históricos EMA (precipitación / T° mínima). Se documentará en `fuentes_datos_dmc.md` al confirmarla.
