import os
import pandas as pd

def main():
    print("Construyendo panel.parquet...")
    
    os.makedirs("data", exist_ok=True)
    os.makedirs("static", exist_ok=True)

    base_dir = "../dataset_salud"
    
    # 1. Cargar datos base
    df_base = pd.read_parquet(os.path.join(base_dir, "urg_resp_centro_semana.parquet"))
    
    # 2. Cargar datos ambientales (comuna)
    # Algunas comunas pueden no tener datos, se usa merge left y se rellenan NAs si es necesario
    df_amb = pd.read_parquet(os.path.join(base_dir, "ambiente_comuna_semana.parquet"))
    df_amb["ComunaCodigo"] = df_amb["ComunaCodigo"].astype(str)
    
    # 3. Cargar datos climáticos (RM, aplica a todas las comunas)
    df_cli = pd.read_parquet(os.path.join(base_dir, "clima_dmc_semana.parquet"))
    
    # 4. Merge
    df_base["ComunaCodigo"] = df_base["ComunaCodigo"].astype(str)
    df = df_base.merge(df_amb, on=["ComunaCodigo", "Anio", "SemanaEstadistica"], how="left")
    df = df.merge(df_cli, on=["Anio", "SemanaEstadistica"], how="left")
    
    # Rellenar valores nulos climáticos/ambientales con 0 o bfill/ffill según corresponda
    # Por ahora llenamos con 0 o la media para simplificar, como en el notebook
    cols_clima = ['mp25_prom', 'mp25_max', 'n_dias_preemergencia', 'temp_min_prom', 'n_dias_helada', 'precip_acum']
    df[cols_clima] = df[cols_clima].fillna(0)
    
    # Ordenar
    df = df.sort_values(["EstablecimientoCodigo", "Anio", "SemanaEstadistica"]).reset_index(drop=True)
    
    # Guardar version "slim" (todas estas columnas son necesarias)
    out_path = os.path.join("data", "panel.parquet")
    df.to_parquet(out_path, index=False)
    print(f"Guardado {out_path} - Filas: {len(df)}, Columnas: {len(df.columns)}")

if __name__ == "__main__":
    main()
