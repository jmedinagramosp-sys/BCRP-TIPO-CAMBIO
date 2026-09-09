"""
extract_load.py
----------------
Pipeline de extraccion y carga (E+L) del tipo de cambio USD/PEN
publicado por el Banco Central de Reserva del Peru (BCRP).

Fuente: API publica de BCRPData (no requiere API key).
Series:
    PD04637PD -> Tipo de cambio interbancario, compra
    PD04638PD -> Tipo de cambio interbancario, venta

Cada ejecucion consulta el rango de fechas indicado y hace un
"upsert": si la fecha ya existe en la base, la actualiza; si no
existe, la inserta. Esto permite correr el script todos los dias
(por ejemplo via cron o el Programador de tareas de Windows) sin
duplicar datos.

Uso:
    python extract_load.py --dias 30
    python extract_load.py --desde 2024-01-01 --hasta 2024-12-31
"""

import argparse
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

BASE_URL = "https://estadisticas.bcrp.gob.pe/estadisticas/series/api"
SERIE_COMPRA = "PD04637PD"
SERIE_VENTA = "PD04638PD"
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "tipo_cambio.db"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
MAX_REINTENTOS = 3
ESPERA_ENTRE_REINTENTOS = 5  # segundos

MESES_ES = {
    "Ene": "01", "Feb": "02", "Mar": "03", "Abr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Ago": "08",
    "Set": "09", "Oct": "10", "Nov": "11", "Dic": "12",
}


def formatear_periodo(d: date) -> str:
    """La API del BCRP espera fechas SIN ceros a la izquierda (ej. 2025-1-5)."""
    return f"{d.year}-{d.month}-{d.day}"


def parsear_fecha_bcrp(periodo: str) -> str:
    """Convierte 'DD.Mes.YY' (formato real del JSON del BCRP, ej. '01.Ene.25') a 'YYYY-MM-DD'."""
    dia, mes_es, anio = periodo.split(".")
    mes = MESES_ES[mes_es]
    return f"20{anio}-{mes}-{dia}"


def obtener_serie(codigo: str, desde: str, hasta: str) -> dict[str, float]:
    """Consulta UNA serie diaria del BCRP. Devuelve {fecha_iso: valor}.

    Importante: la API publica en JSON para series diarias solo soporta
    una serie por consulta; pedir varias juntas (ej. compra-venta) devuelve
    una respuesta vacia. Por eso cada serie se consulta por separado.

    Reintenta automaticamente ante fallos de red temporales (ej. la
    maquina acaba de salir de suspension y el wifi aun no reconecta),
    que devuelven una respuesta vacia o incompleta en vez de un error
    HTTP claro.
    """
    url = f"{BASE_URL}/{codigo}/json/{desde}/{hasta}/esp"

    ultimo_error = None
    for intento in range(1, MAX_REINTENTOS + 1):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            break
        except (requests.exceptions.RequestException, ValueError) as e:
            ultimo_error = e
            if intento < MAX_REINTENTOS:
                print(f"  Intento {intento}/{MAX_REINTENTOS} fallo ({e.__class__.__name__}), "
                      f"reintentando en {ESPERA_ENTRE_REINTENTOS}s...")
                time.sleep(ESPERA_ENTRE_REINTENTOS)
    else:
        raise RuntimeError(
            f"No se pudo consultar la serie {codigo} tras {MAX_REINTENTOS} intentos. "
            f"Ultimo error: {ultimo_error}"
        )

    valores = {}
    for periodo in payload.get("periods", []):
        try:
            fecha = parsear_fecha_bcrp(periodo["name"])
            valor = float(periodo["values"][0])
        except (KeyError, ValueError, IndexError):
            # Filas con datos faltantes (feriados, "n.d.") se descartan
            continue
        valores[fecha] = valor
    return valores


def obtener_datos(desde: str, hasta: str) -> list[dict]:
    """Consulta compra y venta por separado y las combina por fecha."""
    compras = obtener_serie(SERIE_COMPRA, desde, hasta)
    ventas = obtener_serie(SERIE_VENTA, desde, hasta)

    fechas_comunes = sorted(set(compras) & set(ventas))
    registros = []
    for fecha in fechas_comunes:
        compra = compras[fecha]
        venta = ventas[fecha]
        registros.append({
            "fecha": fecha,
            "compra": compra,
            "venta": venta,
            "spread": round(venta - compra, 3),
        })
    return registros


def preparar_base(conn: sqlite3.Connection):
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())


def cargar_datos(conn: sqlite3.Connection, registros: list[dict]):
    ahora = datetime.now().isoformat(timespec="seconds")
    conn.executemany(
        """
        INSERT INTO tipo_cambio (fecha, compra, venta, spread, fecha_extraccion, fuente)
        VALUES (:fecha, :compra, :venta, :spread, :fecha_extraccion, 'BCRP-API')
        ON CONFLICT(fecha) DO UPDATE SET
            compra = excluded.compra,
            venta = excluded.venta,
            spread = excluded.spread,
            fecha_extraccion = excluded.fecha_extraccion
        """,
        [{**r, "fecha_extraccion": ahora} for r in registros],
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Extrae y carga tipo de cambio BCRP")
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--dias", type=int, help="Extraer los ultimos N dias")
    parser.add_argument("--desde", help="Fecha inicio YYYY-MM-DD")
    parser.add_argument("--hasta", help="Fecha fin YYYY-MM-DD")
    args = parser.parse_args()

    if args.dias:
        hasta = date.today()
        desde = hasta - timedelta(days=args.dias)
    else:
        hasta = date.fromisoformat(args.hasta) if args.hasta else date.today()
        desde = date.fromisoformat(args.desde) if args.desde else hasta - timedelta(days=30)

    print(f"Consultando BCRP: {desde} -> {hasta}")
    registros = obtener_datos(formatear_periodo(desde), formatear_periodo(hasta))
    print(f"Registros obtenidos: {len(registros)}")

    if not registros:
        print("No se obtuvieron datos (revisa el rango de fechas o la conexion).")
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        preparar_base(conn)
        cargar_datos(conn, registros)
        total = conn.execute("SELECT COUNT(*) FROM tipo_cambio").fetchone()[0]
        print(f"Base actualizada: {DB_PATH}")
        print(f"Total de registros historicos: {total}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
