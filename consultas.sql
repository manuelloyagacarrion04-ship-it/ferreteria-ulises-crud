USE ferreteria_ulises;

-- 0.1  PARÁMETROS 
SET @umbral_stock_bajo  = 5;    -- RN-01: "stock bajo" = stock <= este valor
SET @dias_nuevo_ingreso = 30;   -- RN-03: un producto es "nuevo" durante N días desde su primer pedido entregado
SET @dias_reclamo       = 30;   -- RN-05: plazo para reclamar fallas de fábrica al proveedor
SET @reajuste_pct       = 5;    -- RN-07: % de aumento de precio de catálogo que se simula
SET @unidades_baja      = 1;    -- RN-05/RN-06: unidades que se dan de baja en la demostración

-- RN-04: escala de descuento por compras acumuladas (menos de @escala_n1 compras = 0 %)
SET @escala_n1 = 3;  SET @escala_d1 = 3;     -- desde 3 compras -> 3 %
SET @escala_n2 = 5;  SET @escala_d2 = 5;     -- desde 5 compras -> 5 %
SET @escala_n3 = 8;  SET @escala_d3 = 10;    -- desde 8 compras -> 10 %

-- Producto de las demostraciones RN-05/06/07: por defecto el más vendido
-- (así siempre tiene ventas). Se puede reemplazar por un ID fijo.
SET @id_producto_demo = (SELECT ID_Producto
                         FROM DETALLE_VENTA
                         GROUP BY ID_Producto
                         ORDER BY COUNT(*) DESC, ID_Producto
                         LIMIT 1);

-- Fecha "de hoy" para el plazo de reclamo: último movimiento cargado
-- (los datos son históricos). En producción reemplazar por CURDATE().
SET @fecha_referencia = GREATEST((SELECT MAX(Fecha) FROM VENTA),
                                 (SELECT MAX(Fecha) FROM PEDIDO));

-- ---------------------------------------------------------------------
-- 0.2  VISTAS DE APOYO (solo leen datos)
-- ---------------------------------------------------------------------
-- Una fila por producto vendido en cada venta.
-- Precio_Catalogo es el VIGENTE hoy; Precio_Cobrado es el histórico guardado
-- en DETALLE_VENTA. Descuento_Pct se calcula contra el catálogo actual.
-- Tipo_Descuento clasifica el precio cobrado respecto al catálogo
-- (tolerancia de 1 centavo por redondeo).
CREATE OR REPLACE VIEW VW_LINEA_VENTA AS
SELECT v.ID_Venta, v.Fecha,
       dv.ID_Producto, p.Nombre AS Producto, p.Stock AS Stock_Actual,
       dv.Cantidad,
       p.Precio_Venta     AS Precio_Catalogo,
       dv.Precio_Unitario AS Precio_Cobrado,
       dv.Subtotal,
       ROUND((1 - dv.Precio_Unitario / NULLIF(p.Precio_Venta, 0)) * 100, 2) AS Descuento_Pct,
       CASE
         WHEN ABS(dv.Precio_Unitario - p.Precio_Venta)        <= 0.01 THEN 'Sin descuento'
         WHEN ABS(dv.Precio_Unitario - p.Precio_Venta * 0.90) <= 0.01 THEN '10 %'
         WHEN ABS(dv.Precio_Unitario - p.Precio_Venta * 0.70) <= 0.01 THEN '30 %'
         WHEN dv.Precio_Unitario < p.Precio_Venta                     THEN 'Otro descuento'
         ELSE 'Sobre catálogo'
       END AS Tipo_Descuento
FROM DETALLE_VENTA dv
JOIN VENTA    v ON v.ID_Venta    = dv.ID_Venta
JOIN PRODUCTO p ON p.ID_Producto = dv.ID_Producto;

-- Fecha del primer pedido entregado de cada producto y unidades recibidas.
-- DETALLE_PEDIDO no tiene ID_Producto: el enlace se hace por nombre del producto.
CREATE OR REPLACE VIEW VW_INGRESO_PRODUCTO AS
SELECT p.ID_Producto, p.Nombre AS Producto,
       MIN(pe.Fecha)    AS Fecha_Ingreso,
       SUM(dp.Cantidad) AS Unidades_Recibidas
FROM PRODUCTO p
JOIN DETALLE_PEDIDO dp ON dp.Nombre_Producto = p.Nombre
JOIN PEDIDO         pe ON pe.ID_Pedido       = dp.ID_Pedido
WHERE pe.Estado = 'Entregado'
GROUP BY p.ID_Producto, p.Nombre;


-- =====================================================================
-- RN-01  Stock bajo -> complementarios con 10 % o 30 % de descuento,
--        respaldado por un precio diferenciado registrado en la venta
-- =====================================================================

-- 1.1 Ventas con precio diferenciado de 10 % o 30 % (precio cobrado vs catálogo)
--     Stock_Bajo se evalúa con el stock actual del producto.
SELECT l.ID_Venta, l.Fecha, l.Producto,
       l.Stock_Actual,
       IF(l.Stock_Actual <= @umbral_stock_bajo, 'Sí', 'No') AS Stock_Bajo,
       l.Cantidad, l.Precio_Catalogo, l.Precio_Cobrado,
       l.Descuento_Pct, l.Tipo_Descuento AS Descuento_Aplicado
FROM VW_LINEA_VENTA l
WHERE l.Tipo_Descuento IN ('10 %', '30 %')
ORDER BY l.Fecha, l.ID_Venta, l.Producto;

-- 1.2 Resumen: cuánto se vendió con cada tipo de precio
SELECT l.Tipo_Descuento,
       COUNT(*)        AS Lineas_de_Venta,
       SUM(l.Cantidad) AS Unidades,
       ROUND(SUM((l.Precio_Catalogo - l.Precio_Cobrado) * l.Cantidad), 2) AS Monto_Descontado
FROM VW_LINEA_VENTA l
GROUP BY l.Tipo_Descuento
ORDER BY FIELD(l.Tipo_Descuento, '10 %', '30 %', 'Otro descuento', 'Sin descuento', 'Sobre catálogo');


-- =====================================================================
-- RN-02  Productos organizados físicamente por categorías
--        Se asume Ubicacion con formato R##-N##-P## (rack-nivel-posición),
--        como en la Figura 9 del informe. Zona = rack + nivel.
-- =====================================================================

-- 2.1 Dónde está físicamente cada categoría
WITH prod AS (
    SELECT p.ID_Producto, p.ID_Categoria, p.Stock,
           NULLIF(TRIM(p.Ubicacion), '')                         AS Ubicacion,
           SUBSTRING_INDEX(NULLIF(TRIM(p.Ubicacion), ''), '-', 2) AS Zona
    FROM PRODUCTO p
)
SELECT c.ID_Categoria, c.Nombre AS Categoria,
       COUNT(pr.ID_Producto)                                   AS Productos,
       COUNT(DISTINCT pr.Zona)                                 AS Zonas_que_ocupa,
       GROUP_CONCAT(DISTINCT pr.Zona ORDER BY pr.Zona SEPARATOR ', ') AS Zonas,
       SUM(pr.Ubicacion IS NULL)                               AS Productos_sin_ubicacion
FROM CATEGORIA c
LEFT JOIN prod pr ON pr.ID_Categoria = c.ID_Categoria
GROUP BY c.ID_Categoria, c.Nombre
ORDER BY c.ID_Categoria;

-- 2.2 Qué categorías conviven en cada zona (rack-nivel): una sola = bien organizada
WITH prod AS (
    SELECT p.ID_Producto, p.ID_Categoria, p.Nombre,
           SUBSTRING_INDEX(NULLIF(TRIM(p.Ubicacion), ''), '-', 2) AS Zona
    FROM PRODUCTO p
)
SELECT pr.Zona,
       COUNT(*)                                                         AS Productos,
       GROUP_CONCAT(DISTINCT c.Nombre ORDER BY c.Nombre SEPARATOR ', ') AS Categorias_en_la_zona,
       IF(COUNT(DISTINCT pr.ID_Categoria) = 1, 'Una sola categoría', 'Categorías mezcladas') AS Organizacion
FROM prod pr
JOIN CATEGORIA c ON c.ID_Categoria = pr.ID_Categoria
WHERE pr.Zona IS NOT NULL
GROUP BY pr.Zona
ORDER BY pr.Zona;


-- =====================================================================
-- RN-03  Nuevo ingreso: descuento promocional por un período, con el
--        valor cobrado guardado aparte del catálogo
-- =====================================================================

-- 3.1 Ventas de productos "nuevos" (dentro de @dias_nuevo_ingreso desde su primer
--     pedido entregado): precio de catálogo vs precio realmente cobrado
SELECT i.Producto, i.Fecha_Ingreso,
       l.ID_Venta, l.Fecha AS Fecha_Venta,
       DATEDIFF(l.Fecha, i.Fecha_Ingreso) AS Dias_Desde_Ingreso,
       l.Cantidad, l.Precio_Catalogo, l.Precio_Cobrado,
       l.Descuento_Pct, l.Tipo_Descuento
FROM VW_INGRESO_PRODUCTO i
JOIN VW_LINEA_VENTA      l ON l.ID_Producto = i.ID_Producto
WHERE l.Fecha >= i.Fecha_Ingreso
  AND DATEDIFF(l.Fecha, i.Fecha_Ingreso) <= @dias_nuevo_ingreso
ORDER BY i.Producto, l.Fecha, l.ID_Venta;


-- =====================================================================
-- RN-04  Clientes frecuentes: atributos con el conteo de compras que
--        permiten definir descuentos escalonados
-- =====================================================================

-- 4.1 Conteo registrado en CLIENTE vs compras reales en VENTA, y el descuento
--     que correspondería según la escala de compras acumuladas
WITH compras AS (
    SELECT ID_Cliente, COUNT(*) AS Compras_Reales, SUM(Total) AS Monto_Total
    FROM VENTA
    GROUP BY ID_Cliente
)
SELECT cl.ID_Cliente,
       CONCAT_WS(' ', cl.Nombre, cl.Apellido_Paterno, cl.Apellido_Materno) AS Cliente,
       COALESCE(cl.Total_Transacciones, 0) AS Compras_Registradas,
       COALESCE(co.Compras_Reales, 0)      AS Compras_en_VENTA,
       IF(COALESCE(cl.Total_Transacciones, 0) = COALESCE(co.Compras_Reales, 0),
          'Coincide', 'Difiere')            AS Conteo,
       COALESCE(co.Monto_Total, 0)         AS Monto_Total,
       cl.Porcentaje_Descuento             AS Dscto_Registrado,
       CASE WHEN COALESCE(cl.Total_Transacciones, 0) >= @escala_n3 THEN @escala_d3
            WHEN COALESCE(cl.Total_Transacciones, 0) >= @escala_n2 THEN @escala_d2
            WHEN COALESCE(cl.Total_Transacciones, 0) >= @escala_n1 THEN @escala_d1
            ELSE 0
       END                                 AS Dscto_Segun_Escala
FROM CLIENTE cl
LEFT JOIN compras co ON co.ID_Cliente = cl.ID_Cliente
ORDER BY Compras_Registradas DESC, Monto_Total DESC;


-- =====================================================================
-- RN-05  Fallas de fábrica: se ajusta el stock y se verifica con el proveedor
-- =====================================================================

-- 5.1 Trazabilidad para el reclamo: pedidos entregados aún dentro del plazo,
--     con proveedor, teléfono y comprobante de pago
SELECT pe.ID_Pedido, pe.Fecha,
       DATEDIFF(@fecha_referencia, pe.Fecha)                   AS Dias_Transcurridos,
       @dias_reclamo - DATEDIFF(@fecha_referencia, pe.Fecha)   AS Dias_Restantes_Reclamo,
       CONCAT_WS(' ', pr.Nombre, pr.Apellido_Paterno, pr.Apellido_Materno) AS Proveedor,
       pr.Telefono,
       COUNT(dp.ID_Detalle) AS Items,
       SUM(dp.Cantidad)     AS Unidades,
       pe.Total,
       co.Num_de_OP         AS Comprobante
FROM PEDIDO pe
JOIN PROVEEDOR pr        ON pr.ID_Proveedor = pe.ID_Proveedor
JOIN DETALLE_PEDIDO dp   ON dp.ID_Pedido    = pe.ID_Pedido
LEFT JOIN COMPROBANTE co ON co.ID_Pedido    = pe.ID_Pedido
WHERE pe.Estado = 'Entregado'
  AND DATEDIFF(@fecha_referencia, pe.Fecha) <= @dias_reclamo
GROUP BY pe.ID_Pedido, pe.Fecha, pe.Total, pr.Nombre, pr.Apellido_Paterno, pr.Apellido_Materno,
         pr.Telefono, co.Num_de_OP
ORDER BY pe.Fecha DESC;


-- =====================================================================
-- RN-06  Productos dañados o no vendibles: baja registrada
-- =====================================================================

-- 6.1 Registro de bajas (MERMA) con acumulado de unidades y valor
SELECT m.ID_Merma, m.Fecha, m.Cantidad, m.Precio, m.Subtotal,
       SUM(m.Cantidad) OVER (ORDER BY m.Fecha, m.ID_Merma) AS Unidades_Acumuladas,
       SUM(m.Subtotal) OVER (ORDER BY m.Fecha, m.ID_Merma) AS Valor_Acumulado,
       CONCAT_WS(' ', e.Nombre, e.Apellido_Paterno)        AS Responsable
FROM MERMA m
LEFT JOIN EMPLEADO e ON e.ID_Empleado = m.ID_Empleado
ORDER BY m.Fecha, m.ID_Merma;


-- =====================================================================
-- RN-07  El precio de catálogo se reemplaza; el vendido queda inmutable
-- =====================================================================

-- 7.1 Evolución mensual del precio realmente cobrado vs el catálogo actual
SELECT l.Producto,
       DATE_FORMAT(l.Fecha, '%Y-%m')               AS Mes,
       SUM(l.Cantidad)                             AS Unidades,
       MIN(l.Precio_Cobrado)                       AS Precio_Min_Cobrado,
       MAX(l.Precio_Cobrado)                       AS Precio_Max_Cobrado,
       ROUND(SUM(l.Subtotal) / SUM(l.Cantidad), 2) AS Precio_Promedio_Cobrado,
       MAX(l.Precio_Catalogo)                      AS Precio_Catalogo_Actual
FROM VW_LINEA_VENTA l
GROUP BY l.ID_Producto, l.Producto, DATE_FORMAT(l.Fecha, '%Y-%m')
ORDER BY l.Producto, Mes;
