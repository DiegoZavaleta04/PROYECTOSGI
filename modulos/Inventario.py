from datetime import date, timedelta

import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# PERMISOS
# ==============================
CLAVE_ROL = "id_rol"
CLAVE_SEDE = "id_sede"

# !! REVISA que coincidan con tu tabla Rol (SELECT * FROM Rol;) !!
ROLES_CON_ACCESO = (
    "encargado cd",
    "vendedor cd",
    "encargado tienda",
    "vendedor tienda",
)

# Roles que pueden ver el inventario de TODAS las sedes (vision global
# del Centro de Distribucion). Los demas solo ven el de su propia sede.
# Para que tambien lo vea el vendedor del CD, agreguen "vendedor cd".
ROLES_VEN_TODAS_LAS_SEDES = (
    "encargado cd",
)

# El rol Administrador NO aparece: no tiene acceso al inventario.

TIPOS_MOVIMIENTO = ["Todos", "Entrada", "Salida"]


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
        st.error(f"Error al consultar los datos: {error}")
        return []

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


def obtener_nombre_rol():
    """Devuelve el nombre del rol del usuario (en minusculas), o None."""
    id_rol = st.session_state.get(CLAVE_ROL)

    if id_rol is None:
        return None

    clave = f"_nombre_rol_{id_rol}"

    if clave not in st.session_state:
        filas = consultar(
            "SELECT Nombre FROM Rol WHERE Id_rol = %s",
            (id_rol,)
        )
        st.session_state[clave] = (
            filas[0][0].strip().lower() if filas else None
        )

    return st.session_state[clave]


def obtener_sede_usuario():
    """Devuelve la sede del usuario, o None si no tiene acceso."""
    id_sede = st.session_state.get(CLAVE_SEDE)
    rol = obtener_nombre_rol()

    if rol in ROLES_CON_ACCESO and id_sede is not None:
        return id_sede

    return None


def puede_ver_todas_las_sedes():
    return obtener_nombre_rol() in ROLES_VEN_TODAS_LAS_SEDES


def sede_a_consultar(id_elegida, sede_usuario):
    """
    Seguridad: solo los roles autorizados pueden consultar otra sede o
    todas (None). Cualquier otro rol consulta siempre la suya, aunque
    la pantalla enviara otro valor.
    """
    if puede_ver_todas_las_sedes():
        return id_elegida

    return sede_usuario


# ==============================
# FUNCIONES DE BASE DE DATOS
# ==============================
def obtener_nombre_sede(id_sede):
    filas = consultar(
        "SELECT nombre FROM Sede WHERE id_sede = %s",
        (id_sede,)
    )

    return filas[0][0] if filas else None


def obtener_sedes():
    return consultar(
        "SELECT id_sede, nombre FROM Sede ORDER BY nombre"
    )


def obtener_inventario(id_sede, busqueda=""):
    """
    Existencias de la sede indicada. Con id_sede = None devuelve las de
    todas las sedes (solo para los roles autorizados).
    """
    return consultar(
        """
        SELECT
            p.Id_producto,
            p.Nombre,
            i.Existencia,
            u.Abreviatura,
            s.nombre
        FROM INVENTARIO i
        INNER JOIN PRODUCTOS p
            ON i.Id_producto = p.Id_producto
        INNER JOIN UNIDAD_MEDIDA u
            ON p.Id_unidad = u.Id_unidad
        INNER JOIN Sede s
            ON i.Id_sede = s.id_sede
        WHERE (%s IS NULL OR i.Id_sede = %s)
          AND p.Nombre LIKE %s
        ORDER BY s.nombre, p.Nombre
        """,
        (id_sede, id_sede, f"%{busqueda.strip()}%")
    )


def obtener_movimientos(id_sede, desde, hasta, busqueda="", tipo="Todos"):
    """
    Entradas (compras) y salidas (ventas) de la sede indicada (o de todas
    con id_sede = None), unidas en una sola lista. Las salidas llevan la
    cantidad en negativo.
    """
    return consultar(
        """
        SELECT Fecha, Tipo, Documento, Producto, Cantidad, Unidad,
               Usuario, Sede
        FROM (
            SELECT
                c.Fecha AS Fecha,
                'Entrada' AS Tipo,
                CONCAT('Compra #', c.Id_compra) AS Documento,
                c.Id_compra AS Id_doc,
                p.Nombre AS Producto,
                d.Cantidad AS Cantidad,
                COALESCE(ud.Abreviatura, ub.Abreviatura) AS Unidad,
                CONCAT(u.Nombre, ' ', u.Apellido) AS Usuario,
                sd.nombre AS Sede
            FROM DETALLE_COMPRA d
            INNER JOIN COMPRAS c
                ON d.Id_compra = c.Id_compra
            INNER JOIN PRODUCTOS p
                ON d.Id_producto = p.Id_producto
            INNER JOIN UNIDAD_MEDIDA ub
                ON p.Id_unidad = ub.Id_unidad
            LEFT JOIN UNIDAD_MEDIDA ud
                ON d.Id_unidad = ud.Id_unidad
            INNER JOIN USUARIO u
                ON c.Id_usuario = u.Id_usuario
            INNER JOIN Sede sd
                ON c.Id_sede = sd.id_sede
            WHERE (%s IS NULL OR c.Id_sede = %s)

            UNION ALL

            SELECT
                v.Fecha AS Fecha,
                'Salida' AS Tipo,
                CONCAT('Venta #', v.Id_venta) AS Documento,
                v.Id_venta AS Id_doc,
                p.Nombre AS Producto,
                -d.Cantidad AS Cantidad,
                COALESCE(ud.Abreviatura, ub.Abreviatura) AS Unidad,
                CONCAT(u.Nombre, ' ', u.Apellido) AS Usuario,
                sd.nombre AS Sede
            FROM DETALLE_VENTA d
            INNER JOIN VENTAS v
                ON d.Id_venta = v.Id_venta
            INNER JOIN PRODUCTOS p
                ON d.Id_producto = p.Id_producto
            INNER JOIN UNIDAD_MEDIDA ub
                ON p.Id_unidad = ub.Id_unidad
            LEFT JOIN UNIDAD_MEDIDA ud
                ON d.Id_unidad = ud.Id_unidad
            INNER JOIN USUARIO u
                ON v.Id_usuario = u.Id_usuario
            INNER JOIN Sede sd
                ON v.Id_sede = sd.id_sede
            WHERE (%s IS NULL OR v.Id_sede = %s)
        ) m
        WHERE m.Fecha BETWEEN %s AND %s
          AND m.Producto LIKE %s
          AND (%s = 'Todos' OR m.Tipo = %s)
        ORDER BY m.Fecha DESC, m.Id_doc DESC, m.Producto
        """,
        (
            id_sede,
            id_sede,
            id_sede,
            id_sede,
            desde,
            hasta,
            f"%{busqueda.strip()}%",
            tipo,
            tipo
        )
    )


# ==============================
# PANTALLA DEL MODULO
# ==============================
def elegir_sede(sede_usuario):
    """
    Selector de sede, solo para los roles que ven todas las sedes.
    Devuelve el id elegido (None = todas las sedes).
    """
    sedes = obtener_sedes()

    opciones = [(None, "Todas las sedes")] + [
        (s[0], s[1]) for s in sedes
    ]

    # Al abrir, aparece seleccionada la sede del propio usuario
    indice = next(
        (i for i, o in enumerate(opciones) if o[0] == sede_usuario),
        0
    )

    elegida = st.selectbox(
        "Ver el inventario de",
        opciones,
        index=indice,
        format_func=lambda o: o[1],
        key="inventario_sede_elegida"
    )

    return elegida[0]


def mostrar_existencias(id_sede_consulta):
    busqueda = st.text_input(
        "Buscar producto",
        placeholder="Nombre del producto",
        key="inventario_busqueda"
    )

    filas = obtener_inventario(id_sede_consulta, busqueda)

    if not filas:
        st.info("No se encontraron productos en el inventario.")
        return

    if id_sede_consulta is None:
        # Todas las sedes: se agrega la columna Sede
        tabla = pd.DataFrame(
            [(f[4], f[0], f[1], float(f[2]), f[3]) for f in filas],
            columns=["Sede", "ID", "Producto", "Existencia", "Unidad"]
        )
    else:
        tabla = pd.DataFrame(
            [(f[0], f[1], float(f[2]), f[3]) for f in filas],
            columns=["ID", "Producto", "Existencia", "Unidad"]
        )

    st.dataframe(
        tabla,
        use_container_width=True,
        hide_index=True
    )

    sin_existencia = int((tabla["Existencia"] <= 0).sum())

    st.caption(
        f"Productos: {len(tabla)} | Sin existencia: {sin_existencia}"
    )


def mostrar_movimientos(id_sede_consulta):
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        busqueda = st.text_input(
            "Buscar producto",
            placeholder="Nombre del producto",
            key="movimientos_busqueda"
        )

    with col2:
        rango = st.date_input(
            "Rango de fechas",
            value=(date.today() - timedelta(days=30), date.today()),
            key="movimientos_rango"
        )

    with col3:
        tipo = st.selectbox(
            "Tipo",
            TIPOS_MOVIMIENTO,
            key="movimientos_tipo"
        )

    # Mientras el usuario elige la segunda fecha el rango esta incompleto
    if not isinstance(rango, (tuple, list)) or len(rango) != 2:
        st.info("Seleccione la fecha inicial y la fecha final.")
        return

    desde, hasta = rango

    filas = obtener_movimientos(
        id_sede_consulta,
        desde,
        hasta,
        busqueda,
        tipo
    )

    if not filas:
        st.info("No se encontraron movimientos en ese período.")
        return

    if id_sede_consulta is None:
        # Todas las sedes: se agrega la columna Sede
        tabla = pd.DataFrame(
            [
                (f[7], f[0], f[1], f[2], f[3], float(f[4]), f[5], f[6])
                for f in filas
            ],
            columns=[
                "Sede",
                "Fecha",
                "Tipo",
                "Documento",
                "Producto",
                "Cantidad",
                "Unidad",
                "Registrado por"
            ]
        )
    else:
        tabla = pd.DataFrame(
            [
                (f[0], f[1], f[2], f[3], float(f[4]), f[5], f[6])
                for f in filas
            ],
            columns=[
                "Fecha",
                "Tipo",
                "Documento",
                "Producto",
                "Cantidad",
                "Unidad",
                "Registrado por"
            ]
        )

    st.dataframe(
        tabla,
        use_container_width=True,
        hide_index=True
    )

    entradas = tabla.loc[tabla["Cantidad"] > 0, "Cantidad"].sum()
    salidas = -tabla.loc[tabla["Cantidad"] < 0, "Cantidad"].sum()

    st.caption(
        f"Movimientos: {len(tabla)} | "
        f"Entradas: {entradas:,.2f} | Salidas: {salidas:,.2f}"
    )


def mostrar_inventario():
    st.header("Inventario")

    sede_usuario = obtener_sede_usuario()

    if sede_usuario is None:
        st.error("No tiene permisos para ver el inventario.")
        return

    nombre_sede = obtener_nombre_sede(sede_usuario)

    if nombre_sede is None:
        st.warning("No se encontró la sede del usuario.")
        return

    # ---- Que sede se consulta ----
    if puede_ver_todas_las_sedes():
        # Vision global: el usuario elige una sede o todas
        id_elegida = elegir_sede(sede_usuario)
    else:
        # Sede fija: cada usuario solo ve el inventario de la suya
        st.text_input(
            "Sede",
            value=nombre_sede,
            disabled=True,
            key="inventario_sede"
        )
        id_elegida = sede_usuario

    id_sede_consulta = sede_a_consultar(id_elegida, sede_usuario)

    tab_existencias, tab_movimientos = st.tabs(
        ["Existencias", "Movimientos"]
    )

    with tab_existencias:
        mostrar_existencias(id_sede_consulta)

    with tab_movimientos:
        mostrar_movimientos(id_sede_consulta)
