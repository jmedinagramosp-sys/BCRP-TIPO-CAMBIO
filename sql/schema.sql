/* ============================================================
   Archivo:  schema.sql
   Objetivo: Esquema para almacenar el historico del tipo de
             cambio USD/PEN extraido de la API del BCRP.

   Compatible con SQLite (usado por el pipeline en Python) y
   adaptable a SQL Server cambiando los tipos de dato marcados.
   ============================================================ */

CREATE TABLE IF NOT EXISTS tipo_cambio (
    fecha           DATE PRIMARY KEY,   -- SQL Server: DATE
    compra          DECIMAL(6,3) NOT NULL,
    venta           DECIMAL(6,3) NOT NULL,
    spread          DECIMAL(6,3) NOT NULL,   -- venta - compra
    fecha_extraccion DATETIME NOT NULL,       -- cuando corrio el pipeline
    fuente          VARCHAR(20) NOT NULL DEFAULT 'BCRP-API'
);

-- Vista de apoyo: variacion diaria del tipo de cambio venta
CREATE VIEW IF NOT EXISTS v_variacion_diaria AS
SELECT
    fecha,
    venta,
    venta - LAG(venta) OVER (ORDER BY fecha) AS variacion_absoluta,
    ROUND(
        (venta - LAG(venta) OVER (ORDER BY fecha)) * 100.0
        / LAG(venta) OVER (ORDER BY fecha), 3
    ) AS variacion_porcentual
FROM tipo_cambio;
