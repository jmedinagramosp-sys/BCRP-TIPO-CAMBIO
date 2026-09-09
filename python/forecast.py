"""
forecast.py
-----------
Genera una proyeccion simple de tendencia del tipo de cambio
(venta) a partir del historico acumulado en la base de datos
local, y exporta un CSV listo para conectar en Power BI.

IMPORTANTE (honestidad tecnica):
Este es un modelo de regresion lineal simple sobre pocos dias
de historia. NO es un modelo financiero serio ni debe usarse
para decisiones de inversion o cambio de moneda reales. Su
valor aqui es demostrar el flujo completo de un pipeline de
datos con un componente predictivo, no la precision del
pronostico en si.

Uso:
    python forecast.py --dias-adelante 7
"""

import argparse
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "tipo_cambio.db"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "data" / "proyeccion.csv"


def cargar_historico() -> pd.DataFrame:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No existe {DB_PATH}. Corre primero extract_load.py para poblar la base."
        )
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql("SELECT fecha, venta FROM tipo_cambio ORDER BY fecha", conn)
    conn.close()
    df["fecha"] = pd.to_datetime(df["fecha"])
    return df


def entrenar_y_proyectar(df: pd.DataFrame, dias_adelante: int) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    df["dia_ordinal"] = np.arange(len(df))

    X = df[["dia_ordinal"]]
    y = df["venta"]

    modelo = LinearRegression()
    modelo.fit(X, y)
    pred_historica = modelo.predict(X)
    mae = mean_absolute_error(y, pred_historica)
    print(f"MAE del ajuste sobre el historico: {mae:.4f} soles")
    print("(referencia de que tan bien la linea de tendencia sigue los datos reales)")

    ultimo_ordinal = df["dia_ordinal"].max()
    futuros_ordinales = np.arange(ultimo_ordinal + 1, ultimo_ordinal + 1 + dias_adelante)
    futuras_fechas = pd.date_range(
        start=df["fecha"].max() + pd.Timedelta(days=1), periods=dias_adelante
    )
    pred_futura = modelo.predict(pd.DataFrame({"dia_ordinal": futuros_ordinales}))

    historico = df[["fecha", "venta"]].copy()
    historico["tipo"] = "real"
    historico = historico.rename(columns={"venta": "valor"})

    proyeccion = pd.DataFrame({
        "fecha": futuras_fechas,
        "valor": pred_futura,
        "tipo": "proyeccion",
    })

    return pd.concat([historico, proyeccion], ignore_index=True)


def main():
    parser = argparse.ArgumentParser(description="Proyecta tendencia del tipo de cambio")
    parser.add_argument("--dias-adelante", type=int, default=7)
    args = parser.parse_args()

    df = cargar_historico()
    if len(df) < 10:
        print(f"Aviso: solo hay {len(df)} registros historicos. "
              "La proyeccion sera poco confiable con tan pocos datos.")

    resultado = entrenar_y_proyectar(df, args.dias_adelante)
    resultado.to_csv(OUTPUT_PATH, index=False)
    print(f"\nArchivo generado: {OUTPUT_PATH}")
    print("Conecta este CSV en Power BI (Obtener datos > Texto/CSV) para el visual de tendencia.")


if __name__ == "__main__":
    main()
