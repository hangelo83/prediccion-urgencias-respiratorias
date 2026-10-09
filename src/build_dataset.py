import os
import sys
import pandas as pd
import numpy as np
import unicodedata

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from configuraciones.configuraciones import (
    DEIS_PARQUET,
    PANEL_PARQUET,
    REGION_CODIGO_RM,
    COMUNAS_ESCENARIO_A,
    ANIO_INICIO,
    ANIO_FIN,
    ORDENCAUSA_TARGET,
    K_SIGMA,
    VENTANA_BASE,
    MAD_SCALE,
    RADIO_VECINDAD_KM,
    FLUNET_CSV,
    FLUNET_ORIGIN_SOURCE,
)


def normalize_text(text):
    if pd.isna(text):
        return text
    text = str(text).upper().strip()
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    return text


def haversine(lat1, lon1, lat2, lon2):
    """Distancia en km entre coordenadas (vectorizable con arrays de numpy)."""
    R = 6371.0
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c


def build_dataset():
    """
    Reconstruye el panel analítico centro × semana (PANEL_PARQUET) a partir del crudo DEIS
    y la serie viral FluNet. Réplica fiel del notebook 002_eda_dataset.ipynb (fuente autoritativa),
    empaquetada como script para el pipeline ETL automatizado.
    """
    print("Iniciando construcción del dataset (centro x semana)...")
    print(f"Cargando {DEIS_PARQUET}...")
    df_raw = pd.read_parquet(DEIS_PARQUET)

    # -------------------------------------------------------------
    # Validación Estructural (T06)
    # -------------------------------------------------------------
    columnas_requeridas = ['EstablecimientoCodigo', 'ComunaCodigo', 'RegionCodigo', 'Anio', 'SemanaEstadistica', 'NumTotal']
    columnas_faltantes = [c for c in columnas_requeridas if c not in df_raw.columns]
    if columnas_faltantes:
        raise ValueError(f"Fallo de integridad: Faltan las siguientes columnas en el crudo DEIS: {columnas_faltantes}")
    if len(df_raw) < 1000:
        raise ValueError(f"Fallo de integridad: El archivo crudo tiene muy pocas filas ({len(df_raw)}). Posible corrupción.")
    
    # -------------------------------------------------------------
    # Filtrado Border-weeks (T05)
    # -------------------------------------------------------------
    current_year, current_week, _ = pd.Timestamp.today().isocalendar()
    print(f"Semana ISO actual del sistema: {current_year}-W{current_week:02d}. Descartando esta semana y futuras por incompletitud.")
    filas_antes = len(df_raw)
    df_raw = df_raw[~((df_raw['Anio'] == current_year) & (df_raw['SemanaEstadistica'] >= current_week))]
    print(f"Se descartaron {filas_antes - len(df_raw)} filas correspondientes a border-weeks o fechas futuras.")

    # -------------------------------------------------------------
    # T03: Filtrado (Escenario A) — Región RM, años del proyecto y comunas objetivo
    # -------------------------------------------------------------
    print("Ejecutando T03: Filtrado Escenario A...")
    df = df_raw[
        (df_raw['RegionCodigo'].astype(str).str.replace(r'\.0$', '', regex=True) == str(REGION_CODIGO_RM)) &
        (df_raw['Anio'].between(ANIO_INICIO, ANIO_FIN))
    ].copy()

    df = df.dropna(subset=['EstablecimientoCodigo', 'ComunaCodigo'])

    comunas_escenario_norm = [normalize_text(c) for c in COMUNAS_ESCENARIO_A]
    df['ComunaGlosa_Norm'] = df['ComunaGlosa'].apply(normalize_text)
    df = df[df['ComunaGlosa_Norm'].isin(comunas_escenario_norm)]

    df['Latitud'] = df['Latitud'].astype(str).str.replace(',', '.').astype(float)
    df['Longitud'] = df['Longitud'].astype(str).str.replace(',', '.').astype(float)

    print(f"  Filtrado completado: {df['EstablecimientoCodigo'].nunique()} establecimientos en {df['ComunaCodigo'].nunique()} comunas.")
    df = df.drop(columns=['ComunaGlosa_Norm'])

    # -------------------------------------------------------------
    # T04 & T05: Causa-target y Panel base
    # -------------------------------------------------------------
    print("Ejecutando T04 & T05: Causa-target y Panel base...")
    df_atenciones = df[df['OrdenCausa'] == ORDENCAUSA_TARGET].copy()
    df_atenciones['n_0a4'] = df_atenciones['NumMenor1Anio'] + df_atenciones['Num1a4Anios']
    df_atenciones['n_5a14'] = df_atenciones['Num5a14Anios']
    df_atenciones['n_65mas'] = df_atenciones['Num65oMas']
    df_atenciones = df_atenciones.rename(columns={'NumTotal': 'n_atenciones'})

    df_hosp = df[df['OrdenCausa'] == 33].copy()
    df_hosp = df_hosp[['EstablecimientoCodigo', 'Anio', 'SemanaEstadistica', 'NumTotal']].rename(columns={'NumTotal': 'n_hosp_resp'})

    keys = ['EstablecimientoCodigo', 'Anio', 'SemanaEstadistica']
    attrs = df_atenciones[['EstablecimientoCodigo', 'TipoUrgencia', 'NivelComplejidad',
                           'ServicioSaludCodigo', 'ComunaCodigo', 'Latitud', 'Longitud']].drop_duplicates()

    panel = df_atenciones[keys + ['n_atenciones', 'n_0a4', 'n_5a14', 'n_65mas']]
    panel = pd.merge(panel, df_hosp, on=keys, how='left')
    panel['n_hosp_resp'] = panel['n_hosp_resp'].fillna(0).astype(int)
    panel = pd.merge(panel, attrs, on='EstablecimientoCodigo', how='left')

    if panel.duplicated(subset=keys).any():
        print("ADVERTENCIA: La llave (Establecimiento, Año, Semana) no es única en el panel.")
    else:
        print(f"  Panel construido correctamente. Filas: {len(panel)}. Llave única: OK.")

    # -------------------------------------------------------------
    # T06: Timeline continuo + semanas faltantes (rellenar con 0)
    # -------------------------------------------------------------
    print("Ejecutando T06: Timeline continuo...")
    timeline = df_raw[df_raw['Anio'].between(ANIO_INICIO, ANIO_FIN)][['Anio', 'SemanaEstadistica']].drop_duplicates().sort_values(['Anio', 'SemanaEstadistica'])
    centros = panel['EstablecimientoCodigo'].unique()
    timeline_tuples = [tuple(x) for x in timeline.to_numpy()]
    full_idx = pd.MultiIndex.from_tuples([(c, a, s) for c in centros for (a, s) in timeline_tuples], names=keys)

    panel = panel.set_index(keys).reindex(full_idx).reset_index()

    num_cols = ['n_atenciones', 'n_0a4', 'n_5a14', 'n_65mas', 'n_hosp_resp']
    panel[num_cols] = panel[num_cols].fillna(0).astype(int)

    panel = panel.drop(columns=attrs.columns.drop('EstablecimientoCodigo'), errors='ignore')
    panel = pd.merge(panel, attrs, on='EstablecimientoCodigo', how='left')

    # -------------------------------------------------------------
    # T07 & T08: Targets. Target A = n_atenciones (regresión).
    # Target B (alta_demanda) — LÍNEA BASE ROBUSTA (Enmienda 2026-07-06):
    #   umbral = mediana(w-VENTANA..w-1) + K_SIGMA · (MAD_SCALE · MAD(w-VENTANA..w-1)) del propio centro.
    #   shift(1) garantiza ausencia de fuga (solo info ≤ t-1, Art. II).
    # -------------------------------------------------------------
    print("Ejecutando T07 & T08: Targets (base robusta mediana+MAD)...")
    panel = panel.sort_values(['EstablecimientoCodigo', 'Anio', 'SemanaEstadistica'])
    g = panel.groupby("EstablecimientoCodigo")["n_atenciones"]

    min_p = max(4, VENTANA_BASE // 2)
    base_med = g.shift(1).rolling(VENTANA_BASE, min_periods=min_p).median()
    base_mad = g.shift(1).rolling(VENTANA_BASE, min_periods=min_p).apply(
        lambda w: np.median(np.abs(w - np.median(w))), raw=True)

    panel["umbral_alta_demanda"] = base_med + K_SIGMA * MAD_SCALE * base_mad
    is_high = panel["n_atenciones"] > panel["umbral_alta_demanda"]
    panel["alta_demanda"] = is_high.astype("Int8")
    panel.loc[panel["umbral_alta_demanda"].isna(), "alta_demanda"] = pd.NA

    print(f"  Tasa de alta_demanda: {panel['alta_demanda'].mean() * 100:.1f}%")
    print(f"  Arranque en frío (NAs): {panel['alta_demanda'].isna().sum()}")

    # -------------------------------------------------------------
    # T09: Señal viral nacional FluNet (pos_vrs, pos_flu) — join por año/semana ISO
    # -------------------------------------------------------------
    print("Ejecutando T09: Señal viral FluNet...")
    df_flu = pd.read_csv(FLUNET_CSV)
    df_flu = df_flu[df_flu['ORIGIN_SOURCE'] == FLUNET_ORIGIN_SOURCE].copy()

    # RSV_PROCESSED vacío/0 en 2023 → usar SPEC_PROCESSED_NB como denominador (caveat D8).
    df_flu['RSV_PROCESSED_EFF'] = df_flu['RSV_PROCESSED'].fillna(df_flu['SPEC_PROCESSED_NB'])
    df_flu['RSV_PROCESSED_EFF'] = np.where(df_flu['RSV_PROCESSED_EFF'] == 0, df_flu['SPEC_PROCESSED_NB'], df_flu['RSV_PROCESSED_EFF'])

    df_flu['pos_vrs'] = (df_flu['RSV'] / df_flu['RSV_PROCESSED_EFF']).replace([np.inf, -np.inf], np.nan).fillna(0)
    df_flu['pos_flu'] = (df_flu['INF_ALL'] / df_flu['SPEC_PROCESSED_NB']).replace([np.inf, -np.inf], np.nan).fillna(0)

    df_flu_join = df_flu[['ISO_YEAR', 'ISO_WEEK', 'pos_vrs', 'pos_flu']].copy()
    panel = pd.merge(panel, df_flu_join, left_on=['Anio', 'SemanaEstadistica'],
                     right_on=['ISO_YEAR', 'ISO_WEEK'], how='left')
    panel = panel.drop(columns=['ISO_YEAR', 'ISO_WEEK'])
    cobertura = (~panel['pos_vrs'].isna()).mean() * 100
    print(f"  Cobertura del join viral: {cobertura:.1f}%")

    # -------------------------------------------------------------
    # T10 & T11: Atributo de red — nº de centros vecinos en radio (haversine)
    # -------------------------------------------------------------
    print("Ejecutando T10 & T11: Centros vecinos (haversine)...")
    n_vecinos = {}
    for _, row in attrs.iterrows():
        dists = haversine(row['Latitud'], row['Longitud'], attrs['Latitud'], attrs['Longitud'])
        vecinos = ((dists <= RADIO_VECINDAD_KM) & (dists > 0.0001)).sum()
        n_vecinos[row['EstablecimientoCodigo']] = int(vecinos)
    panel['n_centros_vecinos'] = panel['EstablecimientoCodigo'].map(n_vecinos)

    # -------------------------------------------------------------
    # T13: QC final y escritura del panel
    # -------------------------------------------------------------
    is_unique = panel.duplicated(subset=keys).sum() == 0
    print(f"  QC llave única: {is_unique}")
    print(f"  Filas finales: {len(panel)} | Columnas: {panel.shape[1]}")

    os.makedirs(os.path.dirname(PANEL_PARQUET), exist_ok=True)
    panel.to_parquet(PANEL_PARQUET, index=False)
    print(f"Panel guardado en {PANEL_PARQUET}")
    return panel


if __name__ == "__main__":
    build_dataset()
