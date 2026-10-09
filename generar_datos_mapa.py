# -*- coding: utf-8 -*-
"""
Genera entregas/datos_mapa.js con los 49 centros geolocalizados (para el 'over' del mapa
en la presentación). Lee coords reales del panel y nombres del mapping.
"""
import json, os, sys
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

COMUNA_NAMES = {
    13101: "Santiago", 13102: "Cerrillos", 13103: "Cerro Navia",
    13105: "El Bosque", 13108: "Independencia", 13110: "La Florida",
    13114: "Las Condes", 13124: "Pudahuel", 13125: "Quilicura",
    13201: "Puente Alto", 13601: "Talagante",
}

df = pd.read_parquet("app_dashboard/data/panel.parquet")
mapping = json.load(open("app_dashboard/data/centros_mapping.json", encoding="utf-8"))

# Un registro por centro (coords/comuna son constantes por centro)
cols = ["EstablecimientoCodigo", "ComunaCodigo", "Latitud", "Longitud", "TipoUrgencia", "NivelComplejidad"]
uni = df[cols].dropna(subset=["Latitud", "Longitud"]).drop_duplicates("EstablecimientoCodigo")

centros = []
for _, r in uni.iterrows():
    cod = str(int(r["EstablecimientoCodigo"]))
    centros.append({
        "cod": cod,
        "nombre": mapping.get(cod, cod),
        "comuna": COMUNA_NAMES.get(int(r["ComunaCodigo"]), str(r["ComunaCodigo"])),
        "tipo": str(r["TipoUrgencia"]),
        "lat": round(float(r["Latitud"]), 5),
        "lon": round(float(r["Longitud"]), 5),
    })

centros.sort(key=lambda c: (c["comuna"], c["nombre"]))

print(f"Centros: {len(centros)} | Comunas: {len(set(c['comuna'] for c in centros))}")
lats = [c["lat"] for c in centros]; lons = [c["lon"] for c in centros]
print(f"Lat [{min(lats)}, {max(lats)}]  Lon [{min(lons)}, {max(lons)}]")
por_comuna = {}
for c in centros:
    por_comuna[c["comuna"]] = por_comuna.get(c["comuna"], 0) + 1
print("Por comuna:", por_comuna)

os.makedirs("entregas", exist_ok=True)
with open("entregas/datos_mapa.js", "w", encoding="utf-8") as f:
    f.write("// Generado por generar_datos_mapa.py — 49 centros geolocalizados (coords reales)\n")
    f.write("window.CENTROS = " + json.dumps(centros, ensure_ascii=False) + ";\n")
print("\nEscrito: entregas/datos_mapa.js")
