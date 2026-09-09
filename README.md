# Pipeline de Tipo de Cambio USD/PEN — BCRP

Pipeline de datos real, de punta a punta: extrae el tipo de cambio
oficial USD/PEN publicado a diario por el **Banco Central de Reserva
del Perú (BCRP)**, lo acumula en una base de datos histórica, genera
una proyección de tendencia y lo deja listo para un dashboard en
Power BI.

A diferencia de un proyecto con datos simulados, esta base **crece
cada vez que corres el pipeline**: cada ejecución trae datos reales
nuevos publicados por el BCRP.

## Fuente de datos

[API pública de BCRPData](https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/api)
— gratuita, sin necesidad de API key ni registro.

- `PD04637PD` — Tipo de cambio interbancario, compra
- `PD04638PD` — Tipo de cambio interbancario, venta

## Arquitectura

```
API BCRP (JSON)
      ↓
extract_load.py   → limpia y hace upsert en SQLite (sin duplicar fechas)
      ↓
tipo_cambio.db     → histórico acumulado
      ↓
forecast.py        → regresión lineal simple + exporta CSV
      ↓
Power BI Desktop    → dashboard (histórico + tendencia)
```

## Estructura del repositorio

```
├── python/
│   ├── extract_load.py   # Extrae de la API BCRP y carga a SQLite
│   └── forecast.py        # Genera proyección de tendencia (CSV para Power BI)
├── sql/
│   └── schema.sql         # Esquema de la tabla + vista de variación diaria
├── data/                  # Se genera al correr el pipeline (no versionado)
├── docs/                  # Capturas del dashboard
├── requirements.txt
└── README.md
```

## Cómo ejecutar

```bash
pip install -r requirements.txt

# 1. Traer historial inicial (ej. último año)
python python/extract_load.py --desde 2025-01-01 --hasta 2026-09-07

# 2. Generar proyección de tendencia (7 días hacia adelante)
python python/forecast.py --dias-adelante 7

# 3. Correr esto periódicamente para mantener la base actualizada
python python/extract_load.py --dias 5
```

### Automatizar la actualización diaria

**Linux/Mac (cron)** — corre todos los días a las 9pm:
```
0 21 * * * cd /ruta/al/proyecto && /usr/bin/python3 python/extract_load.py --dias 3
```

**Windows (Programador de tareas)**: crear una tarea básica que ejecute
`python.exe python/extract_load.py --dias 3` diariamente.

## Conectar Power BI

1. Obtener datos → SQLite (o "Base de datos ODBC" si usas el driver de SQLite)
2. Apuntar a `data/tipo_cambio.db`, tabla `tipo_cambio`
3. Para la proyección: Obtener datos → Texto/CSV → `data/proyeccion.csv`
4. Relacionar ambas fuentes por `fecha`

### Visuales sugeridos

- Línea de tiempo: tipo de cambio venta (histórico + proyección, con color distinto)
- KPI cards: último valor, variación % vs. día anterior (usa la vista `v_variacion_diaria`)
- Histograma de variación diaria para ver volatilidad

## Nota importante sobre la proyección

El modelo de `forecast.py` es una **regresión lineal simple**, elegida
a propósito por su transparencia y facilidad de explicar, no por su
poder predictivo. **No es un modelo financiero** ni debe usarse para
decisiones reales de cambio de moneda o inversión — el tipo de cambio
depende de muchísimas variables que un modelo lineal no captura. Su
valor en este proyecto es demostrar el flujo completo (extracción →
almacenamiento → modelo → visualización), que es exactamente lo que
se evalúa en una entrevista de Data Engineering.

## Posibles extensiones

- Agregar más series del BCRP (inflación, reservas internacionales, tasa de referencia)
- Reemplazar la regresión lineal por un modelo de series de tiempo (ARIMA, Prophet)
- Migrar de SQLite a SQL Server o PostgreSQL para un caso más "enterprise"
- Desplegar `extract_load.py` en un scheduler en la nube (GitHub Actions, Azure Functions)

## Fuente y licencia de los datos

Datos de acceso público bajo las
[condiciones de uso de BCRPData](https://estadisticas.bcrp.gob.pe/estadisticas/series/ayuda/condiciones-de-uso).
