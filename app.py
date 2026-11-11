"""
Sistema CRUD - Ferretería Ulises
Experiencia Curricular: Base de Datos II - Universidad Nacional de Trujillo
Arquitectura por capas: Presentación (Streamlit) | Lógica y Validaciones | Datos (SQLAlchemy + PyMySQL)
"""

import hashlib
from datetime import date, datetime
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

# ==============================================================================
# 1. CONFIGURACIÓN DE PÁGINA Y ESTILOS VISUALES
# ==============================================================================
st.set_page_config(
    page_title="Sistema CRUD - Ferretería Ulises",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
        div[data-testid="stMetric"] {
            background-color: #f8fafc;
            border: 1px solid #e2e8f0;
            padding: 12px 16px;
            border-radius: 10px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.03);
        }
        div[data-testid="stMetricValue"] { font-size: 1.45rem; color: #0f172a; }
        .login-card {
            background-color: #ffffff;
            border: 1px solid #cbd5e1;
            border-radius: 12px;
            padding: 2rem;
            box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08);
        }
        .badge-rn {
            display: inline-block;
            background-color: #e0f2fe;
            color: #0369a1;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 0.78rem;
            font-weight: 600;
            margin-right: 6px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# ==============================================================================
# 2. CAPA DE AUTENTICACIÓN Y SESIÓN ROOT (Planteamiento 2)
# ==============================================================================
# Calculamos el hash SHA-256 real con el propio Python para que coincida 100% siempre
HASH_ULISES = hashlib.sha256("ulises2026".encode("utf-8")).hexdigest().lower()
HASH_MANUEL = hashlib.sha256("M@nuel101101".encode("utf-8")).hexdigest().lower()


def obtener_hash_esperado() -> str:
    try:
        return str(st.secrets["auth"]["root_password_hash"]).strip().lower()
    except Exception:
        return HASH_ULISES


def verificar_clave_root(clave_ingresada: str) -> bool:
    clave_limpia = clave_ingresada.strip()
    hash_ingresado = hashlib.sha256(clave_limpia.encode("utf-8")).hexdigest().lower()
    # Acepta el hash de secrets.toml, o el hash real de "ulises2026" o de "M@nuel101101"
    return hash_ingresado in {obtener_hash_esperado(), HASH_ULISES, HASH_MANUEL}


def pantalla_login_root():
    """
    Diseña la pantalla obligatoria de logeo root.
    - Usuario fijo 'root', campo de clave oculto y botón 'Ingresar'.
    - Sin 'registrarse' ni 'olvidé mi clave'.
    - Bloquea el formulario tras 3 intentos fallidos sin revelar qué dato falló.
    """
    if "autenticado" not in st.session_state:
        st.session_state.autenticado = False
    if "intentos_fallidos" not in st.session_state:
        st.session_state.intentos_fallidos = 0

    _, col_centro, _ = st.columns([1.2, 1.6, 1.2])
    with col_centro:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 🛠️ Sistema de Base de Datos — Ferretería Ulises")
        st.caption("Universidad Nacional de Trujillo • Escuela de Informática • Base de Datos II")
        st.divider()

        bloqueado = st.session_state.intentos_fallidos >= 3

        if bloqueado:
            st.error(
                "🔒 **Formulario bloqueado por seguridad.** Se superó el límite de 3 intentos fallidos permitidos en esta sesión."
            )

        with st.form("form_login_root", clear_on_submit=False):
            st.subheader("Acceso Único de Administrador")
            st.text_input("Usuario", value="root", disabled=True)
            clave = st.text_input(
                "Clave de acceso",
                type="password",
                disabled=bloqueado,
                placeholder="Ingrese la clave del root de la interfaz",
            )
            btn_ingresar = st.form_submit_button(
                "Ingresar", type="primary", use_container_width=True, disabled=bloqueado
            )

            if btn_ingresar and not bloqueado:
                if verificar_clave_root(clave):
                    st.session_state.autenticado = True
                    st.session_state.intentos_fallidos = 0
                    st.rerun()
                else:
                    st.session_state.intentos_fallidos += 1
                    restantes = 3 - st.session_state.intentos_fallidos
                    if restantes > 0:
                        st.error(
                            f"❌ Credenciales inválidas. No se pudo iniciar sesión (intentos restantes: {restantes})."
                        )
                    else:
                        st.rerun()


# Si no existe la marca de sesión, ninguna página abre conexión ni muestra datos
if not st.session_state.get("autenticado", False):
    pantalla_login_root()
    st.stop()


# ==============================================================================
# 3. CAPA DE ACCESO A DATOS (SQLAlchemy + PyMySQL + st.secrets)
# ==============================================================================
def obtener_credenciales_mysql() -> dict:
    try:
        cfg = st.secrets["mysql"]
        return {
            "host": cfg.get("host", "localhost"),
            "port": int(cfg.get("port", 3306)),
            "user": cfg.get("user", "root"),
            "password": cfg.get("password", "M@nuel101101"),
            "database": cfg.get("database", "ferreteria_ulises"),
        }
    except Exception:
        return {
            "host": "localhost",
            "port": 3306,
            "user": "root",
            "password": "M@nuel101101",
            "database": "ferreteria_ulises",
        }


@st.cache_resource
def obtener_engine():
    """Crea el engine de SQLAlchemy una sola vez en la sesión autenticada."""
    creds = obtener_credenciales_mysql()
    url = URL.create(
        "mysql+pymysql",
        username=creds["user"],
        password=creds["password"],
        host=creds["host"],
        port=creds["port"],
        database=creds["database"],
        query={"charset": "utf8mb4"},
    )
    return create_engine(url, pool_pre_ping=True)


def consultar_df(sql: str, params: dict = None) -> pd.DataFrame:
    """Ejecuta SELECT con parámetros enlazados y retorna un DataFrame de pandas."""
    engine = obtener_engine()
    with engine.connect() as con:
        return pd.read_sql(text(sql), con, params=params or {})


def ejecutar_dml(sql: str, params: dict = None):
    """Ejecuta INSERT, UPDATE o DELETE dentro de una transacción segura con parámetros enlazados."""
    engine = obtener_engine()
    with engine.begin() as con:
        con.execute(text(sql), params or {})


def siguiente_id(tabla: str, columna_pk: str) -> int:
    """Como el esquema no usa AUTO_INCREMENT, propone el siguiente identificador (MAX + 1)."""
    df = consultar_df(f"SELECT COALESCE(MAX({columna_pk}), 0) + 1 AS sig FROM {tabla}")
    return int(df["sig"].iloc[0])


def traducir_error_bd(err: Exception, contexto_entidad: str = "el registro") -> str:
    """
    Traduce errores técnicos de MySQL (claves foráneas o unicidad)
    a mensajes comprensibles orientados a las reglas del negocio.
    """
    msg = str(getattr(err, "orig", err)).lower()

    if "1451" in msg or "foreign key constraint fails" in msg:
        mensajes_fk = {
            "CATEGORIA": "No se puede eliminar la categoría porque tiene productos registrados asociados a ella (RN-02).",
            "PRODUCTO": "No se puede eliminar el producto porque ya tiene ventas registradas en DETALLE_VENTA.",
            "CLIENTE": "No se puede eliminar el cliente porque tiene ventas históricas registradas en VENTA.",
            "EMPLEADO": "No se puede eliminar el empleado porque figura como responsable en ventas, mermas o proveedores.",
            "PROVEEDOR": "No se puede eliminar el proveedor porque tiene pedidos o detalles de pedido registrados.",
            "PEDIDO": "No se puede eliminar el pedido directamente: primero debes eliminar sus registros en DETALLE_PEDIDO y su COMPROBANTE.",
            "VENTA": "No se puede eliminar la cabecera de venta porque aún tiene líneas asociadas en DETALLE_VENTA. Elimina primero su detalle.",
        }
        return mensajes_fk.get(
            contexto_entidad.upper(),
            f"No se puede completar la operación en {contexto_entidad} porque existen registros dependientes en otras tablas.",
        )

    if "1062" in msg or "duplicate entry" in msg:
        if "dni" in msg or contexto_entidad.upper() == "EMPLEADO":
            return "Ya existe un empleado registrado con ese número de DNI (el DNI es único) o el ID ya está en uso."
        if contexto_entidad.upper() == "DETALLE_VENTA":
            return "Ese producto ya está registrado dentro de esta misma venta (Clave primaria compuesta ID_Venta + ID_Producto duplicada)."
        return f"El identificador ingresado ya existe en la tabla {contexto_entidad}."

    if "1452" in msg:
        return "La referencia seleccionada (clave foránea) no existe en la tabla padre."

    return f"No se pudo completar la operación en la base de datos: {msg}"


def inicializar_vistas_apoyo():
    """Asegura que las vistas de lectura de consultas.sql estén disponibles."""
    vw_linea = """
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
    """
    vw_ingreso = """
    CREATE OR REPLACE VIEW VW_INGRESO_PRODUCTO AS
    SELECT p.ID_Producto, p.Nombre AS Producto,
           MIN(pe.Fecha)    AS Fecha_Ingreso,
           SUM(dp.Cantidad) AS Unidades_Recibidas
    FROM PRODUCTO p
    JOIN DETALLE_PEDIDO dp ON dp.Nombre_Producto = p.Nombre
    JOIN PEDIDO         pe ON pe.ID_Pedido       = dp.ID_Pedido
    WHERE pe.Estado = 'Entregado'
    GROUP BY p.ID_Producto, p.Nombre;
    """
    ejecutar_dml(vw_linea)
    ejecutar_dml(vw_ingreso)


# ==============================================================================
# 4. BARRA LATERAL Y VERIFICACIÓN DE CONEXIÓN A MYSQL
# ==============================================================================
with st.sidebar:
    st.markdown("## 🛠️ Ferretería Ulises")
    st.caption("Sesión activa: **Administrador (`root`)**")

    if st.button("🚪 Cerrar sesión", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.divider()

    try:
        consultar_df("SELECT 1")
        inicializar_vistas_apoyo()
        st.success("🟢 Conectado a MySQL (`ferreteria_ulises`)")
    except Exception as e:
        st.error("🔴 No se pudo conectar a MySQL local")
        st.caption(
            "Verifica que el servicio MySQL esté activo en localhost:3306 y que las credenciales en `.streamlit/secrets.toml` sean correctas."
        )
        st.code(str(e))
        st.stop()

    modulo_activo = st.radio(
        "📂 Módulos CRUD del Sistema",
        [
            "📦 1. Catálogo (Categoría y Producto)",
            "👥 2. Clientes y Empleados",
            "🚚 3. Abastecimiento (Proveedores y Pedidos)",
            "🧾 4. Ventas (Cabecera y Detalle)",
            "⚠️ 5. Mermas (Registro de Bajas)",
            "📊 6. Consultas de Reglas de Negocio",
        ],
    )

    st.divider()
    st.caption("📋 **Alcance del Sistema**")
    st.caption(
        "Operaciones CRUD directas sobre las 11 tablas del modelo físico, respetando claves primarias, foráneas y reglas RN-01 a RN-07."
    )


# ==============================================================================
# UTILIDAD DE BÚSQUEDA Y ORDENAMIENTO PARA LA VISTA CONSULTAR (READ)
# ==============================================================================
def filtrar_y_ordenar_df(df: pd.DataFrame, key_prefix: str) -> pd.DataFrame:
    """Agrega barra de búsqueda rápida, selector de columna de orden y dirección a cualquier tabla."""
    if df.empty:
        st.info("No hay registros almacenados en esta tabla.")
        return df

    c1, c2, c3 = st.columns([2.2, 1.2, 1])
    busqueda = c1.text_input(
        "🔍 Buscar en cualquier columna",
        key=f"{key_prefix}_search",
        placeholder="Escribe texto, código o monto para filtrar...",
    )
    col_orden = c2.selectbox("Ordenar por columna", df.columns.tolist(), key=f"{key_prefix}_sortcol")
    sentido = c3.selectbox("Orden", ["Ascendente", "Descendente"], key=f"{key_prefix}_sortdir")

    df_res = df.copy()
    if busqueda.strip():
        termino = busqueda.strip().lower()
        mascara = df_res.astype(str).apply(lambda col: col.str.lower().str.contains(termino, na=False)).any(axis=1)
        df_res = df_res[mascara]

    df_res = df_res.sort_values(by=col_orden, ascending=(sentido == "Ascendente"))
    return df_res


def recalcular_total_venta(id_venta: int):
    """Recalcula el atributo derivado VENTA.Total sumando DETALLE_VENTA.Subtotal."""
    ejecutar_dml(
        """
        UPDATE VENTA
        SET Total = COALESCE((SELECT SUM(Subtotal) FROM DETALLE_VENTA WHERE ID_Venta = :idv), 0.00)
        WHERE ID_Venta = :idv
        """,
        {"idv": int(id_venta)},
    )


# ==============================================================================
# MÓDULO 1: CATÁLOGO (CATEGORIA, PRODUCTO)
# ==============================================================================
if modulo_activo.startswith("📦 1."):
    st.title("📦 Módulo Catálogo")
    st.markdown(
        '<span class="badge-rn">RN-02: 1 Categoría por Producto y Ubicación Física</span>'
        '<span class="badge-rn">RN-05 / RN-06: Ajuste de Stock por Bajas</span>'
        '<span class="badge-rn">RN-07: Reemplazo de Precio sin alterar Ventas Pasadas</span>',
        unsafe_allow_html=True,
    )

    tab_cat, tab_prod = st.tabs(["🗂️ Tabla CATEGORIA", "🔩 Tabla PRODUCTO"])

    # ------------------------------------------------------------------
    # 1A. TABLA CATEGORIA
    # ------------------------------------------------------------------
    with tab_cat:
        df_cat = consultar_df(
            """
            SELECT c.ID_Categoria, c.Nombre,
                   COUNT(p.ID_Producto) AS Productos_Asociados
            FROM CATEGORIA c
            LEFT JOIN PRODUCTO p ON p.ID_Categoria = c.ID_Categoria
            GROUP BY c.ID_Categoria, c.Nombre
            ORDER BY c.ID_Categoria
            """
        )

        st.subheader("Consultar Categorías (Read)")
        df_cat_vista = filtrar_y_ordenar_df(df_cat, "cat")
        st.dataframe(df_cat_vista, use_container_width=True, hide_index=True)

        st.divider()
        op_cat = st.radio(
            "Operación en CATEGORIA:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_cat",
        )

        if op_cat == "➕ Ingresar (Create)":
            sig_id = siguiente_id("CATEGORIA", "ID_Categoria")
            with st.form("form_create_cat"):
                c1, c2 = st.columns([1, 2])
                id_cat = c1.number_input("ID_Categoria (Propuesto: máx + 1) *", min_value=1, value=sig_id, step=1)
                nom_cat = c2.text_input("Nombre de la Categoría *", max_chars=100)
                if st.form_submit_button("💾 Guardar Categoría", type="primary"):
                    if not nom_cat.strip():
                        st.error("El nombre de la categoría es obligatorio.")
                    else:
                        try:
                            ejecutar_dml(
                                "INSERT INTO CATEGORIA (ID_Categoria, Nombre) VALUES (:id, :nom)",
                                {"id": int(id_cat), "nom": nom_cat.strip()},
                            )
                            st.success(f"✅ Categoría #{id_cat} ('{nom_cat.strip()}') registrada correctamente.")
                            st.rerun()
                        except Exception as e:
                            st.error(traducir_error_bd(e, "CATEGORIA"))

        elif op_cat == "✏️ Actualizar (Update)":
            if df_cat.empty:
                st.warning("No hay categorías para actualizar.")
            else:
                opciones = {f"{r['ID_Categoria']} — {r['Nombre']}": r for _, r in df_cat.iterrows()}
                sel = st.selectbox("Selecciona la categoría a editar:", list(opciones.keys()), key="upd_cat_sel")
                reg = opciones[sel]
                with st.form("form_update_cat"):
                    c1, c2 = st.columns([1, 2])
                    c1.text_input("ID_Categoria (Clave Primaria bloqueada)", value=str(reg["ID_Categoria"]), disabled=True)
                    nuevo_nom = c2.text_input("Nombre de la Categoría *", value=reg["Nombre"], max_chars=100)
                    if st.form_submit_button("🔄 Actualizar Categoría", type="primary"):
                        if not nuevo_nom.strip():
                            st.error("El nombre no puede quedar vacío.")
                        else:
                            try:
                                ejecutar_dml(
                                    "UPDATE CATEGORIA SET Nombre = :nom WHERE ID_Categoria = :id",
                                    {"nom": nuevo_nom.strip(), "id": int(reg["ID_Categoria"])},
                                )
                                st.success(f"✅ Categoría #{reg['ID_Categoria']} actualizada.")
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "CATEGORIA"))

        elif op_cat == "🗑️ Eliminar (Delete)":
            if df_cat.empty:
                st.warning("No hay categorías para eliminar.")
            else:
                opciones = {
                    f"{r['ID_Categoria']} — {r['Nombre']} ({r['Productos_Asociados']} productos)": r
                    for _, r in df_cat.iterrows()
                }
                sel = st.selectbox("Selecciona la categoría a eliminar:", list(opciones.keys()), key="del_cat_sel")
                reg = opciones[sel]
                st.warning(
                    f"**Resumen de eliminación:** Categoría `ID_Categoria = {reg['ID_Categoria']}` | "
                    f"Nombre: **{reg['Nombre']}** | Productos asociados: **{reg['Productos_Asociados']}**"
                )
                confirmar = st.checkbox("Confirmo que deseo eliminar permanentemente esta categoría.", key="conf_del_cat")
                if st.button("🗑️ Ejecutar Eliminación", type="primary", disabled=not confirmar, key="btn_del_cat"):
                    try:
                        ejecutar_dml(
                            "DELETE FROM CATEGORIA WHERE ID_Categoria = :id",
                            {"id": int(reg["ID_Categoria"])},
                        )
                        st.success(f"✅ Categoría #{reg['ID_Categoria']} eliminada.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "CATEGORIA"))

    # ------------------------------------------------------------------
    # 1B. TABLA PRODUCTO
    # ------------------------------------------------------------------
    with tab_prod:
        df_prod = consultar_df(
            """
            SELECT p.ID_Producto, p.Nombre, p.Stock, p.Precio_Venta, p.Precio_Compra,
                   p.Ubicacion, p.ID_Categoria, c.Nombre AS Categoria, p.Descripcion
            FROM PRODUCTO p
            LEFT JOIN CATEGORIA c ON c.ID_Categoria = p.ID_Categoria
            ORDER BY p.ID_Producto
            """
        )
        df_cat_fk = consultar_df("SELECT ID_Categoria, Nombre FROM CATEGORIA ORDER BY ID_Categoria")

        st.subheader("Consultar Productos (Read)")
        df_prod_vista = filtrar_y_ordenar_df(df_prod, "prod")
        st.dataframe(df_prod_vista, use_container_width=True, hide_index=True)

        st.divider()
        op_prod = st.radio(
            "Operación en PRODUCTO:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_prod",
        )

        mapa_cat = {f"{r['ID_Categoria']} — {r['Nombre']}": int(r["ID_Categoria"]) for _, r in df_cat_fk.iterrows()}

        if op_prod == "➕ Ingresar (Create)":
            if not mapa_cat:
                st.warning("Primero debes registrar al menos una categoría en la tabla CATEGORIA.")
            else:
                sig_id_p = siguiente_id("PRODUCTO", "ID_Producto")
                with st.form("form_create_prod"):
                    f1, f2, f3 = st.columns([1, 2, 1.5])
                    id_p = f1.number_input("ID_Producto (máx + 1) *", min_value=1, value=sig_id_p, step=1)
                    nom_p = f2.text_input("Nombre del Producto *", max_chars=100)
                    cat_sel = f3.selectbox("Categoría (FK - RN-02) *", list(mapa_cat.keys()))

                    f4, f5, f6, f7 = st.columns(4)
                    stk_p = f4.number_input("Stock *", min_value=0, value=10, step=1)
                    pv_p = f5.number_input("Precio_Venta (S/) *", min_value=0.0, value=5.00, step=0.10, format="%.2f")
                    pc_p = f6.number_input("Precio_Compra (S/) *", min_value=0.0, value=3.50, step=0.10, format="%.2f")
                    ubi_p = f7.text_input("Ubicación (stand+nivel, ej. 1A)", value="1A", max_chars=100)

                    desc_p = st.text_area("Descripción (opcional)")

                    if st.form_submit_button("💾 Guardar Producto", type="primary"):
                        if not nom_p.strip():
                            st.error("El nombre del producto es obligatorio.")
                        elif pv_p <= 0 or pc_p <= 0:
                            st.error("Los precios de venta y compra deben ser mayores que cero.")
                        else:
                            try:
                                ejecutar_dml(
                                    """
                                    INSERT INTO PRODUCTO
                                    (ID_Producto, Nombre, Stock, Precio_Venta, Precio_Compra, Descripcion, Ubicacion, ID_Categoria)
                                    VALUES (:id, :nom, :stk, :pv, :pc, :desc, :ubi, :cat)
                                    """,
                                    {
                                        "id": int(id_p),
                                        "nom": nom_p.strip(),
                                        "stk": int(stk_p),
                                        "pv": float(pv_p),
                                        "pc": float(pc_p),
                                        "desc": desc_p.strip() or None,
                                        "ubi": ubi_p.strip() or None,
                                        "cat": mapa_cat[cat_sel],
                                    },
                                )
                                st.success(f"✅ Producto #{id_p} ('{nom_p.strip()}') registrado con éxito.")
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "PRODUCTO"))

        elif op_prod == "✏️ Actualizar (Update)":
            if df_prod.empty:
                st.warning("No hay productos para actualizar.")
            else:
                opciones_p = {
                    f"{r['ID_Producto']} — {r['Nombre']} (Stock: {r['Stock']} | S/ {r['Precio_Venta']:.2f})": r
                    for _, r in df_prod.iterrows()
                }
                sel_p = st.selectbox("Selecciona el producto a modificar:", list(opciones_p.keys()), key="upd_prod_sel")
                reg_p = opciones_p[sel_p]

                lista_keys_cat = list(mapa_cat.keys())
                idx_cat = 0
                for idx, k in enumerate(lista_keys_cat):
                    if mapa_cat[k] == reg_p["ID_Categoria"]:
                        idx_cat = idx
                        break

                with st.form("form_update_prod"):
                    st.info(
                        "💡 **RN-07 / RN-05 / RN-06:** El nuevo `Precio_Venta` reemplaza al anterior en el catálogo sin alterar las ventas históricas en `DETALLE_VENTA`. Las bajas por falla o daño se reflejan ajustando el `Stock`."
                    )
                    u1, u2, u3 = st.columns([1, 2, 1.5])
                    u1.text_input("ID_Producto (PK Bloqueada)", value=str(reg_p["ID_Producto"]), disabled=True)
                    u_nom = u2.text_input("Nombre *", value=str(reg_p["Nombre"]), max_chars=100)
                    u_cat = u3.selectbox("Categoría (FK - RN-02) *", lista_keys_cat, index=idx_cat)

                    u4, u5, u6, u7 = st.columns(4)
                    u_stk = u4.number_input("Stock *", min_value=0, value=int(reg_p["Stock"]), step=1)
                    u_pv = u5.number_input(
                        "Precio_Venta (S/) *", min_value=0.0, value=float(reg_p["Precio_Venta"]), step=0.10, format="%.2f"
                    )
                    u_pc = u6.number_input(
                        "Precio_Compra (S/) *", min_value=0.0, value=float(reg_p["Precio_Compra"]), step=0.10, format="%.2f"
                    )
                    u_ubi = u7.text_input("Ubicación (ej. 1A)", value=str(reg_p["Ubicacion"] or ""), max_chars=100)

                    u_desc = st.text_area("Descripción", value=str(reg_p["Descripcion"] or ""))

                    if st.form_submit_button("🔄 Guardar Cambios en Producto", type="primary"):
                        if not u_nom.strip():
                            st.error("El nombre del producto es obligatorio.")
                        elif u_pv <= 0 or u_pc <= 0:
                            st.error("Los precios no pueden ser cero ni negativos.")
                        else:
                            try:
                                ejecutar_dml(
                                    """
                                    UPDATE PRODUCTO
                                    SET Nombre = :nom, Stock = :stk, Precio_Venta = :pv, Precio_Compra = :pc,
                                        Descripcion = :desc, Ubicacion = :ubi, ID_Categoria = :cat
                                    WHERE ID_Producto = :id
                                    """,
                                    {
                                        "nom": u_nom.strip(),
                                        "stk": int(u_stk),
                                        "pv": float(u_pv),
                                        "pc": float(u_pc),
                                        "desc": u_desc.strip() or None,
                                        "ubi": u_ubi.strip() or None,
                                        "cat": mapa_cat[u_cat],
                                        "id": int(reg_p["ID_Producto"]),
                                    },
                                )
                                st.success(
                                    f"✅ Producto #{reg_p['ID_Producto']} actualizado. Las ventas pasadas conservan su precio histórico (RN-07)."
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "PRODUCTO"))

        elif op_prod == "🗑️ Eliminar (Delete)":
            if df_prod.empty:
                st.warning("No hay productos para eliminar.")
            else:
                opciones_p = {
                    f"{r['ID_Producto']} — {r['Nombre']} (Categoría: {r['Categoria']})": r
                    for _, r in df_prod.iterrows()
                }
                sel_p = st.selectbox("Selecciona el producto a eliminar:", list(opciones_p.keys()), key="del_prod_sel")
                reg_p = opciones_p[sel_p]
                st.warning(
                    f"**Resumen de eliminación:** Producto `ID_Producto = {reg_p['ID_Producto']}` | "
                    f"**{reg_p['Nombre']}** | Stock: {reg_p['Stock']} | Precio Venta: S/ {reg_p['Precio_Venta']:.2f}"
                )
                conf_p = st.checkbox("Confirmo que deseo eliminar este producto del catálogo.", key="conf_del_prod")
                if st.button("🗑️ Eliminar Producto", type="primary", disabled=not conf_p):
                    try:
                        ejecutar_dml("DELETE FROM PRODUCTO WHERE ID_Producto = :id", {"id": int(reg_p["ID_Producto"])})
                        st.success(f"✅ Producto #{reg_p['ID_Producto']} eliminado.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "PRODUCTO"))


# ==============================================================================
# MÓDULO 2: CLIENTES Y EMPLEADOS (CLIENTE, EMPLEADO)
# ==============================================================================
elif modulo_activo.startswith("👥 2."):
    st.title("👥 Módulo Clientes y Empleados")
    st.markdown(
        '<span class="badge-rn">RN-04: Escala de Descuento por Transacciones (0-2 = 0%, 3-4 = 3%, 5-7 = 5%, 8+ = 10%)</span>'
        '<span class="badge-rn">Restricción Física: DNI de Empleado Único</span>',
        unsafe_allow_html=True,
    )

    tab_cli, tab_emp = st.tabs(["🧑 Tabla CLIENTE", "🪪 Tabla EMPLEADO"])

    def calcular_escala_rn04(compras: int) -> float:
        if compras >= 8:
            return 10.00
        if compras >= 5:
            return 5.00
        if compras >= 3:
            return 3.00
        return 0.00

    # ------------------------------------------------------------------
    # 2A. TABLA CLIENTE
    # ------------------------------------------------------------------
    with tab_cli:
        df_cli = consultar_df(
            """
            SELECT ID_Cliente, Nombre, Apellido_Paterno, Apellido_Materno,
                   Telefono, Porcentaje_Descuento, Total_Transacciones
            FROM CLIENTE
            ORDER BY ID_Cliente
            """
        )

        col_head1, col_head2 = st.columns([2.5, 1.5])
        with col_head1:
            st.subheader("Consultar Clientes (Read)")
        with col_head2:
            if st.button("⚡ Aplicar Escala RN-04 a Todos los Clientes", type="secondary", use_container_width=True):
                ejecutar_dml(
                    """
                    UPDATE CLIENTE
                    SET Porcentaje_Descuento = CASE
                        WHEN COALESCE(Total_Transacciones, 0) >= 8 THEN 10.00
                        WHEN COALESCE(Total_Transacciones, 0) >= 5 THEN 5.00
                        WHEN COALESCE(Total_Transacciones, 0) >= 3 THEN 3.00
                        ELSE 0.00
                    END
                    """
                )
                st.success(
                    "✅ Se aplicó la escala de la RN-04 (0-2=0%, 3-4=3%, 5-7=5%, 8+=10%) según el Total_Transacciones de cada cliente."
                )
                st.rerun()

        df_cli_vista = filtrar_y_ordenar_df(df_cli, "cli")
        st.dataframe(df_cli_vista, use_container_width=True, hide_index=True)

        st.divider()
        op_cli = st.radio(
            "Operación en CLIENTE:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_cli",
        )

        if op_cli == "➕ Ingresar (Create)":
            sig_id_c = siguiente_id("CLIENTE", "ID_Cliente")
            with st.form("form_create_cli"):
                c1, c2, c3, c4 = st.columns(4)
                id_c = c1.number_input("ID_Cliente (máx + 1) *", min_value=1, value=sig_id_c, step=1)
                nom_c = c2.text_input("Nombre *", max_chars=100)
                ap_pat = c3.text_input("Apellido_Paterno *", max_chars=100)
                ap_mat = c4.text_input("Apellido_Materno *", max_chars=100)

                c5, c6, c7, c8 = st.columns(4)
                tel_c = c5.text_input("Teléfono", max_chars=20)
                tot_tr = c6.number_input("Total_Transacciones", min_value=0, value=0, step=1)
                dscto_c = c7.number_input("Porcentaje_Descuento (%)", min_value=0.0, max_value=100.0, value=0.0, step=1.0)
                aplicar_rn04_alta = c8.checkbox("Auto-asignar % según RN-04", value=True)

                if st.form_submit_button("💾 Guardar Cliente", type="primary"):
                    if not (nom_c.strip() and ap_pat.strip() and ap_mat.strip()):
                        st.error("Nombre, Apellido Paterno y Apellido Materno son obligatorios.")
                    else:
                        dscto_final = calcular_escala_rn04(int(tot_tr)) if aplicar_rn04_alta else float(dscto_c)
                        try:
                            ejecutar_dml(
                                """
                                INSERT INTO CLIENTE
                                (ID_Cliente, Nombre, Apellido_Paterno, Apellido_Materno, Telefono, Porcentaje_Descuento, Total_Transacciones)
                                VALUES (:id, :n, :ap, :am, :tel, :d, :tt)
                                """,
                                {
                                    "id": int(id_c),
                                    "n": nom_c.strip(),
                                    "ap": ap_pat.strip(),
                                    "am": ap_mat.strip(),
                                    "tel": tel_c.strip() or None,
                                    "d": dscto_final,
                                    "tt": int(tot_tr),
                                },
                            )
                            st.success(f"✅ Cliente #{id_c} registrado con descuento de {dscto_final:.2f}%.")
                            st.rerun()
                        except Exception as e:
                            st.error(traducir_error_bd(e, "CLIENTE"))

        elif op_cli == "✏️ Actualizar (Update)":
            if df_cli.empty:
                st.warning("No hay clientes para actualizar.")
            else:
                opciones_c = {
                    f"{r['ID_Cliente']} — {r['Nombre']} {r['Apellido_Paterno']} {r['Apellido_Materno']} (Compras: {r['Total_Transacciones']} | Dscto: {r['Porcentaje_Descuento']}%)": r
                    for _, r in df_cli.iterrows()
                }
                sel_c = st.selectbox("Selecciona el cliente a editar:", list(opciones_c.keys()), key="upd_cli_sel")
                reg_c = opciones_c[sel_c]

                with st.form("form_update_cli"):
                    u1, u2, u3, u4 = st.columns(4)
                    u1.text_input("ID_Cliente (PK Bloqueada)", value=str(reg_c["ID_Cliente"]), disabled=True)
                    u_nom = u2.text_input("Nombre *", value=str(reg_c["Nombre"]), max_chars=100)
                    u_ap = u3.text_input("Apellido_Paterno *", value=str(reg_c["Apellido_Paterno"]), max_chars=100)
                    u_am = u4.text_input("Apellido_Materno *", value=str(reg_c["Apellido_Materno"]), max_chars=100)

                    u5, u6, u7, u8 = st.columns(4)
                    u_tel = u5.text_input("Teléfono", value=str(reg_c["Telefono"] or ""), max_chars=20)
                    u_tt = u6.number_input(
                        "Total_Transacciones", min_value=0, value=int(reg_c["Total_Transacciones"] or 0), step=1
                    )
                    u_dscto = u7.number_input(
                        "Porcentaje_Descuento (%)",
                        min_value=0.0,
                        max_value=100.0,
                        value=float(reg_c["Porcentaje_Descuento"] or 0.0),
                        step=1.0,
                    )
                    usar_escala = u8.checkbox("Recalcular % con escala RN-04 al guardar", value=False)

                    if st.form_submit_button("🔄 Guardar Cambios en Cliente", type="primary"):
                        if not (u_nom.strip() and u_ap.strip() and u_am.strip()):
                            st.error("Nombre y apellidos son obligatorios.")
                        else:
                            dscto_guardar = calcular_escala_rn04(int(u_tt)) if usar_escala else float(u_dscto)
                            try:
                                ejecutar_dml(
                                    """
                                    UPDATE CLIENTE
                                    SET Nombre = :n, Apellido_Paterno = :ap, Apellido_Materno = :am,
                                        Telefono = :tel, Porcentaje_Descuento = :d, Total_Transacciones = :tt
                                    WHERE ID_Cliente = :id
                                    """,
                                    {
                                        "n": u_nom.strip(),
                                        "ap": u_ap.strip(),
                                        "am": u_am.strip(),
                                        "tel": u_tel.strip() or None,
                                        "d": dscto_guardar,
                                        "tt": int(u_tt),
                                        "id": int(reg_c["ID_Cliente"]),
                                    },
                                )
                                st.success(
                                    f"✅ Cliente #{reg_c['ID_Cliente']} actualizado (Compras: {u_tt}, Descuento: {dscto_guardar:.2f}%)."
                                )
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "CLIENTE"))

        elif op_cli == "🗑️ Eliminar (Delete)":
            if df_cli.empty:
                st.warning("No hay clientes para eliminar.")
            else:
                opciones_c = {
                    f"{r['ID_Cliente']} — {r['Nombre']} {r['Apellido_Paterno']} {r['Apellido_Materno']}": r
                    for _, r in df_cli.iterrows()
                }
                sel_c = st.selectbox("Selecciona el cliente a eliminar:", list(opciones_c.keys()), key="del_cli_sel")
                reg_c = opciones_c[sel_c]
                st.warning(
                    f"**Resumen de eliminación:** Cliente `ID_Cliente = {reg_c['ID_Cliente']}` | "
                    f"**{reg_c['Nombre']} {reg_c['Apellido_Paterno']} {reg_c['Apellido_Materno']}**"
                )
                conf_c = st.checkbox("Confirmo que deseo eliminar este cliente.", key="conf_del_cli")
                if st.button("🗑️ Eliminar Cliente", type="primary", disabled=not conf_c):
                    try:
                        ejecutar_dml("DELETE FROM CLIENTE WHERE ID_Cliente = :id", {"id": int(reg_c["ID_Cliente"])})
                        st.success(f"✅ Cliente #{reg_c['ID_Cliente']} eliminado.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "CLIENTE"))

    # ------------------------------------------------------------------
    # 2B. TABLA EMPLEADO
    # ------------------------------------------------------------------
    with tab_emp:
        df_emp = consultar_df(
            "SELECT ID_Empleado, Nombre, Apellido_Paterno, Apellido_Materno, DNI FROM EMPLEADO ORDER BY ID_Empleado"
        )
        st.subheader("Consultar Empleados (Read)")
        df_emp_vista = filtrar_y_ordenar_df(df_emp, "emp")
        st.dataframe(df_emp_vista, use_container_width=True, hide_index=True)

        st.divider()
        op_emp = st.radio(
            "Operación en EMPLEADO:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_emp",
        )

        if op_emp == "➕ Ingresar (Create)":
            sig_id_e = siguiente_id("EMPLEADO", "ID_Empleado")
            with st.form("form_create_emp"):
                e1, e2, e3, e4, e5 = st.columns(5)
                id_e = e1.number_input("ID_Empleado (máx + 1) *", min_value=1, value=sig_id_e, step=1)
                nom_e = e2.text_input("Nombre *", max_chars=100)
                ap_e = e3.text_input("Apellido_Paterno *", max_chars=100)
                am_e = e4.text_input("Apellido_Materno *", max_chars=100)
                dni_e = e5.text_input("DNI (Único, 8 dígitos) *", max_chars=20)

                if st.form_submit_button("💾 Guardar Empleado", type="primary"):
                    if not (nom_e.strip() and ap_e.strip() and am_e.strip() and dni_e.strip()):
                        st.error("Todos los campos del empleado (incluyendo DNI) son obligatorios.")
                    elif not dni_e.strip().isdigit() or len(dni_e.strip()) != 8:
                        st.error("El DNI debe contener exactamente 8 dígitos numéricos.")
                    else:
                        try:
                            ejecutar_dml(
                                """
                                INSERT INTO EMPLEADO (ID_Empleado, Nombre, Apellido_Paterno, Apellido_Materno, DNI)
                                VALUES (:id, :n, :ap, :am, :dni)
                                """,
                                {
                                    "id": int(id_e),
                                    "n": nom_e.strip(),
                                    "ap": ap_e.strip(),
                                    "am": am_e.strip(),
                                    "dni": dni_e.strip(),
                                },
                            )
                            st.success(f"✅ Empleado #{id_e} registrado con éxito.")
                            st.rerun()
                        except Exception as e:
                            st.error(traducir_error_bd(e, "EMPLEADO"))

        elif op_emp == "✏️ Actualizar (Update)":
            if df_emp.empty:
                st.warning("No hay empleados para actualizar.")
            else:
                opciones_e = {
                    f"{r['ID_Empleado']} — {r['Nombre']} {r['Apellido_Paterno']} (DNI: {r['DNI']})": r
                    for _, r in df_emp.iterrows()
                }
                sel_e = st.selectbox("Selecciona el empleado a editar:", list(opciones_e.keys()), key="upd_emp_sel")
                reg_e = opciones_e[sel_e]

                with st.form("form_update_emp"):
                    e1, e2, e3, e4, e5 = st.columns(5)
                    e1.text_input("ID_Empleado (PK Bloqueada)", value=str(reg_e["ID_Empleado"]), disabled=True)
                    u_ne = e2.text_input("Nombre *", value=str(reg_e["Nombre"]), max_chars=100)
                    u_ape = e3.text_input("Apellido_Paterno *", value=str(reg_e["Apellido_Paterno"]), max_chars=100)
                    u_ame = e4.text_input("Apellido_Materno *", value=str(reg_e["Apellido_Materno"]), max_chars=100)
                    u_dni = e5.text_input("DNI (Único) *", value=str(reg_e["DNI"]), max_chars=20)

                    if st.form_submit_button("🔄 Actualizar Empleado", type="primary"):
                        if not (u_ne.strip() and u_ape.strip() and u_ame.strip() and u_dni.strip()):
                            st.error("Todos los campos del empleado son obligatorios.")
                        elif not u_dni.strip().isdigit() or len(u_dni.strip()) != 8:
                            st.error("El DNI debe contener 8 dígitos numéricos.")
                        else:
                            try:
                                ejecutar_dml(
                                    """
                                    UPDATE EMPLEADO
                                    SET Nombre = :n, Apellido_Paterno = :ap, Apellido_Materno = :am, DNI = :dni
                                    WHERE ID_Empleado = :id
                                    """,
                                    {
                                        "n": u_ne.strip(),
                                        "ap": u_ape.strip(),
                                        "am": u_ame.strip(),
                                        "dni": u_dni.strip(),
                                        "id": int(reg_e["ID_Empleado"]),
                                    },
                                )
                                st.success(f"✅ Empleado #{reg_e['ID_Empleado']} actualizado.")
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "EMPLEADO"))

        elif op_emp == "🗑️ Eliminar (Delete)":
            if df_emp.empty:
                st.warning("No hay empleados para eliminar.")
            else:
                opciones_e = {
                    f"{r['ID_Empleado']} — {r['Nombre']} {r['Apellido_Paterno']} (DNI: {r['DNI']})": r
                    for _, r in df_emp.iterrows()
                }
                sel_e = st.selectbox("Selecciona el empleado a eliminar:", list(opciones_e.keys()), key="del_emp_sel")
                reg_e = opciones_e[sel_e]
                st.warning(
                    f"**Resumen de eliminación:** Empleado `ID_Empleado = {reg_e['ID_Empleado']}` | "
                    f"**{reg_e['Nombre']} {reg_e['Apellido_Paterno']}** (DNI: {reg_e['DNI']})"
                )
                conf_e = st.checkbox("Confirmo que deseo eliminar este empleado.", key="conf_del_emp")
                if st.button("🗑️ Eliminar Empleado", type="primary", disabled=not conf_e):
                    try:
                        ejecutar_dml("DELETE FROM EMPLEADO WHERE ID_Empleado = :id", {"id": int(reg_e["ID_Empleado"])})
                        st.success(f"✅ Empleado #{reg_e['ID_Empleado']} eliminado.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "EMPLEADO"))


# ==============================================================================
# MÓDULO 3: ABASTECIMIENTO (PROVEEDOR, PEDIDO, DETALLE_PEDIDO, COMPROBANTE)
# ==============================================================================
elif modulo_activo.startswith("🚚 3."):
    st.title("🚚 Módulo Abastecimiento")
    st.markdown(
        '<span class="badge-rn">1 Pedido pertenece a 1 Proveedor y genera 1 único Comprobante</span>'
        '<span class="badge-rn">DETALLE_PEDIDO guarda Nombre_Producto independiente del catálogo</span>'
        '<span class="badge-rn">Orden de borrado: primero DETALLE_PEDIDO y COMPROBANTE, luego PEDIDO</span>',
        unsafe_allow_html=True,
    )

    t_prov, t_ped, t_dped, t_comp = st.tabs(
        ["🏢 1. PROVEEDOR", "📦 2. PEDIDO", "📋 3. DETALLE_PEDIDO", "🧾 4. COMPROBANTE"]
    )

    df_emp_fk = consultar_df(
        "SELECT ID_Empleado, CONCAT_WS(' ', Nombre, Apellido_Paterno) AS Nom FROM EMPLEADO ORDER BY ID_Empleado"
    )
    mapa_emp_fk = {f"{r['ID_Empleado']} — {r['Nom']}": int(r["ID_Empleado"]) for _, r in df_emp_fk.iterrows()}

    # ------------------------------------------------------------------
    # 3A. PROVEEDOR
    # ------------------------------------------------------------------
    with t_prov:
        df_prov = consultar_df(
            """
            SELECT pr.ID_Proveedor, pr.Nombre, pr.Apellido_Paterno, pr.Apellido_Materno,
                   pr.Telefono, pr.ID_Empleado,
                   CONCAT_WS(' ', e.Nombre, e.Apellido_Paterno) AS Empleado_Contacto
            FROM PROVEEDOR pr
            LEFT JOIN EMPLEADO e ON e.ID_Empleado = pr.ID_Empleado
            ORDER BY pr.ID_Proveedor
            """
        )
        st.subheader("Consultar Proveedores (Read)")
        st.dataframe(filtrar_y_ordenar_df(df_prov, "prov"), use_container_width=True, hide_index=True)

        st.divider()
        op_pr = st.radio(
            "Operación en PROVEEDOR:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_prov",
        )

        if op_pr == "➕ Ingresar (Create)":
            sig_pr = siguiente_id("PROVEEDOR", "ID_Proveedor")
            with st.form("form_create_prov"):
                p1, p2, p3 = st.columns(3)
                id_pr = p1.number_input("ID_Proveedor (máx + 1) *", min_value=1, value=sig_pr, step=1)
                nom_pr = p2.text_input("Nombre *", max_chars=100)
                ap_pr = p3.text_input("Apellido_Paterno", max_chars=100)

                p4, p5, p6 = st.columns(3)
                am_pr = p4.text_input("Apellido_Materno", max_chars=100)
                tel_pr = p5.text_input("Teléfono", max_chars=20)
                emp_pr = p6.selectbox("ID_Empleado Responsable (FK) *", list(mapa_emp_fk.keys()))

                if st.form_submit_button("💾 Guardar Proveedor", type="primary"):
                    if not nom_pr.strip():
                        st.error("El nombre del proveedor es obligatorio.")
                    else:
                        try:
                            ejecutar_dml(
                                """
                                INSERT INTO PROVEEDOR (ID_Proveedor, Nombre, Apellido_Paterno, Apellido_Materno, Telefono, ID_Empleado)
                                VALUES (:id, :n, :ap, :am, :tel, :ide)
                                """,
                                {
                                    "id": int(id_pr),
                                    "n": nom_pr.strip(),
                                    "ap": ap_pr.strip() or None,
                                    "am": am_pr.strip() or None,
                                    "tel": tel_pr.strip() or None,
                                    "ide": mapa_emp_fk[emp_pr],
                                },
                            )
                            st.success(f"✅ Proveedor #{id_pr} registrado.")
                            st.rerun()
                        except Exception as e:
                            st.error(traducir_error_bd(e, "PROVEEDOR"))

        elif op_pr == "✏️ Actualizar (Update)":
            if df_prov.empty:
                st.warning("No hay proveedores para actualizar.")
            else:
                opc_pr = {
                    f"{r['ID_Proveedor']} — {r['Nombre']} {r['Apellido_Paterno'] or ''}": r
                    for _, r in df_prov.iterrows()
                }
                sel_pr = st.selectbox("Selecciona el proveedor a editar:", list(opc_pr.keys()), key="upd_prov_sel")
                reg_pr = opc_pr[sel_pr]

                keys_e = list(mapa_emp_fk.keys())
                idx_e = next((i for i, k in enumerate(keys_e) if mapa_emp_fk[k] == reg_pr["ID_Empleado"]), 0)

                with st.form("form_update_prov"):
                    p1, p2, p3 = st.columns(3)
                    p1.text_input("ID_Proveedor (PK Bloqueada)", value=str(reg_pr["ID_Proveedor"]), disabled=True)
                    u_npr = p2.text_input("Nombre *", value=str(reg_pr["Nombre"]), max_chars=100)
                    u_appr = p3.text_input("Apellido_Paterno", value=str(reg_pr["Apellido_Paterno"] or ""), max_chars=100)

                    p4, p5, p6 = st.columns(3)
                    u_ampr = p4.text_input("Apellido_Materno", value=str(reg_pr["Apellido_Materno"] or ""), max_chars=100)
                    u_telpr = p5.text_input("Teléfono", value=str(reg_pr["Telefono"] or ""), max_chars=20)
                    u_emppr = p6.selectbox("ID_Empleado (FK) *", keys_e, index=idx_e)

                    if st.form_submit_button("🔄 Actualizar Proveedor", type="primary"):
                        if not u_npr.strip():
                            st.error("El nombre del proveedor es obligatorio.")
                        else:
                            try:
                                ejecutar_dml(
                                    """
                                    UPDATE PROVEEDOR
                                    SET Nombre = :n, Apellido_Paterno = :ap, Apellido_Materno = :am,
                                        Telefono = :tel, ID_Empleado = :ide
                                    WHERE ID_Proveedor = :id
                                    """,
                                    {
                                        "n": u_npr.strip(),
                                        "ap": u_appr.strip() or None,
                                        "am": u_ampr.strip() or None,
                                        "tel": u_telpr.strip() or None,
                                        "ide": mapa_emp_fk[u_emppr],
                                        "id": int(reg_pr["ID_Proveedor"]),
                                    },
                                )
                                st.success(f"✅ Proveedor #{reg_pr['ID_Proveedor']} actualizado.")
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "PROVEEDOR"))

        elif op_pr == "🗑️ Eliminar (Delete)":
            if df_prov.empty:
                st.warning("No hay proveedores para eliminar.")
            else:
                opc_pr = {
                    f"{r['ID_Proveedor']} — {r['Nombre']} {r['Apellido_Paterno'] or ''}": r
                    for _, r in df_prov.iterrows()
                }
                sel_pr = st.selectbox("Selecciona el proveedor a eliminar:", list(opc_pr.keys()), key="del_prov_sel")
                reg_pr = opc_pr[sel_pr]
                st.warning(
                    f"**Resumen de eliminación:** Proveedor `ID_Proveedor = {reg_pr['ID_Proveedor']}` | **{reg_pr['Nombre']}**"
                )
                conf_pr = st.checkbox("Confirmo que deseo eliminar este proveedor.", key="conf_del_prov")
                if st.button("🗑️ Eliminar Proveedor", type="primary", disabled=not conf_pr):
                    try:
                        ejecutar_dml(
                            "DELETE FROM PROVEEDOR WHERE ID_Proveedor = :id", {"id": int(reg_pr["ID_Proveedor"])}
                        )
                        st.success(f"✅ Proveedor #{reg_pr['ID_Proveedor']} eliminado.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "PROVEEDOR"))

    # ------------------------------------------------------------------
    # 3B. PEDIDO
    # ------------------------------------------------------------------
    df_prov_fk = consultar_df(
        "SELECT ID_Proveedor, CONCAT_WS(' ', Nombre, Apellido_Paterno, Apellido_Materno) AS Nom FROM PROVEEDOR ORDER BY ID_Proveedor"
    )
    mapa_prov_fk = {f"{r['ID_Proveedor']} — {r['Nom']}": int(r["ID_Proveedor"]) for _, r in df_prov_fk.iterrows()}

    with t_ped:
        df_ped = consultar_df(
            """
            SELECT pe.ID_Pedido, pe.Fecha, pe.Estado, pe.Total, pe.ID_Dueño, pe.ID_Proveedor,
                   CONCAT_WS(' ', pr.Nombre, pr.Apellido_Paterno) AS Proveedor,
                   co.Num_de_OP AS Comprobante_Asociado,
                   (SELECT COUNT(*) FROM DETALLE_PEDIDO dp WHERE dp.ID_Pedido = pe.ID_Pedido) AS Lineas_Detalle
            FROM PEDIDO pe
            LEFT JOIN PROVEEDOR pr ON pr.ID_Proveedor = pe.ID_Proveedor
            LEFT JOIN COMPROBANTE co ON co.ID_Pedido = pe.ID_Pedido
            ORDER BY pe.ID_Pedido
            """
        )
        st.subheader("Consultar Pedidos (Read)")
        st.dataframe(filtrar_y_ordenar_df(df_ped, "ped"), use_container_width=True, hide_index=True)

        st.divider()
        op_pe = st.radio(
            "Operación en PEDIDO:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_ped",
        )

        if op_pe == "➕ Ingresar (Create)":
            sig_pe = siguiente_id("PEDIDO", "ID_Pedido")
            with st.form("form_create_ped"):
                c1, c2, c3 = st.columns(3)
                id_pe = c1.number_input("ID_Pedido (máx + 1) *", min_value=1, value=sig_pe, step=1)
                fec_pe = c2.date_input("Fecha *", value=date.today())
                est_pe = c3.selectbox("Estado *", ["Entregado", "Pendiente", "Cancelado"])

                c4, c5, c6 = st.columns(3)
                tot_pe = c4.number_input("Total del Pedido (S/) *", min_value=0.0, value=100.00, step=1.0, format="%.2f")
                dueno_pe = c5.number_input("ID_Dueño *", min_value=1, value=1, step=1)
                prov_pe = c6.selectbox("Proveedor (FK - 1 solo proveedor) *", list(mapa_prov_fk.keys()))

                if st.form_submit_button("💾 Guardar Pedido", type="primary"):
                    if tot_pe <= 0:
                        st.error("El monto total del pedido debe ser mayor a 0.")
                    else:
                        try:
                            ejecutar_dml(
                                """
                                INSERT INTO PEDIDO (ID_Pedido, Fecha, Estado, Total, `ID_Dueño`, ID_Proveedor)
                                VALUES (:id, :f, :est, :tot, :dueno, :prov)
                                """,
                                {
                                    "id": int(id_pe),
                                    "f": fec_pe,
                                    "est": est_pe,
                                    "tot": float(tot_pe),
                                    "dueno": int(dueno_pe),
                                    "prov": mapa_prov_fk[prov_pe],
                                },
                            )
                            st.success(f"✅ Pedido #{id_pe} registrado.")
                            st.rerun()
                        except Exception as e:
                            st.error(traducir_error_bd(e, "PEDIDO"))

        elif op_pe == "✏️ Actualizar (Update)":
            if df_ped.empty:
                st.warning("No hay pedidos para actualizar.")
            else:
                opc_pe = {
                    f"Pedido #{r['ID_Pedido']} — {r['Fecha']} ({r['Proveedor']} | S/ {r['Total']:.2f})": r
                    for _, r in df_ped.iterrows()
                }
                sel_pe = st.selectbox("Selecciona el pedido a editar:", list(opc_pe.keys()), key="upd_ped_sel")
                reg_pe = opc_pe[sel_pe]

                keys_pr = list(mapa_prov_fk.keys())
                idx_pr = next((i for i, k in enumerate(keys_pr) if mapa_prov_fk[k] == reg_pe["ID_Proveedor"]), 0)
                estados_disp = ["Entregado", "Pendiente", "Cancelado"]
                idx_est = estados_disp.index(reg_pe["Estado"]) if reg_pe["Estado"] in estados_disp else 0

                with st.form("form_update_ped"):
                    c1, c2, c3 = st.columns(3)
                    c1.text_input("ID_Pedido (PK Bloqueada)", value=str(reg_pe["ID_Pedido"]), disabled=True)
                    u_fec = c2.date_input("Fecha *", value=pd.to_datetime(reg_pe["Fecha"]).date())
                    u_est = c3.selectbox("Estado *", estados_disp, index=idx_est)

                    c4, c5, c6 = st.columns(3)
                    u_tot = c4.number_input(
                        "Total (S/) *", min_value=0.0, value=float(reg_pe["Total"]), step=1.0, format="%.2f"
                    )
                    u_dueno = c5.number_input("ID_Dueño *", min_value=1, value=int(reg_pe["ID_Dueño"] or 1), step=1)
                    u_prov = c6.selectbox("Proveedor (FK) *", keys_pr, index=idx_pr)

                    if st.form_submit_button("🔄 Actualizar Pedido", type="primary"):
                        if u_tot <= 0:
                            st.error("El total del pedido debe ser mayor que cero.")
                        else:
                            try:
                                ejecutar_dml(
                                    """
                                    UPDATE PEDIDO
                                    SET Fecha = :f, Estado = :est, Total = :tot, `ID_Dueño` = :dueno, ID_Proveedor = :prov
                                    WHERE ID_Pedido = :id
                                    """,
                                    {
                                        "f": u_fec,
                                        "est": u_est,
                                        "tot": float(u_tot),
                                        "dueno": int(u_dueno),
                                        "prov": mapa_prov_fk[u_prov],
                                        "id": int(reg_pe["ID_Pedido"]),
                                    },
                                )
                                st.success(f"✅ Pedido #{reg_pe['ID_Pedido']} actualizado.")
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "PEDIDO"))

        elif op_pe == "🗑️ Eliminar (Delete)":
            if df_ped.empty:
                st.warning("No hay pedidos para eliminar.")
            else:
                opc_pe = {
                    f"Pedido #{r['ID_Pedido']} — {r['Proveedor']} (Detalles: {r['Lineas_Detalle']} | Comprobante: {r['Comprobante_Asociado'] or 'Ninguno'})": r
                    for _, r in df_ped.iterrows()
                }
                sel_pe = st.selectbox("Selecciona el pedido a eliminar:", list(opc_pe.keys()), key="del_ped_sel")
                reg_pe = opc_pe[sel_pe]
                st.warning(
                    f"**Resumen de eliminación:** Pedido `ID_Pedido = {reg_pe['ID_Pedido']}` | Fecha: {reg_pe['Fecha']} | "
                    f"Total: S/ {reg_pe['Total']:.2f} | Ítems en DETALLE_PEDIDO: **{reg_pe['Lineas_Detalle']}** | "
                    f"COMPROBANTE: **{reg_pe['Comprobante_Asociado'] or 'Sin comprobante'}**"
                )
                st.caption(
                    "📌 Regla del módulo: Se elimina primero el detalle (`DETALLE_PEDIDO`) y el comprobante (`COMPROBANTE`), y después el pedido (`PEDIDO`)."
                )
                conf_pe = st.checkbox("Confirmo que deseo eliminar este pedido.", key="conf_del_ped")
                if st.button("🗑️ Eliminar Pedido", type="primary", disabled=not conf_pe):
                    try:
                        ejecutar_dml("DELETE FROM PEDIDO WHERE ID_Pedido = :id", {"id": int(reg_pe["ID_Pedido"])})
                        st.success(f"✅ Pedido #{reg_pe['ID_Pedido']} eliminado.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "PEDIDO"))

    # ------------------------------------------------------------------
    # 3C. DETALLE_PEDIDO
    # ------------------------------------------------------------------
    df_ped_fk = consultar_df(
        """
        SELECT pe.ID_Pedido, pe.Fecha, pe.ID_Proveedor,
               CONCAT_WS(' ', pr.Nombre, pr.Apellido_Paterno) AS Proveedor
        FROM PEDIDO pe
        JOIN PROVEEDOR pr ON pr.ID_Proveedor = pe.ID_Proveedor
        ORDER BY pe.ID_Pedido
        """
    )

    with t_dped:
        df_dp = consultar_df(
            """
            SELECT dp.ID_Detalle, dp.ID_Pedido, dp.Cantidad, dp.Nombre_Producto,
                   dp.ID_Proveedor, CONCAT_WS(' ', pr.Nombre, pr.Apellido_Paterno) AS Proveedor
            FROM DETALLE_PEDIDO dp
            LEFT JOIN PROVEEDOR pr ON pr.ID_Proveedor = dp.ID_Proveedor
            ORDER BY dp.ID_Detalle
            """
        )
        st.subheader("Consultar Detalles de Pedido (Read)")
        st.dataframe(filtrar_y_ordenar_df(df_dp, "dped"), use_container_width=True, hide_index=True)

        st.divider()
        op_dp = st.radio(
            "Operación en DETALLE_PEDIDO:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_dped",
        )

        mapa_ped_info = {
            f"Pedido #{r['ID_Pedido']} ({r['Fecha']} — Prov: {r['Proveedor']})": r for _, r in df_ped_fk.iterrows()
        }

        if op_dp == "➕ Ingresar (Create)":
            if not mapa_ped_info:
                st.warning("Primero debes registrar un pedido en la tabla PEDIDO.")
            else:
                sig_dp = siguiente_id("DETALLE_PEDIDO", "ID_Detalle")
                with st.form("form_create_dped"):
                    st.caption(
                        "📌 El detalle guarda la cantidad y el nombre del producto como texto libre (independiente del catálogo), y sincroniza automáticamente el proveedor del pedido."
                    )
                    d1, d2, d3, d4 = st.columns([1, 1.8, 1, 2])
                    id_dp = d1.number_input("ID_Detalle (máx + 1) *", min_value=1, value=sig_dp, step=1)
                    ped_sel = d2.selectbox("Pedido Asociado (FK) *", list(mapa_ped_info.keys()))
                    cant_dp = d3.number_input("Cantidad *", min_value=1, value=5, step=1)
                    nom_prod_dp = d4.text_input("Nombre_Producto (Texto libre) *", max_chars=100)

                    if st.form_submit_button("💾 Guardar Detalle de Pedido", type="primary"):
                        if not nom_prod_dp.strip():
                            st.error("El nombre del producto es obligatorio.")
                        else:
                            ped_row = mapa_ped_info[ped_sel]
                            try:
                                ejecutar_dml(
                                    """
                                    INSERT INTO DETALLE_PEDIDO (ID_Detalle, Cantidad, Nombre_Producto, ID_Proveedor, ID_Pedido)
                                    VALUES (:idd, :c, :np, :idp, :idped)
                                    """,
                                    {
                                        "idd": int(id_dp),
                                        "c": int(cant_dp),
                                        "np": nom_prod_dp.strip(),
                                        "idp": int(ped_row["ID_Proveedor"]),
                                        "idped": int(ped_row["ID_Pedido"]),
                                    },
                                )
                                st.success(f"✅ Detalle #{id_dp} agregado al Pedido #{ped_row['ID_Pedido']}.")
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "DETALLE_PEDIDO"))

        elif op_dp == "✏️ Actualizar (Update)":
            if df_dp.empty:
                st.warning("No hay detalles de pedido para actualizar.")
            else:
                opc_dp = {
                    f"Detalle #{r['ID_Detalle']} (Pedido #{r['ID_Pedido']} — {r['Nombre_Producto']} x {r['Cantidad']})": r
                    for _, r in df_dp.iterrows()
                }
                sel_dp = st.selectbox("Selecciona el detalle a editar:", list(opc_dp.keys()), key="upd_dped_sel")
                reg_dp = opc_dp[sel_dp]

                keys_pe = list(mapa_ped_info.keys())
                idx_pe = next(
                    (i for i, k in enumerate(keys_pe) if mapa_ped_info[k]["ID_Pedido"] == reg_dp["ID_Pedido"]), 0
                )

                with st.form("form_update_dped"):
                    d1, d2, d3, d4 = st.columns([1, 1.8, 1, 2])
                    d1.text_input("ID_Detalle (PK Bloqueada)", value=str(reg_dp["ID_Detalle"]), disabled=True)
                    u_ped_sel = d2.selectbox("Pedido Asociado (FK) *", keys_pe, index=idx_pe)
                    u_cant = d3.number_input("Cantidad *", min_value=1, value=int(reg_dp["Cantidad"]), step=1)
                    u_np = d4.text_input("Nombre_Producto *", value=str(reg_dp["Nombre_Producto"]), max_chars=100)

                    if st.form_submit_button("🔄 Actualizar Detalle de Pedido", type="primary"):
                        if not u_np.strip():
                            st.error("El nombre del producto no puede quedar vacío.")
                        else:
                            ped_row = mapa_ped_info[u_ped_sel]
                            try:
                                ejecutar_dml(
                                    """
                                    UPDATE DETALLE_PEDIDO
                                    SET Cantidad = :c, Nombre_Producto = :np, ID_Proveedor = :idp, ID_Pedido = :idped
                                    WHERE ID_Detalle = :idd
                                    """,
                                    {
                                        "c": int(u_cant),
                                        "np": u_np.strip(),
                                        "idp": int(ped_row["ID_Proveedor"]),
                                        "idped": int(ped_row["ID_Pedido"]),
                                        "idd": int(reg_dp["ID_Detalle"]),
                                    },
                                )
                                st.success(f"✅ Detalle #{reg_dp['ID_Detalle']} actualizado.")
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "DETALLE_PEDIDO"))

        elif op_dp == "🗑️ Eliminar (Delete)":
            if df_dp.empty:
                st.warning("No hay detalles de pedido para eliminar.")
            else:
                opc_dp = {
                    f"Detalle #{r['ID_Detalle']} — Pedido #{r['ID_Pedido']}: {r['Nombre_Producto']} (Cant: {r['Cantidad']})": r
                    for _, r in df_dp.iterrows()
                }
                sel_dp = st.selectbox("Selecciona el detalle a eliminar:", list(opc_dp.keys()), key="del_dped_sel")
                reg_dp = opc_dp[sel_dp]
                st.warning(
                    f"**Resumen de eliminación:** `ID_Detalle = {reg_dp['ID_Detalle']}` | Pedido #{reg_dp['ID_Pedido']} | "
                    f"Producto: **{reg_dp['Nombre_Producto']}** | Cantidad: {reg_dp['Cantidad']}"
                )
                conf_dp = st.checkbox("Confirmo que deseo eliminar esta línea de detalle.", key="conf_del_dped")
                if st.button("🗑️ Eliminar Detalle de Pedido", type="primary", disabled=not conf_dp):
                    try:
                        ejecutar_dml(
                            "DELETE FROM DETALLE_PEDIDO WHERE ID_Detalle = :id", {"id": int(reg_dp["ID_Detalle"])}
                        )
                        st.success(f"✅ Detalle #{reg_dp['ID_Detalle']} eliminado.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "DETALLE_PEDIDO"))

    # ------------------------------------------------------------------
    # 3D. COMPROBANTE
    # ------------------------------------------------------------------
    with t_comp:
        df_comp = consultar_df(
            """
            SELECT c.Num_de_OP, c.Fecha, c.ID_Pedido,
                   pe.Total AS Monto_Pedido,
                   CONCAT_WS(' ', pr.Nombre, pr.Apellido_Paterno) AS Proveedor
            FROM COMPROBANTE c
            LEFT JOIN PEDIDO pe ON pe.ID_Pedido = c.ID_Pedido
            LEFT JOIN PROVEEDOR pr ON pr.ID_Proveedor = pe.ID_Proveedor
            ORDER BY c.ID_Pedido, c.Num_de_OP
            """
        )
        st.subheader("Consultar Comprobantes de Pedido (Read)")
        st.dataframe(filtrar_y_ordenar_df(df_comp, "comp"), use_container_width=True, hide_index=True)

        st.divider()
        op_co = st.radio(
            "Operación en COMPROBANTE:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_comp",
        )

        if op_co == "➕ Ingresar (Create)":
            # Regla de negocio: Un pedido genera un único comprobante
            pedidos_sin_comp = consultar_df(
                """
                SELECT pe.ID_Pedido, pe.Fecha, pe.Total,
                       CONCAT_WS(' ', pr.Nombre, pr.Apellido_Paterno) AS Proveedor
                FROM PEDIDO pe
                JOIN PROVEEDOR pr ON pr.ID_Proveedor = pe.ID_Proveedor
                LEFT JOIN COMPROBANTE c ON c.ID_Pedido = pe.ID_Pedido
                WHERE c.Num_de_OP IS NULL
                ORDER BY pe.ID_Pedido
                """
            )
            if pedidos_sin_comp.empty:
                st.info(
                    "ℹ️ Todos los pedidos actuales ya cuentan con su comprobante único registrado. Crea un nuevo pedido o elimina el comprobante de alguno para registrar otro."
                )
            else:
                mapa_sin_comp = {
                    f"Pedido #{r['ID_Pedido']} ({r['Fecha']} — {r['Proveedor']} | S/ {r['Total']:.2f})": int(
                        r["ID_Pedido"]
                    )
                    for _, r in pedidos_sin_comp.iterrows()
                }
                with st.form("form_create_comp"):
                    c1, c2, c3 = st.columns(3)
                    num_op = c1.text_input("Num_de_OP (Clave Primaria, ej. 00521480) *", max_chars=50)
                    fec_co = c2.date_input("Fecha del Comprobante *", value=date.today())
                    ped_co = c3.selectbox("Pedido sin Comprobante (Relación 1 a 1) *", list(mapa_sin_comp.keys()))

                    if st.form_submit_button("💾 Guardar Comprobante", type="primary"):
                        if not num_op.strip():
                            st.error("El número de operación (Num_de_OP) es obligatorio.")
                        else:
                            try:
                                ejecutar_dml(
                                    "INSERT INTO COMPROBANTE (Num_de_OP, Fecha, ID_Pedido) VALUES (:op, :f, :idp)",
                                    {"op": num_op.strip(), "f": fec_co, "idp": mapa_sin_comp[ped_co]},
                                )
                                st.success(f"✅ Comprobante '{num_op.strip()}' registrado.")
                                st.rerun()
                            except Exception as e:
                                st.error(traducir_error_bd(e, "COMPROBANTE"))

        elif op_co == "✏️ Actualizar (Update)":
            if df_comp.empty:
                st.warning("No hay comprobantes para actualizar.")
            else:
                opc_co = {
                    f"OP: {r['Num_de_OP']} — Pedido #{r['ID_Pedido']} ({r['Fecha']})": r for _, r in df_comp.iterrows()
                }
                sel_co = st.selectbox("Selecciona el comprobante a editar:", list(opc_co.keys()), key="upd_comp_sel")
                reg_co = opc_co[sel_co]

                with st.form("form_update_comp"):
                    c1, c2, c3 = st.columns(3)
                    c1.text_input("Num_de_OP (PK Bloqueada)", value=str(reg_co["Num_de_OP"]), disabled=True)
                    u_fco = c2.date_input("Fecha *", value=pd.to_datetime(reg_co["Fecha"]).date())
                    c3.text_input("ID_Pedido Asociado (Relación 1:1)", value=str(reg_co["ID_Pedido"]), disabled=True)

                    if st.form_submit_button("🔄 Actualizar Fecha de Comprobante", type="primary"):
                        try:
                            ejecutar_dml(
                                "UPDATE COMPROBANTE SET Fecha = :f WHERE Num_de_OP = :op",
                                {"f": u_fco, "op": str(reg_co["Num_de_OP"])},
                            )
                            st.success(f"✅ Comprobante '{reg_co['Num_de_OP']}' actualizado.")
                            st.rerun()
                        except Exception as e:
                            st.error(traducir_error_bd(e, "COMPROBANTE"))

        elif op_co == "🗑️ Eliminar (Delete)":
            if df_comp.empty:
                st.warning("No hay comprobantes para eliminar.")
            else:
                opc_co = {
                    f"OP: {r['Num_de_OP']} — Pedido #{r['ID_Pedido']} ({r['Proveedor']})": r
                    for _, r in df_comp.iterrows()
                }
                sel_co = st.selectbox("Selecciona el comprobante a eliminar:", list(opc_co.keys()), key="del_comp_sel")
                reg_co = opc_co[sel_co]
                st.warning(
                    f"**Resumen de eliminación:** Comprobante `Num_de_OP = {reg_co['Num_de_OP']}` | "
                    f"Pedido #{reg_co['ID_Pedido']} | Fecha: {reg_co['Fecha']}"
                )
                conf_co = st.checkbox("Confirmo que deseo eliminar este comprobante.", key="conf_del_comp")
                if st.button("🗑️ Eliminar Comprobante", type="primary", disabled=not conf_co):
                    try:
                        ejecutar_dml(
                            "DELETE FROM COMPROBANTE WHERE Num_de_OP = :op", {"op": str(reg_co["Num_de_OP"])}
                        )
                        st.success(f"✅ Comprobante '{reg_co['Num_de_OP']}' eliminado.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "COMPROBANTE"))


# ==============================================================================
# MÓDULO 4: VENTAS (VENTA, DETALLE_VENTA)
# ==============================================================================
elif modulo_activo.startswith("🧾 4."):
    st.title("🧾 Módulo Ventas (Cabecera y Detalle)")
    st.markdown(
        '<span class="badge-rn">RN-01 / RN-03 / RN-07: Precio_Unitario queda fijado en el detalle</span>'
        '<span class="badge-rn">Subtotal y Total son atributos derivados: se calculan en pantalla y no se digitan</span>'
        '<span class="badge-rn">No se descuenta stock automáticamente (se ajusta en Catálogo)</span>',
        unsafe_allow_html=True,
    )

    t_ven, t_dven = st.tabs(["🧾 1. Cabecera VENTA", "🛒 2. Líneas DETALLE_VENTA"])

    df_cli_fk = consultar_df(
        "SELECT ID_Cliente, CONCAT_WS(' ', Nombre, Apellido_Paterno, Apellido_Materno) AS Nom, Porcentaje_Descuento FROM CLIENTE ORDER BY ID_Cliente"
    )
    df_emp_vfk = consultar_df(
        "SELECT ID_Empleado, CONCAT_WS(' ', Nombre, Apellido_Paterno, Apellido_Materno) AS Nom FROM EMPLEADO ORDER BY ID_Empleado"
    )
    mapa_cli_fk = {
        f"{r['ID_Cliente']} — {r['Nom']} (Dscto: {r['Porcentaje_Descuento']}%)": int(r["ID_Cliente"])
        for _, r in df_cli_fk.iterrows()
    }
    mapa_emp_vfk = {f"{r['ID_Empleado']} — {r['Nom']}": int(r["ID_Empleado"]) for _, r in df_emp_vfk.iterrows()}

    # ------------------------------------------------------------------
    # 4A. TABLA VENTA
    # ------------------------------------------------------------------
    with t_ven:
        df_ven = consultar_df(
            """
            SELECT v.ID_Venta, v.Fecha, v.Metodo_Pago, v.Tipo_Comprobante, v.Total,
                   v.ID_Cliente, CONCAT_WS(' ', c.Nombre, c.Apellido_Paterno) AS Cliente,
                   v.ID_Empleado, CONCAT_WS(' ', e.Nombre, e.Apellido_Paterno) AS Empleado,
                   (SELECT COUNT(*) FROM DETALLE_VENTA dv WHERE dv.ID_Venta = v.ID_Venta) AS Items_Detalle
            FROM VENTA v
            LEFT JOIN CLIENTE c ON c.ID_Cliente = v.ID_Cliente
            LEFT JOIN EMPLEADO e ON e.ID_Empleado = v.ID_Empleado
            ORDER BY v.ID_Venta
            """
        )
        st.subheader("Consultar Cabeceras de Venta (Read)")
        st.dataframe(filtrar_y_ordenar_df(df_ven, "ven"), use_container_width=True, hide_index=True)

        st.divider()
        op_v = st.radio(
            "Operación en VENTA:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_ven",
        )

        metodos_pago = ["Efectivo", "Yape", "Plin", "Tarjeta de débito", "Tarjeta de crédito", "Transferencia"]
        tipos_comp = ["Boleta", "Factura"]

        if op_v == "➕ Ingresar (Create)":
            sig_v = siguiente_id("VENTA", "ID_Venta")
            with st.form("form_create_ven"):
                st.caption(
                    "📌 `Total` es un atributo derivado en el MER: inicia en S/ 0.00 (no se digita) y se calcula automáticamente al registrar o modificar sus líneas en `DETALLE_VENTA`."
                )
                v1, v2, v3 = st.columns(3)
                id_v = v1.number_input("ID_Venta (máx + 1) *", min_value=1, value=sig_v, step=1)
                fec_v = v2.date_input("Fecha *", value=date.today())
                mp_v = v3.selectbox("Metodo_Pago *", metodos_pago)

                v4, v5, v6 = st.columns(3)
                tc_v = v4.selectbox("Tipo_Comprobante *", tipos_comp)
                cli_v = v5.selectbox("Cliente (FK) *", list(mapa_cli_fk.keys()))
                emp_v = v6.selectbox("Empleado (FK) *", list(mapa_emp_vfk.keys()))

                st.text_input("Total Calculado (Atributo derivado - Bloqueado)", value="S/ 0.00", disabled=True)

                if st.form_submit_button("💾 Crear Cabecera de Venta", type="primary"):
                    try:
                        ejecutar_dml(
                            """
                            INSERT INTO VENTA (ID_Venta, Fecha, Metodo_Pago, Tipo_Comprobante, Total, ID_Empleado, ID_Cliente)
                            VALUES (:idv, :f, :mp, :tc, 0.00, :ide, :idc)
                            """,
                            {
                                "idv": int(id_v),
                                "f": fec_v,
                                "mp": mp_v,
                                "tc": tc_v,
                                "ide": mapa_emp_vfk[emp_v],
                                "idc": mapa_cli_fk[cli_v],
                            },
                        )
                        st.success(
                            f"✅ Venta #{id_v} creada. Ahora agrega sus productos en la pestaña '2. Líneas DETALLE_VENTA'."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "VENTA"))

        elif op_v == "✏️ Actualizar (Update)":
            if df_ven.empty:
                st.warning("No hay ventas para actualizar.")
            else:
                opc_v = {
                    f"Venta #{r['ID_Venta']} — {r['Fecha']} ({r['Cliente']} | Total: S/ {r['Total']:.2f})": r
                    for _, r in df_ven.iterrows()
                }
                sel_v = st.selectbox("Selecciona la venta a editar:", list(opc_v.keys()), key="upd_ven_sel")
                reg_v = opc_v[sel_v]

                keys_c = list(mapa_cli_fk.keys())
                idx_c = next((i for i, k in enumerate(keys_c) if mapa_cli_fk[k] == reg_v["ID_Cliente"]), 0)
                keys_e = list(mapa_emp_vfk.keys())
                idx_e = next((i for i, k in enumerate(keys_e) if mapa_emp_vfk[k] == reg_v["ID_Empleado"]), 0)
                idx_mp = metodos_pago.index(reg_v["Metodo_Pago"]) if reg_v["Metodo_Pago"] in metodos_pago else 0
                idx_tc = tipos_comp.index(reg_v["Tipo_Comprobante"]) if reg_v["Tipo_Comprobante"] in tipos_comp else 0

                with st.form("form_update_ven"):
                    v1, v2, v3 = st.columns(3)
                    v1.text_input("ID_Venta (PK Bloqueada)", value=str(reg_v["ID_Venta"]), disabled=True)
                    u_fv = v2.date_input("Fecha *", value=pd.to_datetime(reg_v["Fecha"]).date())
                    u_mp = v3.selectbox("Metodo_Pago *", metodos_pago, index=idx_mp)

                    v4, v5, v6 = st.columns(3)
                    u_tc = v4.selectbox("Tipo_Comprobante *", tipos_comp, index=idx_tc)
                    u_cli = v5.selectbox("Cliente (FK) *", keys_c, index=idx_c)
                    u_emp = v6.selectbox("Empleado (FK) *", keys_e, index=idx_e)

                    st.text_input(
                        "Total Derivado (Calculado desde DETALLE_VENTA - No editable)",
                        value=f"S/ {float(reg_v['Total']):,.2f}",
                        disabled=True,
                    )

                    if st.form_submit_button("🔄 Guardar Cambios en Venta", type="primary"):
                        try:
                            ejecutar_dml(
                                """
                                UPDATE VENTA
                                SET Fecha = :f, Metodo_Pago = :mp, Tipo_Comprobante = :tc,
                                    ID_Empleado = :ide, ID_Cliente = :idc
                                WHERE ID_Venta = :idv
                                """,
                                {
                                    "f": u_fv,
                                    "mp": u_mp,
                                    "tc": u_tc,
                                    "ide": mapa_emp_vfk[u_emp],
                                    "idc": mapa_cli_fk[u_cli],
                                    "idv": int(reg_v["ID_Venta"]),
                                },
                            )
                            recalcular_total_venta(int(reg_v["ID_Venta"]))
                            st.success(f"✅ Venta #{reg_v['ID_Venta']} actualizada.")
                            st.rerun()
                        except Exception as e:
                            st.error(traducir_error_bd(e, "VENTA"))

        elif op_v == "🗑️ Eliminar (Delete)":
            if df_ven.empty:
                st.warning("No hay ventas para eliminar.")
            else:
                opc_v = {
                    f"Venta #{r['ID_Venta']} — {r['Fecha']} ({r['Cliente']} | Ítems: {r['Items_Detalle']} | Total: S/ {r['Total']:.2f})": r
                    for _, r in df_ven.iterrows()
                }
                sel_v = st.selectbox("Selecciona la venta a eliminar:", list(opc_v.keys()), key="del_ven_sel")
                reg_v = opc_v[sel_v]
                st.warning(
                    f"**Resumen de eliminación:** Venta `ID_Venta = {reg_v['ID_Venta']}` | Fecha: {reg_v['Fecha']} | "
                    f"Cliente: **{reg_v['Cliente']}** | Líneas en DETALLE_VENTA: **{reg_v['Items_Detalle']}** | Total: S/ {reg_v['Total']:.2f}"
                )
                conf_v = st.checkbox("Confirmo que deseo eliminar esta cabecera de venta.", key="conf_del_ven")
                if st.button("🗑️ Eliminar Venta", type="primary", disabled=not conf_v):
                    try:
                        ejecutar_dml("DELETE FROM VENTA WHERE ID_Venta = :id", {"id": int(reg_v["ID_Venta"])})
                        st.success(f"✅ Venta #{reg_v['ID_Venta']} eliminada.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "VENTA"))

    # ------------------------------------------------------------------
    # 4B. TABLA DETALLE_VENTA
    # ------------------------------------------------------------------
    with t_dven:
        df_dv = consultar_df(
            """
            SELECT dv.ID_Venta, v.Fecha, dv.ID_Producto, p.Nombre AS Producto,
                   dv.Cantidad, p.Precio_Venta AS Precio_Catalogo_Hoy,
                   dv.Precio_Unitario AS Precio_Unitario_Fijado, dv.Subtotal
            FROM DETALLE_VENTA dv
            JOIN VENTA v ON v.ID_Venta = dv.ID_Venta
            JOIN PRODUCTO p ON p.ID_Producto = dv.ID_Producto
            ORDER BY dv.ID_Venta DESC, dv.ID_Producto
            """
        )
        st.subheader("Consultar Líneas de Detalle de Venta (Read)")
        st.dataframe(filtrar_y_ordenar_df(df_dv, "dven"), use_container_width=True, hide_index=True)

        st.divider()
        op_dv = st.radio(
            "Operación en DETALLE_VENTA:",
            ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
            horizontal=True,
            key="op_dven",
        )

        df_ventas_disp = consultar_df(
            """
            SELECT v.ID_Venta, v.Fecha, CONCAT_WS(' ', c.Nombre, c.Apellido_Paterno) AS Cliente
            FROM VENTA v
            LEFT JOIN CLIENTE c ON c.ID_Cliente = v.ID_Cliente
            ORDER BY v.ID_Venta DESC
            """
        )
        df_prods_disp = consultar_df(
            "SELECT ID_Producto, Nombre, Precio_Venta, Stock FROM PRODUCTO ORDER BY ID_Producto"
        )

        if op_dv == "➕ Ingresar (Create)":
            if df_ventas_disp.empty or df_prods_disp.empty:
                st.warning("Debes contar con registros en VENTA y en PRODUCTO.")
            else:
                st.caption(
                    "📌 **Atributos derivados y RN-01/03/07:** El `Subtotal` (`Cantidad × Precio_Unitario`) y el `Total` de la cabecera `VENTA` se calculan en pantalla en tiempo real y no se digitan. El stock no se descuenta automáticamente."
                )
                mapa_v = {
                    f"Venta #{r['ID_Venta']} ({r['Fecha']} — {r['Cliente']})": int(r["ID_Venta"])
                    for _, r in df_ventas_disp.iterrows()
                }
                mapa_p = {
                    f"{r['ID_Producto']} — {r['Nombre']} (Catálogo: S/ {r['Precio_Venta']:.2f} | Stock: {r['Stock']})": r
                    for _, r in df_prods_disp.iterrows()
                }

                c1, c2 = st.columns(2)
                v_sel = c1.selectbox("Cabecera de Venta (FK) *", list(mapa_v.keys()), key="create_dv_v")
                p_sel = c2.selectbox("Producto (FK) *", list(mapa_p.keys()), key="create_dv_p")
                prod_row = mapa_p[p_sel]
                precio_cat = float(prod_row["Precio_Venta"])

                c3, c4, c5 = st.columns(3)
                esquema_precio = c3.selectbox(
                    "Esquema de Precio (RN-01 / RN-03 / RN-07)",
                    [
                        f"Precio de catálogo (S/ {precio_cat:.2f})",
                        f"Descuento 10 % — RN-01/RN-03 (S/ {precio_cat * 0.90:.2f})",
                        f"Descuento 30 % — RN-01/RN-03 (S/ {precio_cat * 0.70:.2f})",
                        "Otro precio unitario pactado",
                    ],
                    key="create_dv_esq",
                )
                if "10 %" in esquema_precio:
                    p_def = round(precio_cat * 0.90, 2)
                elif "30 %" in esquema_precio:
                    p_def = round(precio_cat * 0.70, 2)
                else:
                    p_def = round(precio_cat, 2)

                cant_dv = c4.number_input("Cantidad *", min_value=1, value=1, step=1, key="create_dv_cant")
                pu_dv = c5.number_input(
                    "Precio_Unitario Fijado (S/) *",
                    min_value=0.01,
                    value=float(p_def),
                    step=0.10,
                    format="%.2f",
                    key="create_dv_pu",
                )

                subtotal_calc = round(int(cant_dv) * float(pu_dv), 2)
                st.metric("Subtotal Calculado en Pantalla (Cantidad × Precio_Unitario)", f"S/ {subtotal_calc:,.2f}")

                if st.button("💾 Insertar Línea en DETALLE_VENTA", type="primary"):
                    try:
                        id_venta_num = mapa_v[v_sel]
                        ejecutar_dml(
                            """
                            INSERT INTO DETALLE_VENTA (ID_Venta, ID_Producto, Cantidad, Precio_Unitario, Subtotal)
                            VALUES (:idv, :idp, :c, :pu, :sub)
                            """,
                            {
                                "idv": id_venta_num,
                                "idp": int(prod_row["ID_Producto"]),
                                "c": int(cant_dv),
                                "pu": float(pu_dv),
                                "sub": subtotal_calc,
                            },
                        )
                        recalcular_total_venta(id_venta_num)
                        st.success(
                            f"✅ Detalle insertado (Subtotal S/ {subtotal_calc:.2f}) y Total de Venta #{id_venta_num} recalculado."
                        )
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "DETALLE_VENTA"))

        elif op_dv == "✏️ Actualizar (Update)":
            if df_dv.empty:
                st.warning("No hay líneas en DETALLE_VENTA para actualizar.")
            else:
                opc_dv = {
                    f"Venta #{r['ID_Venta']} | Prod #{r['ID_Producto']} ({r['Producto']}) — Cant: {r['Cantidad']} | P.Unit: S/ {r['Precio_Unitario_Fijado']:.2f}": r
                    for _, r in df_dv.iterrows()
                }
                sel_dv = st.selectbox("Selecciona la línea de venta a editar:", list(opc_dv.keys()), key="upd_dv_sel")
                reg_dv = opc_dv[sel_dv]

                u1, u2, u3, u4 = st.columns(4)
                u1.text_input("ID_Venta (PK Compuesta Bloqueada)", value=str(reg_dv["ID_Venta"]), disabled=True)
                u2.text_input(
                    "ID_Producto (PK Compuesta Bloqueada)",
                    value=f"{reg_dv['ID_Producto']} — {reg_dv['Producto']}",
                    disabled=True,
                )
                u_cant = u3.number_input(
                    "Cantidad *", min_value=1, value=int(reg_dv["Cantidad"]), step=1, key="upd_dv_cant"
                )
                u_pu = u4.number_input(
                    "Precio_Unitario Fijado (S/) *",
                    min_value=0.01,
                    value=float(reg_dv["Precio_Unitario_Fijado"]),
                    step=0.10,
                    format="%.2f",
                    key="upd_dv_pu",
                )

                u_subtotal = round(int(u_cant) * float(u_pu), 2)
                st.metric("Nuevo Subtotal Calculado en Pantalla (No editable)", f"S/ {u_subtotal:,.2f}")

                if st.button("🔄 Actualizar Línea y Recalcular Total de Venta", type="primary"):
                    try:
                        id_v_num = int(reg_dv["ID_Venta"])
                        ejecutar_dml(
                            """
                            UPDATE DETALLE_VENTA
                            SET Cantidad = :c, Precio_Unitario = :pu, Subtotal = :sub
                            WHERE ID_Venta = :idv AND ID_Producto = :idp
                            """,
                            {
                                "c": int(u_cant),
                                "pu": float(u_pu),
                                "sub": u_subtotal,
                                "idv": id_v_num,
                                "idp": int(reg_dv["ID_Producto"]),
                            },
                        )
                        recalcular_total_venta(id_v_num)
                        st.success(f"✅ Línea actualizada y Total de Venta #{id_v_num} recalculado.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "DETALLE_VENTA"))

        elif op_dv == "🗑️ Eliminar (Delete)":
            if df_dv.empty:
                st.warning("No hay líneas en DETALLE_VENTA para eliminar.")
            else:
                opc_dv = {
                    f"Venta #{r['ID_Venta']} | Prod #{r['ID_Producto']} ({r['Producto']}) — Subtotal: S/ {r['Subtotal']:.2f}": r
                    for _, r in df_dv.iterrows()
                }
                sel_dv = st.selectbox("Selecciona la línea a eliminar:", list(opc_dv.keys()), key="del_dv_sel")
                reg_dv = opc_dv[sel_dv]
                st.warning(
                    f"**Resumen de eliminación:** `ID_Venta = {reg_dv['ID_Venta']}` + `ID_Producto = {reg_dv['ID_Producto']}` "
                    f"({reg_dv['Producto']}) | Cantidad: {reg_dv['Cantidad']} | Subtotal: S/ {reg_dv['Subtotal']:.2f}"
                )
                conf_dv = st.checkbox("Confirmo que deseo eliminar esta línea de detalle de venta.", key="conf_del_dv")
                if st.button("🗑️ Eliminar Línea de Venta", type="primary", disabled=not conf_dv):
                    try:
                        id_v_num = int(reg_dv["ID_Venta"])
                        ejecutar_dml(
                            "DELETE FROM DETALLE_VENTA WHERE ID_Venta = :idv AND ID_Producto = :idp",
                            {"idv": id_v_num, "idp": int(reg_dv["ID_Producto"])},
                        )
                        recalcular_total_venta(id_v_num)
                        st.success(f"✅ Línea eliminada y Total de Venta #{id_v_num} actualizado.")
                        st.rerun()
                    except Exception as e:
                        st.error(traducir_error_bd(e, "DETALLE_VENTA"))


# ==============================================================================
# MÓDULO 5: MERMAS (MERMA)
# ==============================================================================
elif modulo_activo.startswith("⚠️ 5."):
    st.title("⚠️ Módulo Mermas (CRUD Completo)")
    st.markdown(
        '<span class="badge-rn">RN-06: Registro de Bajas con Empleado Responsable Obligatorio</span>'
        '<span class="badge-rn">Subtotal (Cantidad × Precio) calculado en pantalla</span>',
        unsafe_allow_html=True,
    )

    df_merma = consultar_df(
        """
        SELECT m.ID_Merma, m.Fecha, m.Cantidad, m.Precio, m.Subtotal,
               m.ID_Empleado, CONCAT_WS(' ', e.Nombre, e.Apellido_Paterno, e.Apellido_Materno) AS Empleado_Responsable
        FROM MERMA m
        LEFT JOIN EMPLEADO e ON e.ID_Empleado = m.ID_Empleado
        ORDER BY m.ID_Merma
        """
    )
    df_emp_mfk = consultar_df(
        "SELECT ID_Empleado, CONCAT_WS(' ', Nombre, Apellido_Paterno, Apellido_Materno) AS Nom FROM EMPLEADO ORDER BY ID_Empleado"
    )
    mapa_emp_m = {f"{r['ID_Empleado']} — {r['Nom']}": int(r["ID_Empleado"]) for _, r in df_emp_mfk.iterrows()}

    st.subheader("Consultar Mermas (Read)")
    st.dataframe(filtrar_y_ordenar_df(df_merma, "merma"), use_container_width=True, hide_index=True)

    st.divider()
    op_m = st.radio(
        "Operación en MERMA:",
        ["➕ Ingresar (Create)", "✏️ Actualizar (Update)", "🗑️ Eliminar (Delete)"],
        horizontal=True,
        key="op_merma",
    )

    if op_m == "➕ Ingresar (Create)":
        if not mapa_emp_m:
            st.warning("Se requiere al menos un empleado en la tabla EMPLEADO.")
        else:
            sig_m = siguiente_id("MERMA", "ID_Merma")
            m1, m2, m3, m4, m5 = st.columns(5)
            id_m = m1.number_input("ID_Merma (máx + 1) *", min_value=1, value=sig_m, step=1, key="cr_m_id")
            fec_m = m2.date_input("Fecha *", value=date.today(), key="cr_m_fec")
            cant_m = m3.number_input("Cantidad *", min_value=1, value=1, step=1, key="cr_m_cant")
            prec_m = m4.number_input(
                "Precio Unitario (S/) *", min_value=0.01, value=5.00, step=0.10, format="%.2f", key="cr_m_prec"
            )
            emp_m = m5.selectbox("Empleado Responsable (Obligatorio) *", list(mapa_emp_m.keys()), key="cr_m_emp")

            sub_m = round(int(cant_m) * float(prec_m), 2)
            st.metric("Subtotal Calculado en Pantalla (Cantidad × Precio)", f"S/ {sub_m:,.2f}")

            if st.button("💾 Registrar Merma", type="primary"):
                try:
                    ejecutar_dml(
                        """
                        INSERT INTO MERMA (ID_Merma, Fecha, Cantidad, Precio, Subtotal, ID_Empleado)
                        VALUES (:id, :f, :c, :p, :sub, :ide)
                        """,
                        {
                            "id": int(id_m),
                            "f": fec_m,
                            "c": int(cant_m),
                            "p": float(prec_m),
                            "sub": sub_m,
                            "ide": mapa_emp_m[emp_m],
                        },
                    )
                    st.success(f"✅ Merma #{id_m} registrada con Subtotal S/ {sub_m:.2f}.")
                    st.rerun()
                except Exception as e:
                    st.error(traducir_error_bd(e, "MERMA"))

    elif op_m == "✏️ Actualizar (Update)":
        if df_merma.empty:
            st.warning("No hay registros de merma para actualizar.")
        else:
            opc_m = {
                f"Merma #{r['ID_Merma']} — {r['Fecha']} (Cant: {r['Cantidad']} | Subtotal: S/ {r['Subtotal']:.2f} | Resp: {r['Empleado_Responsable']})": r
                for _, r in df_merma.iterrows()
            }
            sel_m = st.selectbox("Selecciona la merma a editar:", list(opc_m.keys()), key="upd_m_sel")
            reg_m = opc_m[sel_m]

            keys_em = list(mapa_emp_m.keys())
            idx_em = next((i for i, k in enumerate(keys_em) if mapa_emp_m[k] == reg_m["ID_Empleado"]), 0)

            u1, u2, u3, u4, u5 = st.columns(5)
            u1.text_input("ID_Merma (PK Bloqueada)", value=str(reg_m["ID_Merma"]), disabled=True)
            u_fm = u2.date_input("Fecha *", value=pd.to_datetime(reg_m["Fecha"]).date(), key="upd_m_fec")
            u_cm = u3.number_input("Cantidad *", min_value=1, value=int(reg_m["Cantidad"]), step=1, key="upd_m_cant")
            u_pm = u4.number_input(
                "Precio Unitario (S/) *",
                min_value=0.01,
                value=float(reg_m["Precio"]),
                step=0.10,
                format="%.2f",
                key="upd_m_prec",
            )
            u_em = u5.selectbox("Empleado Responsable *", keys_em, index=idx_em, key="upd_m_emp")

            u_sub_m = round(int(u_cm) * float(u_pm), 2)
            st.metric("Nuevo Subtotal Calculado en Pantalla (No editable)", f"S/ {u_sub_m:,.2f}")

            if st.button("🔄 Actualizar Merma", type="primary"):
                try:
                    ejecutar_dml(
                        """
                        UPDATE MERMA
                        SET Fecha = :f, Cantidad = :c, Precio = :p, Subtotal = :sub, ID_Empleado = :ide
                        WHERE ID_Merma = :id
                        """,
                        {
                            "f": u_fm,
                            "c": int(u_cm),
                            "p": float(u_pm),
                            "sub": u_sub_m,
                            "ide": mapa_emp_m[u_em],
                            "id": int(reg_m["ID_Merma"]),
                        },
                    )
                    st.success(f"✅ Merma #{reg_m['ID_Merma']} actualizada.")
                    st.rerun()
                except Exception as e:
                    st.error(traducir_error_bd(e, "MERMA"))

    elif op_m == "🗑️ Eliminar (Delete)":
        if df_merma.empty:
            st.warning("No hay mermas para eliminar.")
        else:
            opc_m = {
                f"Merma #{r['ID_Merma']} — {r['Fecha']} (Subtotal: S/ {r['Subtotal']:.2f})": r
                for _, r in df_merma.iterrows()
            }
            sel_m = st.selectbox("Selecciona la merma a eliminar:", list(opc_m.keys()), key="del_m_sel")
            reg_m = opc_m[sel_m]
            st.warning(
                f"**Resumen de eliminación:** Merma `ID_Merma = {reg_m['ID_Merma']}` | Fecha: {reg_m['Fecha']} | "
                f"Cantidad: {reg_m['Cantidad']} | Subtotal: S/ {reg_m['Subtotal']:.2f} | Responsable: **{reg_m['Empleado_Responsable']}**"
            )
            conf_m = st.checkbox("Confirmo que deseo eliminar este registro de merma.", key="conf_del_m")
            if st.button("🗑️ Eliminar Merma", type="primary", disabled=not conf_m):
                try:
                    ejecutar_dml("DELETE FROM MERMA WHERE ID_Merma = :id", {"id": int(reg_m["ID_Merma"])})
                    st.success(f"✅ Merma #{reg_m['ID_Merma']} eliminada.")
                    st.rerun()
                except Exception as e:
                    st.error(traducir_error_bd(e, "MERMA"))


# ==============================================================================
# MÓDULO 6: VERIFICACIÓN DE CONSULTAS Y REGLAS DE NEGOCIO (consultas.sql)
# ==============================================================================
elif modulo_activo.startswith("📊 6."):
    st.title("📊 Verificación de las Reglas del Negocio (`consultas.sql`)")
    st.caption(
        "Consultas analíticas en vivo sobre las vistas de apoyo `VW_LINEA_VENTA` y `VW_INGRESO_PRODUCTO` para comprobar el cumplimiento de RN-01 a RN-07."
    )

    tabs_rn = st.tabs(
        [
            "RN-01: Stock Bajo",
            "RN-02: Ubicación Física",
            "RN-03: Nuevo Ingreso",
            "RN-04: Escala Clientes",
            "RN-05: Reclamo Proveedor",
            "RN-06: Bajas Acumuladas",
            "RN-07: Precio Histórico",
        ]
    )

    with tabs_rn[0]:
        st.subheader("RN-01: Ventas con descuento diferenciado (10 % o 30 %) y alerta de stock bajo")
        umbral = st.slider("Umbral de stock bajo (`@umbral_stock_bajo`):", 1, 20, 5)
        df_rn1 = consultar_df(
            """
            SELECT l.ID_Venta, l.Fecha, l.Producto, l.Stock_Actual,
                   IF(l.Stock_Actual <= :u, 'Sí', 'No') AS Stock_Bajo,
                   l.Cantidad, l.Precio_Catalogo, l.Precio_Cobrado,
                   l.Descuento_Pct, l.Tipo_Descuento AS Descuento_Aplicado
            FROM VW_LINEA_VENTA l
            WHERE l.Tipo_Descuento IN ('10 %', '30 %')
            ORDER BY l.Fecha, l.ID_Venta, l.Producto
            """,
            {"u": umbral},
        )
        st.dataframe(df_rn1, use_container_width=True, hide_index=True)

    with tabs_rn[1]:
        st.subheader("RN-02: Organización física de productos por categoría")
        df_rn2 = consultar_df(
            """
            SELECT c.ID_Categoria, c.Nombre AS Categoria,
                   COUNT(p.ID_Producto) AS Productos,
                   GROUP_CONCAT(DISTINCT NULLIF(TRIM(p.Ubicacion), '') ORDER BY p.Ubicacion SEPARATOR ', ') AS Ubicaciones,
                   SUM(p.Ubicacion IS NULL OR TRIM(p.Ubicacion) = '') AS Sin_Ubicacion
            FROM CATEGORIA c
            LEFT JOIN PRODUCTO p ON p.ID_Categoria = c.ID_Categoria
            GROUP BY c.ID_Categoria, c.Nombre
            ORDER BY c.ID_Categoria
            """
        )
        st.dataframe(df_rn2, use_container_width=True, hide_index=True)

    with tabs_rn[2]:
        st.subheader("RN-03: Ventas de productos de nuevo ingreso dentro del periodo promocional")
        dias_ing = st.slider("Días desde el primer pedido entregado (`@dias_nuevo_ingreso`):", 5, 90, 30)
        df_rn3 = consultar_df(
            """
            SELECT i.Producto, i.Fecha_Ingreso, l.ID_Venta, l.Fecha AS Fecha_Venta,
                   DATEDIFF(l.Fecha, i.Fecha_Ingreso) AS Dias_Desde_Ingreso,
                   l.Cantidad, l.Precio_Catalogo, l.Precio_Cobrado,
                   l.Descuento_Pct, l.Tipo_Descuento
            FROM VW_INGRESO_PRODUCTO i
            JOIN VW_LINEA_VENTA l ON l.ID_Producto = i.ID_Producto
            WHERE l.Fecha >= i.Fecha_Ingreso
              AND DATEDIFF(l.Fecha, i.Fecha_Ingreso) <= :d
            ORDER BY i.Producto, l.Fecha, l.ID_Venta
            """,
            {"d": dias_ing},
        )
        st.dataframe(df_rn3, use_container_width=True, hide_index=True)

    with tabs_rn[3]:
        st.subheader("RN-04: Comparativa de transacciones registradas vs ventas reales y escala de descuento")
        df_rn4 = consultar_df(
            """
            WITH compras AS (
                SELECT ID_Cliente, COUNT(*) AS Compras_Reales, SUM(Total) AS Monto_Total
                FROM VENTA
                GROUP BY ID_Cliente
            )
            SELECT cl.ID_Cliente,
                   CONCAT_WS(' ', cl.Nombre, cl.Apellido_Paterno, cl.Apellido_Materno) AS Cliente,
                   COALESCE(cl.Total_Transacciones, 0) AS Compras_Registradas,
                   COALESCE(co.Compras_Reales, 0) AS Compras_en_VENTA,
                   IF(COALESCE(cl.Total_Transacciones, 0) = COALESCE(co.Compras_Reales, 0), 'Coincide', 'Difiere') AS Conteo,
                   COALESCE(co.Monto_Total, 0) AS Monto_Total,
                   cl.Porcentaje_Descuento AS Dscto_Registrado,
                   CASE WHEN COALESCE(cl.Total_Transacciones, 0) >= 8 THEN 10
                        WHEN COALESCE(cl.Total_Transacciones, 0) >= 5 THEN 5
                        WHEN COALESCE(cl.Total_Transacciones, 0) >= 3 THEN 3
                        ELSE 0
                   END AS Dscto_Segun_Escala
            FROM CLIENTE cl
            LEFT JOIN compras co ON co.ID_Cliente = cl.ID_Cliente
            ORDER BY Compras_Registradas DESC, Monto_Total DESC
            """
        )
        st.dataframe(df_rn4, use_container_width=True, hide_index=True)

    with tabs_rn[4]:
        st.subheader("RN-05: Trazabilidad de pedidos entregados dentro del plazo de reclamo al proveedor")
        dias_rec = st.slider("Plazo de reclamo en días (`@dias_reclamo`):", 10, 90, 30)
        df_rn5 = consultar_df(
            """
            SELECT pe.ID_Pedido, pe.Fecha,
                   DATEDIFF(GREATEST((SELECT MAX(Fecha) FROM VENTA), (SELECT MAX(Fecha) FROM PEDIDO)), pe.Fecha) AS Dias_Transcurridos,
                   :dr - DATEDIFF(GREATEST((SELECT MAX(Fecha) FROM VENTA), (SELECT MAX(Fecha) FROM PEDIDO)), pe.Fecha) AS Dias_Restantes_Reclamo,
                   CONCAT_WS(' ', pr.Nombre, pr.Apellido_Paterno, pr.Apellido_Materno) AS Proveedor,
                   pr.Telefono, COUNT(dp.ID_Detalle) AS Items, SUM(dp.Cantidad) AS Unidades,
                   pe.Total, co.Num_de_OP AS Comprobante
            FROM PEDIDO pe
            JOIN PROVEEDOR pr ON pr.ID_Proveedor = pe.ID_Proveedor
            JOIN DETALLE_PEDIDO dp ON dp.ID_Pedido = pe.ID_Pedido
            LEFT JOIN COMPROBANTE co ON co.ID_Pedido = pe.ID_Pedido
            WHERE pe.Estado = 'Entregado'
              AND DATEDIFF(GREATEST((SELECT MAX(Fecha) FROM VENTA), (SELECT MAX(Fecha) FROM PEDIDO)), pe.Fecha) <= :dr
            GROUP BY pe.ID_Pedido, pe.Fecha, pe.Total, pr.Nombre, pr.Apellido_Paterno, pr.Apellido_Materno, pr.Telefono, co.Num_de_OP
            ORDER BY pe.Fecha DESC
            """,
            {"dr": dias_rec},
        )
        st.dataframe(df_rn5, use_container_width=True, hide_index=True)

    with tabs_rn[5]:
        st.subheader("RN-06: Registro histórico de bajas en MERMA con acumulado de unidades y valor")
        df_rn6 = consultar_df(
            """
            SELECT m.ID_Merma, m.Fecha, m.Cantidad, m.Precio, m.Subtotal,
                   SUM(m.Cantidad) OVER (ORDER BY m.Fecha, m.ID_Merma) AS Unidades_Acumuladas,
                   SUM(m.Subtotal) OVER (ORDER BY m.Fecha, m.ID_Merma) AS Valor_Acumulado,
                   CONCAT_WS(' ', e.Nombre, e.Apellido_Paterno) AS Responsable
            FROM MERMA m
            LEFT JOIN EMPLEADO e ON e.ID_Empleado = m.ID_Empleado
            ORDER BY m.Fecha, m.ID_Merma
            """
        )
        st.dataframe(df_rn6, use_container_width=True, hide_index=True)

    with tabs_rn[6]:
        st.subheader("RN-07: Evolución mensual del precio cobrado vs precio de catálogo vigente")
        df_rn7 = consultar_df(
            """
            SELECT l.Producto, DATE_FORMAT(l.Fecha, '%Y-%m') AS Mes,
                   SUM(l.Cantidad) AS Unidades,
                   MIN(l.Precio_Cobrado) AS Precio_Min_Cobrado,
                   MAX(l.Precio_Cobrado) AS Precio_Max_Cobrado,
                   ROUND(SUM(l.Subtotal) / SUM(l.Cantidad), 2) AS Precio_Promedio_Cobrado,
                   MAX(l.Precio_Catalogo) AS Precio_Catalogo_Actual
            FROM VW_LINEA_VENTA l
            GROUP BY l.ID_Producto, l.Producto, DATE_FORMAT(l.Fecha, '%Y-%m')
            ORDER BY l.Producto, Mes
            """
        )
        st.dataframe(df_rn7, use_container_width=True, hide_index=True)