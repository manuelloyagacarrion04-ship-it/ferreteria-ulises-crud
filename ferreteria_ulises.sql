CREATE DATABASE IF NOT EXISTS ferreteria_ulises;
USE ferreteria_ulises;

-- 1. Tabla CATEGORIA (Independiente)
CREATE TABLE CATEGORIA (
    ID_Categoria INT PRIMARY KEY,
    Nombre VARCHAR(100) NOT NULL
);

-- 2. Tabla CLIENTE (Independiente)
CREATE TABLE CLIENTE (
    ID_Cliente INT PRIMARY KEY,
    Nombre VARCHAR(100) NOT NULL,
    Apellido_Paterno VARCHAR(100) NOT NULL,
    Apellido_Materno VARCHAR(100) NOT NULL,
    Telefono VARCHAR(20),
    Porcentaje_Descuento DECIMAL(5,2),
    Total_Transacciones INT
);

-- 3. Tabla EMPLEADO (Independiente)
CREATE TABLE EMPLEADO (
    ID_Empleado INT PRIMARY KEY,
    Nombre VARCHAR(100) NOT NULL,
    Apellido_Paterno VARCHAR(100) NOT NULL,
    Apellido_Materno VARCHAR(100) NOT NULL,
    DNI VARCHAR(20) NOT NULL UNIQUE
);

-- 4. Tabla PRODUCTO (Depende de CATEGORIA)
CREATE TABLE PRODUCTO (
    ID_Producto INT PRIMARY KEY,
    Nombre VARCHAR(100) NOT NULL,
    Stock INT NOT NULL,
    Precio_Venta DECIMAL(10,2) NOT NULL,
    Precio_Compra DECIMAL(10,2) NOT NULL,
    Descripcion TEXT,
    Ubicacion VARCHAR(100),
    ID_Categoria INT,
    FOREIGN KEY (ID_Categoria) REFERENCES CATEGORIA(ID_Categoria)
);

-- 5. Tabla PROVEEDOR (Depende de EMPLEADO)
CREATE TABLE PROVEEDOR (
    ID_Proveedor INT PRIMARY KEY,
    Nombre VARCHAR(100) NOT NULL,
    Apellido_Paterno VARCHAR(100),
    Apellido_Materno VARCHAR(100),
    Telefono VARCHAR(20),
    ID_Empleado INT,
    FOREIGN KEY (ID_Empleado) REFERENCES EMPLEADO(ID_Empleado)
);

-- 6. Tabla MERMA (Depende de EMPLEADO)
CREATE TABLE MERMA (
    ID_Merma INT PRIMARY KEY,
    Fecha DATE NOT NULL,
    Cantidad INT NOT NULL,
    Precio DECIMAL(10,2) NOT NULL,
    Subtotal DECIMAL(10,2) NOT NULL,
    ID_Empleado INT,
    FOREIGN KEY (ID_Empleado) REFERENCES EMPLEADO(ID_Empleado)
);

-- 7. Tabla VENTA (Depende de EMPLEADO y CLIENTE)
CREATE TABLE VENTA (
    ID_Venta INT PRIMARY KEY,
    Fecha DATE NOT NULL,
    Metodo_Pago VARCHAR(50),
    Tipo_Comprobante VARCHAR(50),
    Total DECIMAL(10,2) NOT NULL,
    ID_Empleado INT,
    ID_Cliente INT,
    FOREIGN KEY (ID_Empleado) REFERENCES EMPLEADO(ID_Empleado),
    FOREIGN KEY (ID_Cliente) REFERENCES CLIENTE(ID_Cliente)
);

-- 8. Tabla DETALLE_VENTA (Depende de VENTA y PRODUCTO)
CREATE TABLE DETALLE_VENTA (
    ID_Venta INT,
    ID_Producto INT,
    Cantidad INT NOT NULL,
    Precio_Unitario DECIMAL(10,2) NOT NULL,
    Subtotal DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (ID_Venta, ID_Producto),
    FOREIGN KEY (ID_Venta) REFERENCES VENTA(ID_Venta),
    FOREIGN KEY (ID_Producto) REFERENCES PRODUCTO(ID_Producto)
);

-- 9. Tabla PEDIDO (Depende de PROVEEDOR)
CREATE TABLE PEDIDO (
    ID_Pedido INT PRIMARY KEY,
    Fecha DATE NOT NULL,
    Estado VARCHAR(50),
    Total DECIMAL(10,2) NOT NULL,
    ID_Dueño INT,
    ID_Proveedor INT,
    FOREIGN KEY (ID_Proveedor) REFERENCES PROVEEDOR(ID_Proveedor)
);

-- 10. Tabla COMPROBANTE (Depende de PEDIDO)
CREATE TABLE COMPROBANTE (
    Num_de_OP VARCHAR(50) PRIMARY KEY,
    Fecha DATE NOT NULL,
    ID_Pedido INT,
    FOREIGN KEY (ID_Pedido) REFERENCES PEDIDO(ID_Pedido)
);

-- 11. Tabla DETALLE_PEDIDO (Depende de PEDIDO y PROVEEDOR)
CREATE TABLE DETALLE_PEDIDO (
    ID_Detalle INT PRIMARY KEY,
    Cantidad INT NOT NULL,
    Nombre_Producto VARCHAR(100) NOT NULL,
    ID_Proveedor INT,
    ID_Pedido INT,
    FOREIGN KEY (ID_Proveedor) REFERENCES PROVEEDOR(ID_Proveedor),
    FOREIGN KEY (ID_Pedido) REFERENCES PEDIDO(ID_Pedido)
);