import os
import itertools
import numpy as np
from sklearn.metrics import precision_recall_curve, auc
import xgboost as xgb
from modelo import load_data, derive_dynamic_target

def run_search():
    df_raw = load_data()
    
    tipos = ['nivel', 'sobre_tendencia', 'salto_wow', 'aumento_estandar', 'aumento_reciente', 'estacional']
    ventanas = [4, 8, 12]
    ks = [1.0, 1.5, 2.0]
    severidades = [0.0, 0.15, 0.20]
    
    bools = [False, True]
    
    all_results = []
    
    # Pre-cache derived targets to avoid recomputing for the same (tipo, k, ventana, severidad) over and over
    cache_targets = {}
    
    combinations = list(itertools.product(tipos, ventanas, ks, severidades, bools, bools, bools, bools))
    
    total = len(combinations)
    print(f"Total combinaciones a evaluar: {total}")
    
    for idx, (tipo, ventana, k, severidad, clima, red, viral, zrob) in enumerate(combinations):
        if (idx+1) % 50 == 0:
            print(f"Progreso: {idx+1}/{total}")
            
        tkvs = (tipo, ventana, k, severidad)
        if tkvs not in cache_targets:
            cache_targets[tkvs] = derive_dynamic_target(df_raw, tipo, k, ventana, severidad)
        df = cache_targets[tkvs]
        
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
        
        if viral:
            base_feats += ['pos_vrs_lag1', 'pos_vrs_lag2', 'pos_flu_lag1', 'pos_flu_lag2', 'd_flu', 'd_vrs', 'viral_x_z']
        if zrob:
            base_feats += ['z_rob_dyn']
        if red:
            base_feats += ['com_z', 'com_adrate', 'ss_z', 'ss_adrate']
        if clima:
            base_feats += ['mp25_prom', 'mp25_max', 'n_dias_preemergencia', 'temp_min_prom', 'n_dias_helada', 'precip_acum']
            
        features = [f for f in base_feats if f in df.columns]
        
        train_mask = df['Anio'].isin([2023, 2024])
        test_mask = df['Anio'].isin([2025, 2026])
        
        X_train, y_train = df.loc[train_mask, features], df.loc[train_mask, 'alta_demanda']
        X_test, y_test = df.loc[test_mask, features], df.loc[test_mask, 'alta_demanda']
        
        if len(y_train) == 0 or len(y_test) == 0 or sum(y_test) == 0:
            continue
            
        model = xgb.XGBClassifier(
            n_estimators=150, max_depth=2, learning_rate=0.1,
            random_state=42, eval_metric='logloss', use_label_encoder=False,
            n_jobs=4
        )
        model.fit(X_train, y_train)
        
        test_probs = model.predict_proba(X_test)[:, 1]
        prec, rec, _ = precision_recall_curve(y_test, test_probs)
        pr_auc = auc(rec, prec)
        
        preds = (test_probs >= 0.5).astype(int)
        tp = sum((y_test == 1) & (preds == 1))
        fp = sum((y_test == 0) & (preds == 1))
        fn = sum((y_test == 1) & (preds == 0))
        
        curr_recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        curr_precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        
        conf = {
            'tipo': tipo, 'ventana': ventana, 'k': k, 'severidad': severidad,
            'clima': clima, 'red': red, 'viral': viral, 'zrob': zrob
        }
        
        all_results.append({
            'conf': conf,
            'pr_auc': float(pr_auc),
            'recall': float(curr_recall),
            'precision': float(curr_precision)
        })
        
    best_auc = -1
    best_conf = None
    worst_auc = 2
    worst_conf = None

    for item in all_results:
        if item['pr_auc'] > best_auc:
            best_auc = item['pr_auc']
            best_conf = item['conf']
        if item['pr_auc'] < worst_auc:
            worst_auc = item['pr_auc']
            worst_conf = item['conf']
            
    import json
    res = {
        'best': {'conf': best_conf, 'pr_auc': best_auc},
        'worst': {'conf': worst_conf, 'pr_auc': worst_auc},
        'all': all_results
    }
    
    with open('c:/Proyectos/Diplomado-ML V2/app_dashboard/data/grid_results.json', 'w') as f:
        json.dump(res, f)
    print("Done! Best AUC:", best_auc, "Worst AUC:", worst_auc)

if __name__ == "__main__":
    run_search()
