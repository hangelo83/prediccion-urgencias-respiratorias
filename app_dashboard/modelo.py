import os
import json
import datetime
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import recall_score, precision_score, f1_score, accuracy_score, confusion_matrix, precision_recall_curve, auc
from functools import lru_cache
import shap
import warnings
warnings.filterwarnings('ignore')

from configuraciones.configuraciones import DATA_PATH, MAPPING_PATH, GRID_PATH, MODELO_DEFAULTS

# Nombres de las 11 comunas del Escenario A (RM con estación SINCA propia). El panel solo trae
# ComunaCodigo (ComunaGlosa se descarta en el ETL) — este mapeo es el mismo usado por
# generar_datos_mapa.py para el widget del mapa, es la única fuente de nombres real disponible.
COMUNA_NAMES = {
    13101: "Santiago", 13102: "Cerrillos", 13103: "Cerro Navia",
    13105: "El Bosque", 13108: "Independencia", 13110: "La Florida",
    13114: "Las Condes", 13124: "Pudahuel", 13125: "Quilicura",
    13201: "Puente Alto", 13601: "Talagante",
}

# Global cache for base dataframe
df_base_cache = None

def _next_semana(anio, sem):
    """Semana ISO siguiente a (anio, sem). Usado tanto para generar la fila T+1 como
    para identificar, más tarde, cuál semana de df_future es el pronóstico genuino."""
    next_sem = sem + 1
    next_anio = anio
    if next_sem > 52:
        next_sem = 1
        next_anio += 1
    return next_anio, next_sem

def load_data():
    global df_base_cache
    if df_base_cache is None:
        print("Cargando y procesando features base...")
        df = pd.read_parquet(DATA_PATH)
        df = df.sort_values(['EstablecimientoCodigo', 'Anio', 'SemanaEstadistica']).copy()

        # --- GENERAR SEMANA T+1 (ALERTA FUTURA) ---
        max_anio = df['Anio'].max()
        max_sem = df[df['Anio'] == max_anio]['SemanaEstadistica'].max()
        next_anio, next_sem = _next_semana(max_anio, max_sem)

        future_rows = []
        for centro in df['EstablecimientoCodigo'].unique():
            last_row = df[df['EstablecimientoCodigo'] == centro].iloc[-1].copy()
            last_row['Anio'] = next_anio
            last_row['SemanaEstadistica'] = next_sem
            last_row['n_atenciones'] = np.nan
            future_rows.append(last_row)
            
        if future_rows:
            df = pd.concat([df, pd.DataFrame(future_rows)], ignore_index=True)
            df = df.sort_values(['EstablecimientoCodigo', 'Anio', 'SemanaEstadistica']).copy()

        
        # 1. Lags básicos
        features_to_lag = ['n_atenciones', 'pos_vrs', 'pos_flu', 'n_0a4', 'n_5a14', 'n_65mas']
        for col in features_to_lag:
            for lag in [1, 2, 3]:
                df[f'{col}_lag{lag}'] = df.groupby('EstablecimientoCodigo')[col].shift(lag)
        
        g = df.groupby('EstablecimientoCodigo')['n_atenciones']
        
        # 2. Lags estáticos para v3/v5
        df['roll_mean4'] = g.transform(lambda x: x.shift(1).rolling(4, min_periods=2).mean())
        df['roll_std4']  = g.transform(lambda x: x.shift(1).rolling(4, min_periods=2).std())
        df['roll_mean8'] = g.transform(lambda x: x.shift(1).rolling(8, min_periods=3).mean())
        df['roll_std8']  = g.transform(lambda x: x.shift(1).rolling(8, min_periods=3).std())
        
        df['z_lag1'] = (df['n_atenciones_lag1'] - df['roll_mean4']) / (df['roll_std4'] + 1e-6)
        df['z_lag8'] = (df['n_atenciones_lag1'] - df['roll_mean8']) / (df['roll_std8'] + 1e-6)
        df['ratio_l1_m4'] = df['n_atenciones_lag1'] / (df['roll_mean4'] + 1e-6)
        
        # 3. Momentum
        df['mom_1_2'] = df['n_atenciones_lag1'] - df['n_atenciones_lag2']
        df['mom_2_3'] = df['n_atenciones_lag2'] - df['n_atenciones_lag3']
        df['mom_accel'] = df['mom_1_2'] - df['mom_2_3']
        df['d_flu'] = df['pos_flu_lag1'] - df['pos_flu_lag2']
        df['d_vrs'] = df['pos_vrs_lag1'] - df['pos_vrs_lag2']
        df['viral_x_z'] = df['pos_flu_lag1'] * df['z_lag1']
        df['n_hosp_resp_lag1'] = df.groupby('EstablecimientoCodigo')['n_hosp_resp'].shift(1)
        
        # 4. Estacionalidad
        df['sem_sin'] = np.sin(2 * np.pi * df['SemanaEstadistica'] / 52.0)
        df['sem_cos'] = np.cos(2 * np.pi * df['SemanaEstadistica'] / 52.0)
        
        # 5. Dummies estructurales
        if 'TipoUrgencia' in df.columns:
            df = pd.get_dummies(df, columns=['TipoUrgencia'], drop_first=True)
        if 'NivelComplejidad' in df.columns:
            df = pd.get_dummies(df, columns=['NivelComplejidad'], drop_first=True)
            
        df_base_cache = df
    return df_base_cache

def derive_dynamic_target(df, tipo, k, ventana, severidad=0.0):
    """
    Rederiva la etiqueta 'alta_demanda' y la feature alineada (z_rob).
    También recalcula las métricas de red (presión espacial) porque dependen
    de la alerta rezagada, la cual cambia al cambiar la definición.
    """
    df = df.copy()
    g = df.groupby('EstablecimientoCodigo')['n_atenciones']
    
    # 1. Definir base móvil según la ventana elegida
    if tipo == 'nivel':
        # Default v7/v8: media o mediana
        df['base_movil'] = g.transform(lambda x: x.shift(1).rolling(ventana, min_periods=max(2, ventana//2)).median())
        df['disp_movil'] = g.transform(lambda x: x.shift(1).rolling(ventana, min_periods=max(2, ventana//2)).apply(
            lambda w: np.median(np.abs(w - np.median(w))), raw=True))
        
        # Target (severidad = % mínimo de exceso sobre el umbral para contar como colapso)
        df['umbral'] = (df['base_movil'] + k * (1.4826 * df['disp_movil'])) * (1.0 + severidad)
        df['alta_demanda'] = (df['n_atenciones'] > df['umbral']).astype(int)
        
        # Feature alineada (z_rob_dyn)
        df['z_rob_dyn'] = (df['n_atenciones_lag1'] - df['base_movil']) / (1.4826 * df['disp_movil'] + 1e-6)
        
    elif tipo == 'sobre_tendencia':
        df['base_movil'] = g.transform(lambda x: x.shift(1).rolling(ventana, min_periods=max(2, ventana//2)).mean())
        df['disp_movil'] = g.transform(lambda x: x.shift(1).rolling(ventana, min_periods=max(2, ventana//2)).std())
        df['umbral'] = (df['base_movil'] + k * df['disp_movil']) * (1.0 + severidad)
        df['alta_demanda'] = (df['n_atenciones'] > df['umbral']).astype(int)
        df['z_rob_dyn'] = (df['n_atenciones_lag1'] - df['base_movil']) / (df['disp_movil'] + 1e-6)
        
    elif tipo == 'salto_wow':
        df['base_movil'] = df['n_atenciones_lag1']
        df['disp_movil'] = g.transform(lambda x: x.shift(1).rolling(ventana, min_periods=max(2, ventana//2)).std())
        df['umbral'] = (df['base_movil'] + k * df['disp_movil']) * (1.0 + severidad)
        df['alta_demanda'] = (df['n_atenciones'] > df['umbral']).astype(int)
        df['z_rob_dyn'] = (df['n_atenciones_lag1'] - df['n_atenciones_lag2']) / (df['disp_movil'] + 1e-6)
        
    elif tipo == 'aumento_estandar':
        df['base_movil'] = df['umbral_alta_demanda']
        df['umbral'] = df['base_movil'] * (1.0 + severidad)
        df['alta_demanda'] = (df['n_atenciones'] > df['umbral']).astype(int)
        df['z_rob_dyn'] = (df['n_atenciones_lag1'] - df['base_movil']) / (df['base_movil'] + 1e-6)
        
    elif tipo == 'aumento_reciente':
        df['base_movil'] = g.transform(lambda x: x.shift(1).rolling(ventana, min_periods=max(2, ventana//2)).median())
        df['umbral'] = df['base_movil'] * (1.0 + severidad)
        df['alta_demanda'] = (df['n_atenciones'] > df['umbral']).astype(int)
        df['z_rob_dyn'] = (df['n_atenciones_lag1'] - df['base_movil']) / (df['base_movil'] + 1e-6)

    elif tipo == 'estacional':
        # V4: Umbral Estacional-Adaptativo. Base = climatología de ESTA MISMA semana del año
        # (mediana usando solo años ESTRICTAMENTE anteriores, sin fuga), corregida por si el año
        # en curso viene corriendo más caliente/frío que su propio histórico reciente. A diferencia
        # de V3 (que solo mira las últimas `ventana` semanas), esto anticipa el giro estacional en
        # vez de perseguirlo con rezago.
        clim_g = df.groupby(['EstablecimientoCodigo', 'SemanaEstadistica'])['n_atenciones']
        df['clima_semana'] = clim_g.transform(lambda x: x.shift(1).expanding().median())

        # Fallback para el primer año sin histórico previo (ej. 2023): tendencia reciente (V3)
        fallback = g.transform(lambda x: x.shift(1).rolling(ventana, min_periods=max(2, ventana//2)).median())
        df['clima_semana'] = df['clima_semana'].fillna(fallback)

        # Corrección: ¿las últimas `ventana` semanas corrieron por sobre/bajo su propia norma histórica?
        df['ratio_vs_clima'] = df['n_atenciones'] / (df['clima_semana'] + 1e-6)
        ratio_g = df.groupby('EstablecimientoCodigo')['ratio_vs_clima']
        df['ratio_reciente'] = ratio_g.transform(
            lambda x: x.shift(1).rolling(ventana, min_periods=max(2, ventana//2)).median()
        ).fillna(1.0)

        df['base_movil'] = df['clima_semana'] * df['ratio_reciente']
        df['umbral'] = df['base_movil'] * (1.0 + severidad)
        df['alta_demanda'] = (df['n_atenciones'] > df['umbral']).astype(int)
        df['z_rob_dyn'] = (df['n_atenciones_lag1'] - df['base_movil']) / (df['base_movil'] + 1e-6)

    # 1b. Historial crudo de las últimas `ventana` semanas por centro (para explicar el cálculo
    # de "lo normal" en el hover del dashboard: qué valores exactos entraron a la mediana).
    def _historial_ventana(serie):
        vals = serie.shift(1).tolist()
        out = []
        for i in range(len(vals)):
            inicio = max(0, i - ventana + 1)
            ventana_vals = [v for v in vals[inicio:i + 1] if pd.notna(v)]
            out.append(ventana_vals)
        return pd.Series(out, index=serie.index)

    df['historial'] = df.groupby('EstablecimientoCodigo')['n_atenciones'].transform(_historial_ventana)

    # 2. Rederivar presión de red (depende de alta_demanda y z_rob_dyn)
    df['ad_lag1'] = df.groupby('EstablecimientoCodigo')['alta_demanda'].shift(1)
    
    def _loo_mean(frame, key, val):
        s = frame.groupby([key, 'Anio', 'SemanaEstadistica'])[val].transform('sum')
        n = frame.groupby([key, 'Anio', 'SemanaEstadistica'])[val].transform('count')
        return (s - frame[val]) / (n - 1).replace(0, np.nan)
        
    for key, tag in [('ComunaCodigo', 'com'), ('ServicioSaludCodigo', 'ss')]:
        df[f'{tag}_z']      = _loo_mean(df, key, 'z_rob_dyn')
        df[f'{tag}_adrate'] = _loo_mean(df, key, 'ad_lag1')

    # Limpiar nulos tras derivadas (preservar fila futura T+1)
    mask_future = df['n_atenciones'].isna()
    df_valid = df[~mask_future].dropna(subset=['alta_demanda', 'ad_lag1', 'com_z', 'ss_z', 'z_rob_dyn', 'n_atenciones_lag1'])
    df_future = df[mask_future]
    
    df = pd.concat([df_valid, df_future]).sort_values(['EstablecimientoCodigo', 'Anio', 'SemanaEstadistica'])
    
    cols_to_fill = [c for c in df.columns if c not in ['n_atenciones', 'alta_demanda', 'umbral']]
    df[cols_to_fill] = df[cols_to_fill].fillna(0)
    
    return df

@lru_cache(maxsize=64)
def train_and_evaluate(target_tipo, target_k, target_ventana, feat_clima, feat_red, feat_viral, feat_zrob, severidad=0.0, train_years=(2023, 2024), test_years=(2025, 2026), semanas_estimar=()):
    """
    Entrena el modelo on-demand y devuelve los resultados base (predicciones test).
    Cacheado por los parámetros que implican reentrenamiento.

    `semanas_estimar`: tupla de tuplas (anio, semana) — semanas reales que el usuario decidió
    NO confiar tal cual (ej. detectó rezago de reporte en el sidebar) y quiere que el modelo
    ESTIME en su lugar, igual que la fila T+1 sintética.
    """
    df_raw = load_data()
    if semanas_estimar:
        # df_raw es el objeto cacheado global de load_data(): hay que copiarlo antes de mutar,
        # o se corrompería el caché para el resto de peticiones (incluidas las que no
        # seleccionan ninguna semana a estimar).
        df_raw = df_raw.copy()
        mask = pd.Series(False, index=df_raw.index)
        for anio_w, sem_w in semanas_estimar:
            mask |= (df_raw['Anio'] == anio_w) & (df_raw['SemanaEstadistica'] == sem_w)
        df_raw.loc[mask, 'n_atenciones'] = np.nan

    df = derive_dynamic_target(df_raw, target_tipo, target_k, target_ventana, severidad)
    
    # 1. Definir features activas según ablación
    base_feats = [
        'n_centros_vecinos',
        'n_atenciones_lag1', 'n_atenciones_lag2', 'n_atenciones_lag3',
        'n_0a4_lag1', 'n_65mas_lag1', 'n_5a14_lag1',
        'z_lag1', 'z_lag8', 'ratio_l1_m4', 
        'mom_1_2', 'mom_2_3', 'mom_accel',
        'n_hosp_resp_lag1', 'sem_sin', 'sem_cos'
    ]
    
    dummy_cols = [c for c in df.columns if c.startswith('TipoUrgencia_') or c.startswith('NivelComplejidad_')]
    base_feats += dummy_cols
    
    if feat_viral:
        base_feats += ['pos_vrs_lag1', 'pos_vrs_lag2', 'pos_flu_lag1', 'pos_flu_lag2', 'd_flu', 'd_vrs', 'viral_x_z']
    if feat_zrob:
        base_feats += ['z_rob_dyn']
    if feat_red:
        base_feats += ['com_z', 'com_adrate', 'ss_z', 'ss_adrate']
    if feat_clima:
        base_feats += ['mp25_prom', 'mp25_max', 'n_dias_preemergencia', 'temp_min_prom', 'n_dias_helada', 'precip_acum']
        
    # Asegurar que todas las features existen
    features = [f for f in base_feats if f in df.columns]
    
    # 2. Split temporal estricto dinámico
    is_future = df['n_atenciones'].isna()
    train_mask = df['Anio'].isin(train_years) & ~is_future
    test_mask = df['Anio'].isin(test_years) & ~is_future
    
    X_train, y_train = df.loc[train_mask, features], df.loc[train_mask, 'alta_demanda']
    X_test, y_test = df.loc[test_mask, features], df.loc[test_mask, 'alta_demanda']
    X_future = df.loc[is_future, features]
    
    # 3. Entrenar
    try:
        model = xgb.XGBClassifier(
            n_estimators=150,
            max_depth=2,
            learning_rate=0.1,
            random_state=42,
            eval_metric='logloss',
            use_label_encoder=False,
            tree_method='hist',
            device='cuda'
        )
        model.fit(X_train, y_train)
    except Exception as e:
        print("Fallback a CPU: GPU no disponible o error al usar CUDA en XGBoost.")
        model = xgb.XGBClassifier(
            n_estimators=150,
            max_depth=2,
            learning_rate=0.1,
            random_state=42,
            eval_metric='logloss',
            use_label_encoder=False
        )
        model.fit(X_train, y_train)
    
    # 4. Calibrar umbral en train para target recall (ej 0.885)
    train_probs = model.predict_proba(X_train)[:, 1]
    prec_t, rec_t, th_t = precision_recall_curve(y_train, train_probs)
    # Buscar el umbral que da el recall más cercano al 88.5% (o equivalente) para mantener el 83% en test
    target_train_recall = 0.885
    idx = np.abs(rec_t - target_train_recall).argmin()
    opt_th = th_t[idx] if idx < len(th_t) else 0.5
    
    # 5. Predecir en test y en el futuro
    test_probs = model.predict_proba(X_test)[:, 1] if len(X_test) > 0 else np.array([])
    future_probs = model.predict_proba(X_future)[:, 1] if len(X_future) > 0 else np.array([])
    
    # SHAP (explainer global en test para rapidez, tomamos una muestra para no colapsar)
    explainer = shap.TreeExplainer(model)
    if len(X_test) > 0:
        shap_vals = explainer.shap_values(X_test.sample(min(1000, len(X_test)), random_state=42))
    else:
        shap_vals = explainer.shap_values(X_train.sample(min(1000, len(X_train)), random_state=42))
    mean_abs_shap = np.abs(shap_vals).mean(axis=0)
    top_idx = np.argsort(mean_abs_shap)[::-1][:8]
    shap_top = {
        "labels": [features[i] for i in top_idx],
        "values": [float(mean_abs_shap[i]) for i in top_idx]
    }
    
    # Armar dataframe de resultados de test
    df_test = df.loc[test_mask].copy()
    df_test['prob'] = test_probs
    
    # Empaquetar predicciones futuras
    df_future = df.loc[is_future].copy()
    df_future['prob'] = future_probs
    
    return {
        'df_test': df_test,
        'df_future': df_future,
        'y_test': y_test.values if len(y_test) > 0 else [],
        'probs': test_probs,
        'opt_th': float(opt_th),
        'shap_top': shap_top
    }

def get_dashboard_state(target, features_config, filtro, recall_objetivo, train_years=[2023, 2024, 2025], test_years=[2026], semanas_estimar=None):
    """
    Genera el JSON final para el frontend.

    `semanas_estimar`: lista de dicts [{"anio":2026,"semana":28}, ...] — semanas reales que
    el usuario marcó (desde el sidebar) como "no confiar, estimar con el modelo".
    """
    sev = float(target.get('severidad', 0.0))
    # Tupla de tuplas: hashable, requerido por el @lru_cache de train_and_evaluate.
    semanas_tup = tuple(sorted((int(s['anio']), int(s['semana'])) for s in (semanas_estimar or [])))
    res = train_and_evaluate(
        target['tipo'], target['k'], target['ventana'],
        features_config['clima'], features_config['red'],
        features_config['viral'], features_config['z_rob8'], sev,
        tuple(train_years), tuple(test_years), semanas_tup
    )
    
    df_test = res['df_test'].copy()
    
    # 1. Aplicar filtros (segmentación post-hoc)
    if filtro.get('comuna'):
        df_test = df_test[df_test['ComunaCodigo'] == filtro['comuna']]
    if filtro.get('centro'):
        df_test = df_test[df_test['EstablecimientoCodigo'] == filtro['centro']]
    
    y_test = df_test['alta_demanda'].values
    probs = df_test['prob'].values
    
    # 2. Calcular KPIs con recall objetivo
    if len(y_test) == 0:
        return {"error": "Filtro vacío"}
        
    prec, rec, th = precision_recall_curve(y_test, probs)
    pr_auc = auc(rec, prec)
    
    # Buscar el umbral óptimo de CLIENTE según recall_objetivo
    # Si el cliente no mandó recall_objetivo (o no lo cambiamos), usamos el calibrado en train
    # Pero el frontend permite mover el dial de recall
    target_rec = recall_objetivo / 100.0
    idx = np.abs(rec - target_rec).argmin()
    use_th = th[idx] if idx < len(th) else 0.5
    
    preds = (probs >= use_th).astype(int)
    cm = confusion_matrix(y_test, preds, labels=[0, 1])
    
    if cm.shape == (2,2):
        TN, FP, FN, TP = cm.ravel()
    else:
        TN, FP, FN, TP = len(y_test), 0, 0, 0 # dummy fall-back
        
    # Curva general (subsampleada para no enviar miles de puntos)
    curva_p = prec[::max(1, len(prec)//100)].tolist()
    curva_r = rec[::max(1, len(rec)//100)].tolist()
    
    # Agrupaciones para gráficos
    # Alertas semana
    alertas = df_test.groupby(['Anio', 'SemanaEstadistica']).agg(
        real=('alta_demanda', 'sum'),
        pred=('prob', lambda x: (x >= use_th).sum())
    ).reset_index()
    alertas['label'] = alertas.apply(lambda row: f"{int(row['Anio'])}-W{int(row['SemanaEstadistica']):02d}", axis=1)
    
    # Volúmenes (usamos un regresor simple ingenuo para volumen, ya que el dashboard de la v8 enfoca en alertas)
    vol_tot = df_test.groupby(['Anio', 'SemanaEstadistica']).agg(
        real=('n_atenciones', 'sum'),
        pred=('n_atenciones_lag1', 'sum'),
        umbral=('umbral', 'sum')
    ).reset_index()
    
    # Marcadores en el tiempo (agrupados si no hay filtro, unitarios si hay filtro)
    # TP y FP se grafican sobre el umbral; FN se grafica sobre el real
    tp_series = []
    fp_series = []
    fn_series = []
    tp_series_alerta = []
    fp_series_alerta = []
    fn_series_alerta = []
    tp_centers = []
    fp_centers = []
    fn_centers = []
    detalle_centros = []  # por semana: {codigo: {real, normal, margen, umbral, prob, alerta, resultado}}

    df_test['pred_alerta'] = preds

    for i, row in df_test.groupby(['Anio', 'SemanaEstadistica']):
        mask_tp = (row['alta_demanda'] == 1) & (row['pred_alerta'] == 1)
        mask_fp = (row['alta_demanda'] == 0) & (row['pred_alerta'] == 1)
        mask_fn = (row['alta_demanda'] == 1) & (row['pred_alerta'] == 0)

        has_tp = mask_tp.any()
        has_fp = mask_fp.any()
        has_fn = mask_fn.any()

        sum_umbral = row['umbral'].sum()
        sum_real = row['n_atenciones'].sum()

        tp_series.append(float(sum_umbral) if has_tp else None)
        fp_series.append(float(sum_umbral) if has_fp else None)
        fn_series.append(float(sum_real) if has_fn else None)

        sum_alerta_real = int(mask_tp.sum() + mask_fn.sum())
        sum_alerta_pred = int(mask_tp.sum() + mask_fp.sum())

        tp_series_alerta.append(float(mask_tp.sum()) if has_tp else None)
        fp_series_alerta.append(float(mask_fp.sum()) if has_fp else None)
        fn_series_alerta.append(float(mask_fn.sum()) if has_fn else None)

        tp_centers.append(row[mask_tp]['EstablecimientoCodigo'].astype(str).tolist())
        fp_centers.append(row[mask_fp]['EstablecimientoCodigo'].astype(str).tolist())
        fn_centers.append(row[mask_fn]['EstablecimientoCodigo'].astype(str).tolist())

        # Detalle numérico por centro implicado (para el hover "¿por qué se definió así su umbral?")
        detalle_semana = {}
        mask_implicado = mask_tp | mask_fp | mask_fn
        for idx_r, r in row[mask_implicado].iterrows():
            if mask_tp.loc[idx_r]:
                resultado = 'acierto'
            elif mask_fp.loc[idx_r]:
                resultado = 'falsa_alarma'
            else:
                resultado = 'no_detectado'
            detalle_semana[str(r['EstablecimientoCodigo'])] = {
                "real": float(r['n_atenciones']),
                "normal": float(r['base_movil']),
                "margen": float(r['umbral'] - r['base_movil']),
                "umbral": float(r['umbral']),
                "prob": float(r['prob']),
                "alerta": bool(r['pred_alerta']),
                "resultado": resultado,
                "historial": [float(v) for v in r['historial']]
            }
        detalle_centros.append(detalle_semana)
    
    # Por centro
    por_centro = []
    if not filtro.get('centro'): # Solo si no está filtrado ya por centro (para no duplicar logica)
        # Tomar los top centros
        top_c = df_test.groupby('EstablecimientoCodigo')['alta_demanda'].sum().sort_values(ascending=False).head(5)
        for c_code in top_c.index:
            df_c = df_test[df_test['EstablecimientoCodigo'] == c_code].copy()
            por_centro.append({
                "centro": c_code,
                "real": int(df_c['n_atenciones'].sum()),
                "umbral": float(df_c['umbral'].mean()),
                "prob": float(df_c['prob'].mean()),
                "alerta_real": int(df_c['alta_demanda'].sum()),
                "alerta_modelo": int((df_c['prob'] >= use_th).sum())
            })
            
    corr = alertas['real'].corr(alertas['pred'])
    if pd.isna(corr):
        corr = None
    else:
        corr = float(corr)

    # ---- Semáforo de fiabilidad: FIRME (precisión >=0.75) vs VIGILAR (punto del dial) ----
    def _tier_stats(mask):
        tp = int(((y_test == 1) & (mask == 1)).sum()); fp = int(((y_test == 0) & (mask == 1)).sum())
        fn = int(((y_test == 1) & (mask == 0)).sum())
        return {"recall": (tp / (tp + fn)) if (tp + fn) else 0.0,
                "precision": (tp / (tp + fp)) if (tp + fp) else 0.0,
                "alertas": tp + fp, "detectados": tp}
    ok_f = np.where(prec[:-1] >= 0.75)[0]
    th_firme = float(th[ok_f[0]]) if len(ok_f) else (float(th[-1]) if len(th) else 1.0)
    firme = _tier_stats((probs >= th_firme).astype(int)); firme["umbral"] = th_firme
    vigilar = _tier_stats(preds); vigilar["umbral"] = float(use_th)
    semaforo = {"firme": firme, "vigilar": vigilar}

    # df_future agrupa TANTO la fila T+1 (siempre presente, pronóstico genuino) COMO,
    # si estimar_semanas_incompletas está activo, las últimas semanas reales enmascaradas
    # por rezago de reporte (ver train_and_evaluate). Se distingue cada semana por tipo
    # comparándola contra el máximo real verdadero (sin enmascarar) de load_data().
    df_future = res['df_future'].copy()
    df_base_real = load_data()
    real_rows = df_base_real[df_base_real['n_atenciones'].notna()]
    true_max_anio = int(real_rows['Anio'].max())
    true_max_sem = int(real_rows.loc[real_rows['Anio'] == true_max_anio, 'SemanaEstadistica'].max())
    true_next_anio, true_next_sem = _next_semana(true_max_anio, true_max_sem)

    pronostico_futuro = []
    if len(df_future) > 0:
        for (anio_g, sem_g), grupo in df_future.groupby(['Anio', 'SemanaEstadistica']):
            alertas_g = sorted(
                [{"centro": str(r['EstablecimientoCodigo']), "prob": float(r['prob'])}
                 for _, r in grupo.iterrows() if r['prob'] >= use_th],
                key=lambda x: x['prob'], reverse=True
            )
            tipo = 'pronostico' if (int(anio_g) == true_next_anio and int(sem_g) == true_next_sem) else 'estimado_retroactivo'
            pronostico_futuro.append({
                "anio": int(anio_g),
                "semana": int(sem_g),
                "tipo": tipo,
                "alertas": alertas_g
            })
        pronostico_futuro.sort(key=lambda w: (w['anio'], w['semana']))

    return {
        "pronostico_futuro": pronostico_futuro,
        "prevalencia": float(np.mean(y_test)) if len(y_test) > 0 else 0.0,
        "kpis": {
            "recall": float(TP / (TP + FN)) if (TP+FN)>0 else 0,
            "precision": float(TP / (TP + FP)) if (TP+FP)>0 else 0,
            "f1": float(f1_score(y_test, preds)),
            "pr_auc": float(pr_auc),
            "TP": int(TP),
            "FP": int(FP),
            "FN": int(FN),
            "TN": int(TN),
            "accuracy": float((TP+TN)/len(y_test))
        },
        "curva": {
            "recall": curva_r,
            "precision": curva_p,
            "npos": int(sum(y_test)),
            "nneg": int(len(y_test) - sum(y_test))
        },
        "alertas_semana": {
            "labels": alertas['label'].tolist(),
            "real": alertas['real'].tolist(),
            "pred": alertas['pred'].tolist(),
            "tp": tp_series_alerta,
            "fp": fp_series_alerta,
            "fn": fn_series_alerta,
            "corr": corr
        },
        "volume": {
            "labels": alertas['label'].tolist(),
            "real": vol_tot['real'].tolist(),
            "pred": vol_tot['pred'].tolist(),
            "umbral": vol_tot['umbral'].tolist(),
            "tp": tp_series,
            "fp": fp_series,
            "fn": fn_series,
            "tp_centers": tp_centers,
            "fp_centers": fp_centers,
            "fn_centers": fn_centers,
            "detalle": detalle_centros
        },
        "shap_top": res['shap_top'],
        "tabla": por_centro,
        "semaforo": semaforo,
        "severidad": sev,
        "ventana": target['ventana'],
        "umbral_prob": float(use_th),
        "n_test": len(df_test)
    }

def _cobertura_reciente(df, n_semanas=3):
    """
    Diagnóstico de rezago de reporte: para cada una de las últimas `n_semanas` semanas ISO
    reales (excluye la fila sintética T+1), compara el volumen reportado contra la
    climatología de esa misma semana ISO en años estrictamente anteriores. Un valor muy por
    debajo de lo normal casi siempre es rezago de reporte de los centros al DEIS, no una
    caída real de demanda (confirmado empíricamente: semana 2026-W28 llegó a ~18% de su
    volumen habitual). No depende de filtros ni de reentrenar el modelo — se calcula una
    sola vez junto con /api/meta.
    """
    real_df = df[df['n_atenciones'].notna()]
    semanas = (real_df[['Anio', 'SemanaEstadistica']]
               .drop_duplicates()
               .sort_values(['Anio', 'SemanaEstadistica'], ascending=False)
               .head(n_semanas))

    tot_por_semana = real_df.groupby(['Anio', 'SemanaEstadistica'])['n_atenciones'].sum()

    out = []
    for _, w in semanas.iterrows():
        anio, sem = int(w['Anio']), int(w['SemanaEstadistica'])
        real_total = float(tot_por_semana.get((anio, sem), 0.0))

        # Climatología: misma semana ISO en años ESTRICTAMENTE anteriores.
        prior = tot_por_semana[
            (tot_por_semana.index.get_level_values('SemanaEstadistica') == sem) &
            (tot_por_semana.index.get_level_values('Anio') < anio)
        ]
        normal = float(prior.median()) if len(prior) > 0 else None

        if normal is None or normal <= 0:
            ratio_pct, estado = None, "sin_referencia"
        else:
            ratio_pct = round(real_total / normal * 100, 1)
            estado = "ok" if ratio_pct >= 90 else ("precaucion" if ratio_pct >= 60 else "alerta")

        out.append({
            "anio": anio,
            "semana": sem,
            "real": int(round(real_total)),
            "normal_estimado": int(round(normal)) if normal is not None else None,
            "ratio_pct": ratio_pct,
            "estado": estado
        })
    # Orden cronológico ascendente para mostrar en el sidebar (más antigua primero).
    out.sort(key=lambda w: (w['anio'], w['semana']))
    return out


def get_meta():
    df = load_data()
    try:
        import json
        with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
    except:
        mapping = {}
        
    try:
        import json
        with open(GRID_PATH, 'r', encoding='utf-8') as f:
            grid_res = json.load(f)
    except:
        grid_res = None
    
    centros_list = []
    df_coords = df[['EstablecimientoCodigo', 'Latitud', 'Longitud']].drop_duplicates('EstablecimientoCodigo')
    coords_dict = df_coords.set_index('EstablecimientoCodigo').to_dict('index')

    for k in df['EstablecimientoCodigo'].unique():
        code = str(k)
        name = mapping.get(code, code)
        lat = coords_dict.get(k, {}).get('Latitud')
        lon = coords_dict.get(k, {}).get('Longitud')
        centros_list.append({
            "code": code, 
            "name": f"{code} - {name}",
            "lat": float(lat) if not pd.isna(lat) else None,
            "lon": float(lon) if not pd.isna(lon) else None
        })
        
    # Default OPERATIVO (V2).
    # El grid (mejor/peor combo) se sigue exponiendo en la clave "grid" para el banner.
    defaults = MODELO_DEFAULTS

    return {
        "comunas": sorted(df['ComunaCodigo'].dropna().unique().tolist()),
        "centros": centros_list,
        "grid": grid_res,
        "defaults": defaults,
        "cobertura_reciente": _cobertura_reciente(df)
    }


def get_last_update_date():
    df = pd.read_parquet(DATA_PATH)
    # Descarta semanas futuras o border-weeks incompletas (p.ej. artefacto W53) que puedan
    # colarse en el parquet, para no reportar como "última actualización" una fecha fantasma.
    cy, cw, _ = pd.Timestamp.today().isocalendar()
    df = df[~((df['Anio'] > cy) | ((df['Anio'] == cy) & (df['SemanaEstadistica'] >= cw)))]
    max_anio = df['Anio'].max()
    max_semana = df[df['Anio'] == max_anio]['SemanaEstadistica'].max()
    # mtime del propio archivo: cuándo se generó de verdad, sea por el botón del dashboard
    # o por el pipeline automatizado — no depende de que alguien haya apretado un botón.
    archivo_actualizado = datetime.datetime.fromtimestamp(os.path.getmtime(DATA_PATH)).isoformat()
    return {'anio': int(max_anio), 'semana': int(max_semana), 'archivo_actualizado': archivo_actualizado}


def reset_cache():
    """
    Invalida el caché global tras un refresco exitoso de panel.parquet (botón de
    actualización de datos): load_data() devuelve el mismo df en memoria hasta que se
    reinicia el proceso, y train_and_evaluate() está memoizado por parámetros — ambos
    deben limpiarse o el dashboard seguiría sirviendo el dato viejo pese al archivo nuevo.
    """
    global df_base_cache
    df_base_cache = None
    train_and_evaluate.cache_clear()


def get_resumen_datos():
    """
    Resumen del dataset cargado (para responder preguntas como '¿qué datos tienes?').
    Reutiliza get_meta()/get_last_update_date() en vez de recorrer el parquet de nuevo.
    """
    meta = get_meta()
    upd = get_last_update_date()
    df = load_data()
    real = df[df['n_atenciones'].notna()]
    return {
        "n_centros": len(meta["centros"]),
        "n_comunas": len(meta["comunas"]),
        "comunas": [COMUNA_NAMES.get(int(c), str(c)) for c in meta["comunas"]],
        "periodo": {
            "anio_inicio": int(real['Anio'].min()),
            "anio_fin": int(real['Anio'].max()),
        },
        "total_atenciones_historicas": int(real['n_atenciones'].sum()),
        "ultima_semana_reportada": {"anio": upd["anio"], "semana": upd["semana"]},
        "archivo_actualizado": upd["archivo_actualizado"],
        "cobertura_reciente": meta["cobertura_reciente"],
    }


MESES_ES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12
}


def _resolver_mes(mes):
    """Acepta nombre en español ('junio') o número (6, '6') y devuelve 1-12, o None si no aplica."""
    if mes is None:
        return None
    clave = str(mes).strip().lower()
    if clave in MESES_ES:
        return MESES_ES[clave]
    try:
        n = int(clave)
        return n if 1 <= n <= 12 else None
    except ValueError:
        return None


def get_top_centros_atenciones(top_n=3, mes=None, anio=None):
    """
    Centros con mayor volumen real de atenciones respiratorias (suma de n_atenciones).
    Sin filtros, suma todo el histórico 2023-2026. `mes` (nombre o número) y `anio` acotan
    el período — el mes se deriva del lunes de cada semana ISO (mismo criterio que
    format_week_date en serve.py), ya que el panel no trae una fecha exacta por fila.
    """
    df = load_data()
    real = df[df['n_atenciones'].notna()].copy()

    mes_num = _resolver_mes(mes)
    if mes_num is not None:
        lunes = pd.to_datetime(
            real['Anio'].astype(int).astype(str) + '-W' +
            real['SemanaEstadistica'].astype(int).astype(str).str.zfill(2) + '-1',
            format='%G-W%V-%u'
        )
        real = real[lunes.dt.month == mes_num]

    if anio is not None:
        try:
            real = real[real['Anio'] == int(anio)]
        except (TypeError, ValueError):
            pass

    try:
        with open(MAPPING_PATH, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
    except Exception:
        mapping = {}

    if real.empty:
        return []

    top = (real.groupby('EstablecimientoCodigo')['n_atenciones']
           .sum().sort_values(ascending=False).head(top_n))

    return [
        {
            "codigo": str(codigo),
            "nombre": mapping.get(str(codigo), str(codigo)),
            "total_atenciones": int(total)
        }
        for codigo, total in top.items()
    ]


def _dashboard_state_default():
    """
    Corre get_dashboard_state() con la misma config operativa por defecto del panel
    (MODELO_DEFAULTS, sin filtro, período de prueba 2026) — la que usan el banner de
    pronóstico y las gráficas de distribución. train_and_evaluate() está cacheado por
    parámetros, así que llamarla varias veces con estos mismos argumentos es barato tras la
    primera vez.
    """
    return get_dashboard_state(
        {"tipo": MODELO_DEFAULTS["tipo"], "k": MODELO_DEFAULTS["k"],
         "ventana": MODELO_DEFAULTS["ventana"], "severidad": MODELO_DEFAULTS["severidad"]},
        MODELO_DEFAULTS["features"],
        {"comuna": None, "centro": None},
        83.0,
        [2023, 2024, 2025],
        [2026],
        None
    )


def get_top_comunas_riesgo(top_n=3):
    """
    Comunas con mayor riesgo de colapso según el pronóstico T+1 vigente (misma config por
    defecto que el banner del dashboard: MODELO_DEFAULTS). Rankea por cantidad de centros en
    alerta y, en empate, por la probabilidad máxima entre ellos.
    """
    res = _dashboard_state_default()
    pronostico = next((w for w in res.get("pronostico_futuro", []) if w["tipo"] == "pronostico"), None)
    if not pronostico or not pronostico["alertas"]:
        return []

    df = load_data()
    centro_comuna = df[['EstablecimientoCodigo', 'ComunaCodigo']].drop_duplicates('EstablecimientoCodigo')
    centro_comuna = {str(k): v for k, v in centro_comuna.set_index('EstablecimientoCodigo')['ComunaCodigo'].items()}

    por_comuna = {}
    for alerta in pronostico["alertas"]:
        comuna_cod = centro_comuna.get(str(alerta["centro"]))
        if comuna_cod is None:
            continue
        entry = por_comuna.setdefault(comuna_cod, {"n_centros_alerta": 0, "prob_max": 0.0})
        entry["n_centros_alerta"] += 1
        entry["prob_max"] = max(entry["prob_max"], alerta["prob"])

    ranking = sorted(por_comuna.items(), key=lambda kv: (kv[1]["n_centros_alerta"], kv[1]["prob_max"]), reverse=True)

    return [
        {
            "comuna": COMUNA_NAMES.get(int(cod), str(cod)),
            "centros_en_alerta": datos["n_centros_alerta"],
            "probabilidad_maxima": round(datos["prob_max"], 3)
        }
        for cod, datos in ranking[:top_n]
    ]


MESES_ES_LISTA = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
                   "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def get_colapsos_por_periodo():
    """
    Distribución de colapsos REALES (aciertos + no detectados, TP+FN — no incluye falsas
    alarmas) agrupada por estación del año y por mes. Replica exactamente el cálculo de
    updateDistributionCharts() en index.html (mismos rangos de semana ISO para estación,
    mismo criterio TP+FN), para que el chat responda lo mismo que muestran las donas
    "Colapsos por Estación" / "Colapsos por Mes" del panel. Cubre el período de prueba del
    modelo (2026) bajo la config operativa por defecto — no todo el histórico 2023-2026.
    """
    res = _dashboard_state_default()
    vol = res.get("volume", {})
    labels = vol.get("labels", [])
    tp_centers = vol.get("tp_centers", [])
    fn_centers = vol.get("fn_centers", [])

    estacion_counts = {"Otoño": 0, "Invierno": 0, "Primavera": 0, "Verano": 0}
    mes_counts = {m: 0 for m in MESES_ES_LISTA}

    for i, label in enumerate(labels):
        try:
            anio_s, sem_s = label.split("-W")
            anio, sem = int(anio_s), int(sem_s)
        except ValueError:
            continue

        n_tp = len(tp_centers[i]) if i < len(tp_centers) and tp_centers[i] else 0
        n_fn = len(fn_centers[i]) if i < len(fn_centers) and fn_centers[i] else 0
        colapsos = n_tp + n_fn
        if colapsos == 0:
            continue

        if 12 <= sem <= 24:
            estacion = "Otoño"
        elif 25 <= sem <= 37:
            estacion = "Invierno"
        elif 38 <= sem <= 50:
            estacion = "Primavera"
        else:
            estacion = "Verano"
        estacion_counts[estacion] += colapsos

        try:
            # Mismo ancla que updateDistributionCharts() en index.html: new Date(year, 0, 4 +
            # (w-1)*7) — NO es el lunes ISO real de la semana (fromisocalendar da resultados
            # distintos, verificado). Hay que igualar esta fórmula, no "corregirla", o el chat
            # contradice el mes que muestra la dona en pantalla para la misma semana.
            fecha_ancla = datetime.date(anio, 1, 4) + datetime.timedelta(days=(sem - 1) * 7)
            mes_counts[MESES_ES_LISTA[fecha_ancla.month - 1]] += colapsos
        except Exception:
            pass

    return {
        "total_colapsos_reales": sum(estacion_counts.values()),
        "por_estacion": estacion_counts,
        "por_mes": {k: v for k, v in mes_counts.items() if v > 0},
        "periodo_evaluado": "2026 (período de prueba del modelo)",
        "definicion": "Colapso real = alerta correcta (acierto) + colapso no detectado, sobre la config operativa por defecto del panel. No incluye falsas alarmas."
    }
