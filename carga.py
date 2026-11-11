"""
Carga de datos a MySQL - Ferretería Ulises
Requisitos:  pip install pandas sqlalchemy pymysql
Entrada:     una carpeta con un CSV por tabla, nombrado igual que la tabla (categoria.csv, cliente.csv, ...)

Flujo (según el diagrama):
  Inicio -> CSV transformados listos -> Script lee CSV y se conecta a MySQL
  -> Vaciar tablas -> Carga en orden de dependencias
  -> ¿Alguna sentencia falló?  Sí: corregir el CSV y repetir | No: carga completada -> Fin
"""

import os
import sys
import unicodedata
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

# ----------------------------------------------------------------------
# CONFIGURACIÓN (lee de variables de entorno para no exponer claves en GitHub)
# ----------------------------------------------------------------------
CARPETA_CSV   = "csv_transformados"   # carpeta con los CSV transformados (uno por tabla)
SEPARADOR     = None                  # None = detecta "," o ";" automáticamente; o fija "," / ";"
DECIMAL       = "."                   # "." (12.50) o "," (12,50) según cómo estén escritos los precios
FORMATO_FECHA = "%Y-%m-%d"            # formato de las columnas fecha en los CSV (ej. 2026-09-14)

HOST       = os.getenv("MYSQL_HOST", "localhost")
PUERTO     = int(os.getenv("MYSQL_PORT", "3306"))
USUARIO    = os.getenv("MYSQL_USER", "root")
PASSWORD   = os.getenv("MYSQL_PASSWORD", "M@nuel101101")
BASE_DATOS = os.getenv("MYSQL_DB", "ferreteria_ulises")

# Orden de carga según las claves foráneas del modelo físico.
# Cada nivel solo depende de tablas de niveles anteriores.
ORDEN_CARGA = [
    ["categoria", "cliente", "empleado"],               # 1. Tablas padre
    ["producto", "proveedor", "venta", "merma"],        # 2. Dependen de las padre
    ["pedido", "detalle_venta"],                        # 3. Dependen de las anteriores
    ["detalle_pedido", "comprobante"],                  # 4. Dependen de pedido
]
TABLAS = [t for nivel in ORDEN_CARGA for t in nivel]

# Columnas que se leen como texto para no perder ceros iniciales (DNI, teléfonos, N.º de operación)
COLUMNAS_TEXTO = {"dni", "telefono", "num_de_op"}


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def sin_acentos(texto):
    """'id_dueño' -> 'id_dueno' (permite que el CSV y la BD difieran solo en acentos/ñ)."""
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def mensaje_error(e):
    """Extrae el mensaje original de MySQL (p. ej. clave foránea que falla) desde la cadena de excepciones."""
    while e.__cause__ is not None:
        e = e.__cause__
    return str(getattr(e, "orig", e))


def leer_texto(ruta):
    """Prueba UTF-8 (con o sin BOM) y, si falla, Windows-1252 (CSV típico de Excel)."""
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            with open(ruta, encoding=codificacion) as f:
                f.read()
            return codificacion
        except UnicodeDecodeError:
            continue
    sys.exit(f"ERROR: no se pudo determinar la codificación de {ruta}")


def detectar_separador(ruta, codificacion):
    """Elige entre ',' y ';' contando cuál aparece más en la fila de encabezados."""
    with open(ruta, encoding=codificacion) as f:
        encabezado = f.readline()
    return ";" if encabezado.count(";") > encabezado.count(",") else ","


# ----------------------------------------------------------------------
# PASO 1: Archivos transformados listos -> el script lee los CSV (pandas)
# ----------------------------------------------------------------------
def leer_csv(carpeta):
    print(f"[1/3] Leyendo CSV transformados de: {carpeta}")
    if not os.path.isdir(carpeta):
        sys.exit(f"ERROR: no existe la carpeta '{carpeta}'")

    # nombre de archivo en minúsculas (sin .csv) -> ruta real
    archivos = {f[:-4].lower(): os.path.join(carpeta, f)
                for f in os.listdir(carpeta) if f.lower().endswith(".csv")}
    faltantes = [t for t in TABLAS if t not in archivos]
    if faltantes:
        sys.exit(f"ERROR: faltan los CSV de las tablas: {', '.join(faltantes)}")

    datos = {}
    for tabla in TABLAS:
        ruta = archivos[tabla]
        cod = leer_texto(ruta)
        sep = SEPARADOR or detectar_separador(ruta, cod)

        # Columnas de texto sin importar mayúsculas/minúsculas del encabezado (DNI, Telefono, ...)
        encabezado = pd.read_csv(ruta, sep=sep, encoding=cod, nrows=0).columns
        tipos = {c: str for c in encabezado if str(c).strip().lower() in COLUMNAS_TEXTO}

        df = pd.read_csv(ruta, sep=sep, encoding=cod, decimal=DECIMAL, dtype=tipos,
                         keep_default_na=False, na_values=[""])   # solo el campo vacío cuenta como NULL
        df.columns = [str(c).strip().lower() for c in df.columns]
        datos[tabla] = preparar(df.dropna(how="all"), tabla)       # descarta filas totalmente vacías
    return datos


def preparar(df, tabla):
    """Deja el DataFrame listo para insertar: enteros sin '.0', fechas como DATE y vacíos como NULL."""
    df = df.convert_dtypes()           # evita que un INT con vacíos (ej. ID_Empleado) pase a float
    for col in df.columns:
        if col.startswith("fecha"):
            try:
                df[col] = pd.to_datetime(df[col], format=FORMATO_FECHA).dt.date
            except ValueError as e:
                sys.exit(f"ERROR: fechas inválidas en '{tabla}.{col}' (se espera {FORMATO_FECHA}): {e}")
    return df.astype(object).where(pd.notna(df), None)             # NaN/NaT/NA -> None (NULL en MySQL)


# ----------------------------------------------------------------------
# PASO 2: Conectarse a MySQL y validar contra el esquema
# ----------------------------------------------------------------------
def conectar():
    print(f"[1/3] Conectando a MySQL ({HOST}:{PUERTO}/{BASE_DATOS})")
    url = URL.create("mysql+pymysql", username=USUARIO, password=PASSWORD,
                     host=HOST, port=PUERTO, database=BASE_DATOS)
    engine = create_engine(url)
    try:
        with engine.connect() as con:
            con.execute(text("SELECT 1"))
    except SQLAlchemyError as e:
        sys.exit(f"ERROR de conexión: {mensaje_error(e)}")
    return engine


def resolver_tablas(engine):
    """Devuelve {nombre en minúsculas: nombre real en MySQL} (el .sql crea CATEGORIA, CLIENTE, ...)."""
    reales = {t.lower(): t for t in inspect(engine).get_table_names()}
    faltan = [t for t in TABLAS if t not in reales]
    if faltan:
        sys.exit(f"ERROR: la base '{BASE_DATOS}' no tiene las tablas: {', '.join(faltan)}. "
                 "Ejecuta primero ferreteria_ulises.sql")
    return reales


def validar_columnas(engine, datos, reales):
    """Comprueba que las columnas del CSV existan en cada tabla y las renombra al nombre exacto de la BD."""
    insp = inspect(engine)
    for tabla in TABLAS:
        # nombre normalizado -> nombre real de la columna en MySQL (ej. 'id_dueno' -> 'ID_Dueño')
        columnas_bd = {sin_acentos(c["name"].lower()): c["name"] for c in insp.get_columns(reales[tabla])}
        extras = [c for c in datos[tabla].columns if sin_acentos(c) not in columnas_bd]
        if extras:
            sys.exit(f"ERROR: el CSV '{tabla}.csv' tiene columnas que no existen en la tabla: {extras}")
        datos[tabla].columns = [columnas_bd[sin_acentos(c)] for c in datos[tabla].columns]


# ----------------------------------------------------------------------
# PASO 3: Vaciar las tablas (evita duplicados al repetir la carga)
# ----------------------------------------------------------------------
def vaciar_tablas(engine, reales):
    print("[2/3] Vaciando las tablas")
    with engine.connect() as con:
        con.execute(text("SET FOREIGN_KEY_CHECKS = 0"))          # permite TRUNCATE con claves foráneas
        try:
            for tabla in reversed(TABLAS):
                con.execute(text(f"TRUNCATE TABLE `{reales[tabla]}`"))
        finally:
            con.execute(text("SET FOREIGN_KEY_CHECKS = 1"))      # siempre se reactiva
            con.commit()


# ----------------------------------------------------------------------
# PASO 4: Carga en orden de dependencias  +  decisión "¿Alguna sentencia falló?"
# ----------------------------------------------------------------------
def cargar(engine, datos, reales):
    print("[3/3] Carga en orden de dependencias")
    tabla = None
    try:
        # Una sola transacción: si alguna sentencia falla, se revierte TODO (no queda carga a medias)
        with engine.begin() as con:
            for i, nivel in enumerate(ORDEN_CARGA, start=1):
                for tabla in nivel:
                    datos[tabla].to_sql(reales[tabla], con, if_exists="append", index=False, chunksize=500)
                    print(f"      nivel {i}: {tabla:<15} {len(datos[tabla]):>5} filas insertadas")
    except (SQLAlchemyError, pd.errors.DatabaseError) as e:
        # ¿Alguna sentencia falló? = Sí -> corregir en el archivo transformado y repetir la carga
        print(f"\nERROR al insertar en '{tabla}'. Se revirtió toda la carga.")
        print(f"Detalle: {mensaje_error(e)}")
        print(f"Corrige '{tabla}.csv' (o el archivo que corresponda) y vuelve a ejecutar el script; "
              "las tablas se vaciarán de nuevo.")
        sys.exit(1)

    # ¿Alguna sentencia falló? = No -> carga completada satisfactoriamente
    print(f"\nCarga de datos completada satisfactoriamente: "
          f"base '{BASE_DATOS}' con sus {len(TABLAS)} tablas pobladas.")


# ----------------------------------------------------------------------
# Flujo principal
# ----------------------------------------------------------------------
def main():
    datos = leer_csv(CARPETA_CSV)             # Archivos transformados listos + lectura con pandas
    engine = conectar()                       # Script se conecta a MySQL
    reales = resolver_tablas(engine)          # nombres reales de las tablas (CATEGORIA, CLIENTE, ...)
    validar_columnas(engine, datos, reales)   # revisa columnas antes de modificar la BD
    vaciar_tablas(engine, reales)             # Vaciar las tablas
    cargar(engine, datos, reales)             # Carga en orden de dependencias -> ¿falló alguna sentencia?


if __name__ == "__main__":
    main()