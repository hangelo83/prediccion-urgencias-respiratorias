# Fuente: WHO FluNet — Vigilancia viral respiratoria de Chile (VRS + Influenza)

> 🟢 **EN MANO.** Descargado y verificado el 2026-07-05. Reemplaza el scraping de ~181 PDFs del
> ISP para obtener la serie viral nacional. Archivo: `flunet_chile_viral_semanal.csv` (312 KB).

## 1. Qué es y por qué

Serie **semanal nacional** de vigilancia de virus respiratorios de Chile, consolidada por la
**OMS (WHO FluNet / GISRS)** a partir de los datos que reporta el **ISP** (Centro Nacional de
Referencia de Influenza desde 1968). Da la **circulación viral (VRS e influenza)** que sirve de
**control temporal** en el baseline del modelo: descuenta la ola epidémica antes de medir el
aporte del MP2.5. Validada de forma independiente por literatura revisada por pares que usa esta
misma red para Chile (Rivas et al., *IJID* 2025; Couto et al., *Lancet Reg Health Am* 2025).

## 2. Cómo se obtuvo (reproducible)

```bash
curl -s 'https://xmart-api-public.who.int/FLUMART/VIW_FNT?$format=csv&$filter=COUNTRY_CODE%20eq%20%27CHL%27' -o flunet_chile_viral_semanal.csv
```

- Endpoint público (API xMart de la OMS), **sin autenticación**.
- Nota: algunos fetchers de navegador descartan el `$filter` y devuelven el dataset global.
  Con `curl` / Python `requests` / R el filtro funciona (verificado).
- Diccionario de datos: `https://xmart-api-public.who.int/FLUMART/VIW_FLU_METADATA?$format=csv`

## 3. Estructura (verificada sobre el archivo real)

- **1.825 filas, solo `COUNTRY_CODE=CHL`, cobertura 1997–2026.** Granularidad: **nacional × semana
  epidemiológica** (`ISO_YEAR`, `ISO_WEEK`, `ISO_WEEKSTARTDATE`).
- **Ventana del proyecto 2023–2026: completa** — VRS, INF_ALL y SPEC_PROCESSED_NB poblados en
  todas las semanas.
- **Columnas clave:**

| Columna | Descripción |
|---|---|
| `RSV` | Nº de detecciones de VRS en la semana |
| `RSV_PROCESSED` | Denominador VRS (muestras procesadas para VRS) |
| `INF_A`, `INF_B`, `INF_ALL` | Detecciones de influenza (A, B, total) |
| `SPEC_PROCESSED_NB` | Denominador influenza (muestras procesadas) |
| `ISO_YEAR`, `ISO_WEEK`, `ISO_WEEKSTARTDATE` | Semana epidemiológica |
| `ORIGIN_SOURCE` | Stream de vigilancia (ver caveats) |

- **Positividad** = detecciones / procesadas:
  `pos_vrs = RSV / RSV_PROCESSED` · `pos_flu = INF_ALL / SPEC_PROCESSED_NB`.
  (Verificado: en invierno 2024 la influenza cae y el VRS sube — peakean en momentos distintos.)

## 4. Caveats (leídos del archivo real — resolver en el EDA)

1. **Dos filas por semana** en años recientes: `ORIGIN_SOURCE` = **SENTINEL** y **NONSENTINEL**
   (`NOTDEFINED` en años antiguos). **Elegir un stream y no mezclar denominadores.** SENTINEL es
   el estándar OMS para positividad (denominador menor, más ruidoso); NONSENTINEL tiene muestra
   mayor (más suave). Decidir en el EDA.
2. **`RSV_PROCESSED` vacío en 2023** (sí desde 2024). Para el VRS de 2023: usar `SPEC_PROCESSED_NB`
   como denominador, o los conteos `RSV` directos.
3. **Solo nacional — sin desglose por región.** Válido como **control temporal** de la ola viral
   (la RM concentra gran parte de los centinela → la serie nacional la representa). Si se quisiera
   positividad específica de la RM, solo el ISP (PDFs) o RedSalud la tienen.
4. **Quiebres de serie:** el panel incorporó SARS-CoV-2 (SE01-2022) y Rinovirus/otros (SE01-2024),
   y el nº de centinela cambió en el tiempo → la composición del denominador varía. Preferir el
   numerador/denominador **específico por virus** (VRS y flu por separado) antes que una positividad
   total; considerar un indicador post-2024.
5. **Rezago de reporte:** FluNet actualiza semanal pero con algo de lag en la semana más reciente
   (irrelevante para entrenamiento retrospectivo 2023–2026).

## 5. Rol en el proyecto

Entra en el **baseline A** (control viral: `pos_vrs`, `pos_flu` rezagadas) — es lo que permite el
**test de valor incremental del MP2.5** (B − A). Ver `entregas/E1-propuesta-viral.md`.
