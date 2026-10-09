# -*- coding: utf-8 -*-
"""
Extrae "píldoras de datos" reales para la presentación (presentacion_resultados.html).

Calcula, a partir del panel semana×centro:
  - Total y promedio de atenciones respiratorias.
  - Top comunas por volumen atendido.
  - Top comunas por tasa de sobrecarga (colapso).
  - Mayor alza semanal (% respecto a la semana anterior).

Uso:
    python extraer_pildoras.py

No modifica nada: solo lee los .parquet y muestra texto listo para pegar como píldora.
"""
import json
import os
import sys
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")  # emojis en consola Windows (cp1252)
except Exception:
    pass

# Códigos INE (CUT) de las 11 comunas del Escenario A → nombre legible
COMUNA_NAMES = {
    13101: "Santiago", 13102: "Cerrillos", 13103: "Cerro Navia",
    13105: "El Bosque", 13108: "Independencia", 13110: "La Florida",
    13114: "Las Condes", 13124: "Pudahuel", 13125: "Quilicura",
    13201: "Puente Alto", 13601: "Talagante",
}

# --- 1. Cargar el panel (probamos las rutas conocidas, en orden) -------------
CANDIDATOS = [
    "app_dashboard/data/panel.parquet",
    "dataset_salud/urg_resp_centro_semana.parquet",
]
ruta = next((p for p in CANDIDATOS if os.path.exists(p)), None)
if ruta is None:
    raise SystemExit("No encontré el panel .parquet en las rutas conocidas: " + ", ".join(CANDIDATOS))

df = pd.read_parquet(ruta)
print(f"\n[FUENTE] {ruta}  —  {len(df):,} filas")
print("[COLUMNAS]", list(df.columns))

# --- 2. Detectar nombres de columnas de forma flexible -----------------------
def primera(cols, *candidatas):
    for c in candidatas:
        if c in cols:
            return c
    return None

cols = df.columns
col_atn   = primera(cols, "n_atenciones", "atenciones", "NumTotal")
col_est   = primera(cols, "EstablecimientoCodigo", "centro", "establecimiento")
col_com   = primera(cols, "ComunaGlosa", "ComunaGlosa_Norm", "comuna", "ComunaCodigo")
col_flag  = primera(cols, "alta_demanda", "colapso", "target", "y")
col_anio  = primera(cols, "Anio", "anio", "year")

print(f"[MAPEo] atenciones={col_atn} | centro={col_est} | comuna={col_com} | colapso={col_flag} | anio={col_anio}\n")

# Nombres legibles de comuna si solo hay código
mapa_comuna = {}
if col_com and "Codigo" in col_com and os.path.exists("app_dashboard/data/centros_mapping.json"):
    try:
        mapa_comuna = json.load(open("app_dashboard/data/centros_mapping.json", encoding="utf-8"))
    except Exception:
        pass

def nombre_comuna(v):
    try:
        k = int(v)
        if k in COMUNA_NAMES:
            return COMUNA_NAMES[k]
    except Exception:
        pass
    return mapa_comuna.get(str(v), str(v))

# --- 3. Volumen global -------------------------------------------------------
print("=" * 64)
if col_atn:
    total = int(df[col_atn].sum())
    print(f"📊 Atenciones respiratorias totales: {total:,}")
    if col_anio and df[col_anio].notna().any():
        por_anio = df.groupby(col_anio)[col_atn].sum().astype(int)
        print("   Por año:")
        for a, v in por_anio.items():
            print(f"     {a}: {v:,}")
        print(f"   Promedio anual: {int(por_anio.mean()):,}")
    prom_sc = df[col_atn].mean()
    print(f"🏥 Promedio por semana-centro: {prom_sc:.0f} atenciones")
    if col_est:
        prom_centro = df.groupby(col_est)[col_atn].sum().mean()
        print(f"   Promedio total por centro (todo el período): {int(prom_centro):,}")

# --- 4. Top comunas por volumen ---------------------------------------------
if col_com and col_atn:
    print("\n📍 Top 5 comunas por volumen atendido:")
    top_vol = df.groupby(col_com)[col_atn].sum().sort_values(ascending=False).head(5)
    for c, v in top_vol.items():
        print(f"     {nombre_comuna(c):<28} {int(v):>10,}")

# --- 5. Top comunas por tasa de sobrecarga ----------------------------------
if col_com and col_flag:
    print("\n⚠️  Top 5 comunas por tasa de sobrecarga (colapso):")
    tasa = (df.groupby(col_com)[col_flag].mean() * 100).sort_values(ascending=False).head(5)
    for c, v in tasa.items():
        print(f"     {nombre_comuna(c):<28} {v:>6.1f}%")

# --- 6. Mayor alza semanal ---------------------------------------------------
if col_est and col_atn:
    orden = [c for c in [col_est, col_anio, "SemanaEstadistica"] if c]
    d = df.sort_values(orden).copy()
    d["prev"] = d.groupby(col_est)[col_atn].shift(1)
    d["alza_pct"] = (d[col_atn] / d["prev"] - 1) * 100
    d = d[(d["prev"] >= 20) & d["alza_pct"].notna()]  # evitar % explosivos sobre bases minúsculas
    if len(d):
        top = d.loc[d["alza_pct"].idxmax()]
        est = top[col_est]
        nombre_est = json.load(open("app_dashboard/data/centros_mapping.json", encoding="utf-8")).get(str(est), str(est)) \
            if os.path.exists("app_dashboard/data/centros_mapping.json") else str(est)
        print(f"\n📈 Mayor alza semana-a-semana: +{top['alza_pct']:.0f}%  ({nombre_est})")
        print(f"     de {int(top['prev'])} a {int(top[col_atn])} atenciones en una semana")
        print(f"   Alza semanal promedio (subidas): +{d[d['alza_pct']>0]['alza_pct'].mean():.1f}%")

print("=" * 64)
print("\nCopia los números que te sirvan como nuevas <div class=\"pill\"> en la presentación.")
