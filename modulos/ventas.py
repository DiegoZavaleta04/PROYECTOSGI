import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# CONFIGURACION (AJUSTAR SI HACE FALTA)
# ==============================
CLAVE_USUARIO = "usuario"   # en tu sesion guarda el correo
CLAVE_SEDE = "id_sede"
CLAVE_ROL = "id_rol"

# REVISA que coincida con el id del rol Administrador en phpMyAdmin
ID_ROL_ADMINISTRADOR = 5

# Nombres de las tablas EXACTAMENTE como aparecen en phpMyAdmin
# (importan las mayusculas y minusculas)
T_USUARIO = "USUARIO"
T_SEDE = "Sede"
T_CLIENTE = "CLIENTE"
T_PRODUCTOS = "PRODUCTOS"
T_UNIDAD = "UNIDAD_MEDIDA"
T_VENTAS = "VENTAS"
T_DETALLE_VENTA = "DETALLE_VENTA"


# ==============================
# FUNCIONES DE BASE DE DATOS
# ==============================
def consultar(consulta, parametros=()):
    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return []

        cursor = conexion.cursor()
        cursor.execute(consulta, parametros)

        return cursor.fetchall()

    except Exception as error:
        st.error(
            f"Error al consultar los datos: {error}"
        )
        return []

    finally:
        if cursor is not None:
            cursor.close()

        if (
            conexion is not None
            and conexion.is_connected()
        ):
            conexion.close()


def obtener_usuario(correo):
    filas = consultar(
        f"""
        SELECT Id_usuario, Nombre, Apellido
        FROM {T_USUARIO}
        WHERE Correo = %s
        LIMIT 1
        """,
        (correo,)
    )
    return filas[0] if filas else None


def obtener_nombre_sede(id_sede):
    filas = consultar(
        f"SELECT nombre FROM {T_SEDE} WHERE id_sede = %s",
        (id_sede,)
    )
    return filas[0][0] if filas else ""


def obtener_clientes(id_sede):
    return consultar(
        f"""
        SELECT Id_cliente, Nombre
        FROM {T_CLIENTE}
        WHERE Id_sede = %s
        ORDER BY Nombre
        """,
        (id_sede,)
    )


def obtener_productos():
    return consultar(
        f"""
        SELECT
            p.Id_producto,
            p.Nombre,
            u.Abreviatura,
            p.Id_unidad
        FROM {T_PRODUCTOS} p
        INNER JOIN {T_UNIDAD} u
            ON p.Id_unidad = u.Id_unidad
        ORDER BY p.Nombre
        """
    )


def obtener_ventas_recientes(id_sede):
    return consultar(
        f"""
        SELECT
            v.Id_venta,
            v.Fecha,
            c.Nombre,
            CONCAT(u.Nombre, ' ', u.Apellido),
            COALESCE(SUM(d.Cantidad * d.Precio_venta), 0)
        FROM {T_VENTAS} v
        INNER JOIN {T_CLIENTE} c
            ON v.Id_cliente = c.Id_cliente
        INNER JOIN {T_USUARIO} u
            ON v.Id_usuario = u.Id_usuario
        LEFT JOIN {T_DETALLE_VENTA} d
            ON d.Id_venta = v.Id_venta
        WHERE v.Id_sede = %s
        GROUP BY v.Id_venta, v.Fecha, c.Nombre, u.Nombre, u.Apellido
        ORDER BY v.Id_venta DESC
        LIMIT 20
        """,
        (id_sede,)
    )


def registrar_venta(fecha, id_usuario, id_sede, id_cliente, lineas):
    """
    Guarda la venta y su detalle en una sola transaccion:
    si algo falla, no se guarda nada.
    Devuelve el Id de la venta, o None si hubo error.
    """
    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return None

        cursor = conexion.cursor()

        cursor.execute(
            f"""
            INSERT INTO {T_VENTAS} (Fecha, Id_usuario, Id_sede, Id_cliente)
            VALUES (%s, %s, %s, %s)
            """,
            (fecha, id_usuario, id_sede, id_cliente)
        )

        id_venta = cursor.lastrowid

        cursor.executemany(
            f"""
            INSERT INTO {T_DETALLE_VENTA}
            (Id_venta, Id_producto, Cantidad, Id_unidad, Precio_venta)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (
                    id_venta,
                    l["id_producto"],
                    l["cantidad"],
                    l["id_unidad"],
                    l["precio"]
                )
                for l in lineas
            ]
        )

        conexion.commit()
        return id_venta

    except Exception as error:
        if conexion is not None:
            conexion.rollback()

        st.error(
            f"Error al registrar la venta: {error}"
        )
        return None

    finally:
        if cursor is not None:
            cursor.close()

        if (
            conexion is not None
            and conexion.is_connected()
        ):
            conexion.close()


# ==============================
# PANTALLA DEL MODULO
# ==============================
def mostrar_venta():
    st.header("Registrar nueva venta")

    # ---- Permisos ----
    id_rol = st.session_state.get(CLAVE_ROL)
    id_sede = st.session_state.get(CLAVE_SEDE)
    correo = st.session_state.get(CLAVE_USUARIO)

    if id_rol == ID_ROL_ADMINISTRADOR:
        st.warning(
            "El administrador no puede registrar ventas."
        )
        return

    if id_sede is None or correo is None:
        st.error(
            "No se encontró la sede o el usuario de la sesión."
        )
        return

    usuario = obtener_usuario(correo)

    if usuario is None:
        st.error(
            "No se encontró el usuario en la base de datos."
        )
        return

    id_usuario = usuario[0]
    nombre_vendedor = f"{usuario[1]} {usuario[2]}"
    nombre_sede = obtener_nombre_sede(id_sede)

    # Mensaje guardado antes de recargar la pagina
    mensaje = st.session_state.pop("mensaje_venta", None)
    if mensaje:
        st.success(mensaje)

    if "lineas_venta" not in st.session_state:
        st.session_state["lineas_venta"] = []

    clientes = obtener_clientes(id_sede)
    productos = obtener_productos()

    if not clientes:
        st.warning(
            "Esta sede no tiene clientes registrados. "
            "Registre un cliente antes de vender."
        )
        return

    if not productos:
        st.warning(
            "No hay productos registrados."
        )
        return

    # -----------------------------------
    # DATOS DE LA VENTA
    # -----------------------------------
    col1, col2 = st.columns(2)

    with col1:
        cliente = st.selectbox(
            "Cliente",
            clientes,
            format_func=lambda c: c[1]
        )

    with col2:
        st.text_input(
            "Sede",
            value=nombre_sede,
            disabled=True
        )

    col3, col4 = st.columns(2)

    with col3:
        fecha = st.date_input("Fecha de la venta")

    with col4:
        st.text_input(
            "Vendedor",
            value=nombre_vendedor,
            disabled=True
        )

    # -----------------------------------
    # PRODUCTOS DE LA VENTA
    # -----------------------------------
    st.subheader("Productos de la venta")

    colp, colc, colpr = st.columns([3, 1, 1])

    with colp:
        producto = st.selectbox(
            "Producto",
            productos,
            format_func=lambda p: f"{p[0]} - {p[1]} ({p[2]})"
        )

    with colc:
        cantidad = st.number_input(
            "Cantidad",
            min_value=0.0,
            step=1.0,
            format="%.2f"
        )

    with colpr:
        precio = st.number_input(
            "Precio unitario ($)",
            min_value=0.0,
            step=0.05,
            format="%.2f"
        )

    if st.button("Agregar al detalle"):
        if cantidad <= 0:
            st.warning("La cantidad debe ser mayor que 0.")
        elif precio <= 0:
            st.warning("El precio debe ser mayor que 0.")
        else:
            lineas = st.session_state["lineas_venta"]

            # Un producto no puede repetirse en la misma venta
            # (la llave de Detalle_venta es Id_venta + Id_producto),
            # asi que si ya existe se suma la cantidad.
            existente = next(
                (l for l in lineas if l["id_producto"] == producto[0]),
                None
            )

            if existente:
                existente["cantidad"] += cantidad
                existente["precio"] = precio
            else:
                lineas.append({
                    "id_producto": producto[0],
                    "producto": producto[1],
                    "abreviatura": producto[2],
                    "id_unidad": producto[3],
                    "cantidad": cantidad,
                    "precio": precio
                })

            st.rerun()

    lineas = st.session_state["lineas_venta"]

    # -----------------------------------
    # DETALLE Y TOTAL
    # -----------------------------------
    if lineas:
        tabla = pd.DataFrame(
            [
                (
                    l["producto"],
                    l["abreviatura"],
                    l["cantidad"],
                    l["precio"],
                    round(l["cantidad"] * l["precio"], 2)
                )
                for l in lineas
            ],
            columns=[
                "Producto",
                "Unidad",
                "Cantidad",
                "Precio unitario ($)",
                "Subtotal ($)"
            ]
        )

        st.dataframe(
            tabla,
            use_container_width=True,
            hide_index=True
        )

        total = round(
            sum(l["cantidad"] * l["precio"] for l in lineas),
            2
        )

        st.metric("Total de la venta", f"${total:,.2f}")

        cb1, cb2, _ = st.columns([1, 1, 3])

        with cb1:
            if st.button("Quitar último"):
                lineas.pop()
                st.rerun()

        with cb2:
            if st.button("Vaciar detalle"):
                st.session_state["lineas_venta"] = []
                st.rerun()
    else:
        st.info("Aún no hay productos en el detalle.")

    # -----------------------------------
    # REGISTRAR
    # -----------------------------------
    if st.button("Registrar venta"):
        if not lineas:
            st.warning(
                "Agregue al menos un producto al detalle."
            )
        else:
            id_venta = registrar_venta(
                fecha,
                id_usuario,
                id_sede,       # siempre la sede del usuario
                cliente[0],
                lineas
            )

            if id_venta:
                total = round(
                    sum(l["cantidad"] * l["precio"] for l in lineas),
                    2
                )
                st.session_state["lineas_venta"] = []
                st.session_state["mensaje_venta"] = (
                    f"Venta #{id_venta} registrada correctamente. "
                    f"Total: ${total:,.2f}"
                )
                st.rerun()

    st.divider()

    # -----------------------------------
    # VENTAS RECIENTES DE LA SEDE
    # -----------------------------------
    st.subheader("Ventas recientes de la sede")

    ventas = obtener_ventas_recientes(id_sede)

    if ventas:
        tabla_ventas = pd.DataFrame(
            [
                (v[0], v[1], v[2], v[3], float(v[4]))
                for v in ventas
            ],
            columns=[
                "ID",
                "Fecha",
                "Cliente",
                "Vendedor",
                "Total ($)"
            ]
        )

        st.dataframe(
            tabla_ventas,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("Aún no hay ventas registradas en esta sede.")
