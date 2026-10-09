# Fuente: ISP — Vigilancia Centinela de Virus Respiratorios

> ⚪ **FUERA DE ALCANCE (2026-07-05).** El proyecto pivotó a *predicción de saturación de urgencias
> por centro* (núcleo solo-DEIS; ambiente SINCA/DMC opcional). La vigilancia viral del ISP **ya no
> forma parte del plan** porque requiere scrapear ~181 PDFs semanales (mayor riesgo para el
> cronograma). Esta documentación **se conserva intacta** por si se reincorpora como predictor
> opcional adicional de la demanda. No borrar.

> Documentación técnica para la ingesta de datos. Última actualización: 2026-07-05.

## 1. Portal y URLs

### Portal de informes (listado por año)
```
https://www.ispch.gob.cl/biomedico/vigilancia-de-laboratorio/ambitos-de-vigilancia/vigilancia-virus-respiratorios/informes-virus-respiratorios/?y={AÑO}
```

Ejemplo: `?y=2026`, `?y=2025`, `?y=2024`, `?y=2023`

### PDFs individuales (un PDF por semana epidemiológica)

Patrón de URL (ejemplo SE-25 de 2026):
```
https://www.ispch.gob.cl/wp-content/uploads/2026/07/Informe-circulacion-virus-respiratorios-SE25-30-06-2026-V2.pdf
```

> ⚠️ **El patrón de URL no es 100% predecible**: incluye la fecha de publicación y
> a veces un sufijo de versión (`-V2`). Se recomienda **scrapear los links desde el
> portal HTML** (tabla con columnas `Semana | Enlace`) en vez de construir URLs.

### Cobertura temporal verificada

| Año  | ¿Informes? | Semanas   | Notas |
|------|-----------|-----------|-------|
| 2026 | ✅ Sí      | SE 1–25   | En curso (hasta 30-jun-2026) |
| 2025 | ✅ Sí      | ~52       | Completo |
| 2024 | ✅ Sí      | ~52       | Completo |
| 2023 | ✅ Sí      | ~52       | Completo |
| 2022 | ✅ Sí      | ~52       | Completo (pero excluido del proyecto) |
| 2021 | ✅ Sí      | SE 1–52   | Completo (COVID, excluido) |
| 2020 | ✅ Sí      | SE 1–53   | Completo (COVID, excluido) |
| 2019 | ✅ Sí      | SE 1–51   | Completo |
| 2018 | ⚠️ Parcial | SE 36–51  | Solo ~16 semanas |
| 2017 | ❌ Vacío   | —         | Tabla sin datos en portal |
| 2015 | ❌ Vacío   | —         | Tabla sin datos |
| 2014 | ❌ Vacío   | —         | Tabla sin datos |

**Ventana del proyecto: 2023–2026** (~181 semanas × 11 comunas ≈ 2.000 obs).

---

## 2. Estructura del PDF (ejemplo: SE-25, 2026, 10 páginas)

### Página 1 — Resumen ejecutivo
- Total de casos analizados, casos positivos, nº de virus detectados
- Positividad total (%)
- Desglose por virus: SARS-CoV-2, Metapneumovirus, Influenza B, Influenza A,
  Parainfluenza, Adenovirus, **VRS**, Rinovirus, OVR

### Páginas 2-3 — Figura 1: Serie temporal
- Gráfico de área apilada: circulación de cada virus por SE, Chile 2022-2026
- Eje derecho: **% de positividad** (línea roja) ← variable principal
- **No se extrae de la figura**; el dato numérico está en la Tabla 1

### Página 3 — Tabla 1: Acumulados por SE y año (★ TABLA PRINCIPAL PARA EXTRACCIÓN)
Columnas:
```
Año | SE | Nº casos positivos | Nº virus positivos | VRS | Adv | Para | Inf A | Inf B | Meta | SARS-CoV-2 | Rino | OVR
```
- Nivel: **Nacional × SE**
- Es la tabla que alimenta `positividad_viral_semanal.parquet`
- Positividad = `Nº virus positivos / Nº casos analizados` (el denominador viene del resumen)

### Páginas 3-4 — Tabla 2: Detecciones por centro centinela (★ TABLA PARA PROXY REGIONAL)
Columnas:
```
Hospital Centinela | Total de casos | Nº casos positivos | Nº virus positivos | VRS | Adv | Para | Inf A | Inf B | Meta | SARS-CoV-2 | Rino | OVR
```
- Nivel: **Centro centinela × SE**
- Se agrega por Servicio de Salud para obtener proxy regional

### Página 5 — Figura 2: Desglose por grupo etario
- Grupos: <1 | 1-4 | 5-14 | 15-54 | 55-64 | ≥65
- Muestra qué virus domina en cada grupo
- **Útil para validación** pero difícil de extraer automáticamente (es gráfico)

---

## 3. Mapeo Centro Centinela → Servicio de Salud → Comunas del Proyecto

### Centinelas Hospitalarios

| Centro Centinela ISP | Servicio de Salud | Comunas del proyecto |
|---|---|---|
| R.M. Occidente Félix Bulnes | SSMOcc | **Cerro Navia, Pudahuel** |
| R.M. Occidente San Juan de Dios | SSMOcc | (Quinta Normal — no en proyecto, pero refuerza SSMOcc) |
| R.M. Sur Exequiel González C. | SSMS | **El Bosque** |
| R.M. Suroriente Padre Hurtado | SSMSO | **Puente Alto, La Florida** |
| R.M. Oriente Hospital del Tórax | SSMOr | **Las Condes** (especializado, sesgo) |
| R.M. Oriente Hospital Militar | SSMOr | **Las Condes** (0 datos en SE-25) |

### Centinelas Ambulatorios

| Centro Centinela ISP | Servicio de Salud | Comunas del proyecto |
|---|---|---|
| Santiago, Consultorio Steeger | SSMOcc | **Cerro Navia** (directo) |
| Santiago, Consultorio Avendaño | SSMC | **Santiago** |
| Santiago, Consultorio 5 | SSMC | **Santiago** |
| Santiago, Consultorio Barros Luco | SSMS | **El Bosque** |
| Santiago, Consultorio Arriztía | SSMC | **Santiago / Cerrillos** |

### Cobertura por comuna

| Comuna | Servicio de Salud | Centinela(s) asignable(s) | Calidad |
|---|---|---|---|
| Cerro Navia | SSMOcc | Félix Bulnes + Steeger | 🟢 Excelente |
| Pudahuel | SSMOcc | Félix Bulnes | 🟢 Bueno |
| Talagante | SSMOcc | (agrupado por SS) | 🟡 Aceptable |
| El Bosque | SSMS | Exequiel González + Barros Luco | 🟢 Bueno |
| Puente Alto | SSMSO | Padre Hurtado | 🟢 Bueno |
| La Florida | SSMSO | Padre Hurtado | 🟢 Bueno |
| Santiago | SSMC | Avendaño + Consultorio 5 + Arriztía | 🟢 Excelente |
| Cerrillos | SSMC | (Arriztía por SS Central) | 🟡 Aceptable |
| Independencia | SSMN | ⚠️ Sin centinela | 🔴 Fallback nacional |
| Quilicura | SSMN | ⚠️ Sin centinela | 🔴 Fallback nacional |
| Las Condes | SSMOr | Hospital del Tórax (especializado) | 🟡 Limitado |

**Estrategia:** Opción A — agregar detecciones por Servicio de Salud.
Independencia y Quilicura usan dato nacional como fallback.

---

## 4. Variables a construir para el modelo

| Variable | Fuente en PDF | Granularidad | Fórmula |
|---|---|---|---|
| `positividad_ss` | Tabla 2 | SS × SE | `Σ virus_positivos(centinelas del SS) / Σ casos(centinelas del SS)` |
| `n_vrs_ss` | Tabla 2, col VRS | SS × SE | Suma de VRS en centinelas del SS |
| `n_influenza_ss` | Tabla 2, Inf A + Inf B | SS × SE | Suma de Influenza en centinelas del SS |
| `positividad_nacional` | Tabla 1 / Resumen | Nacional × SE | Fallback para Independencia, Quilicura |
| `ratio_vrs_total` | Tabla 1 | Nacional × SE | VRS / Nº virus positivos |

---

## 5. Pipeline de extracción sugerido

```
[1] Scrapear portal HTML para obtener lista de URLs de PDFs (2023–2026)
    → verificar: ~181 URLs recolectadas

[2] Descargar todos los PDFs
    → verificar: ~181 archivos en disco

[3] Extraer Tabla 1 y Tabla 2 de cada PDF con pdfplumber/tabula-py
    → verificar: DataFrame con columnas [año, SE, virus...] sin gaps

[4] Agregar Tabla 2 por Servicio de Salud
    → verificar: positividad_ss calculable para 6 SS

[5] Generar positividad_viral_semanal.parquet
    → verificar: merge exitoso con panel DEIS por año-semana

[6] Merge al dataset analítico urg_resp_comuna_semana.parquet
    → verificar: sin NaN en columnas virales
```

**Herramientas:** `pdfplumber` (preferido, tablas regulares con texto vectorial confirmado)
o `tabula-py` como alternativa.
