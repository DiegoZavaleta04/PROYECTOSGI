from datetime import date

import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion

# Roles que pueden registrar compras:
# 1 = Encargado CD, 2 = Encargado tienda
ROLES_PUEDEN_COMPRAR = (1, 2)

METODOS_PAGO = ["Efectivo", "Tarjeta", "Transferencia"]


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


def obtener_proveedores():
    return consultar(
        "SELECT Id_proveedor, Nombre FROM PROVEEDORES ORDER BY Nombre"
    )


def obtener_sedes():
    return consultar(
        "SELECT id_sede, nombre FROM Sede ORDER BY nombre"
    )


def obtener_productos():
    return consultar(
        """
        SELECT p.Id_producto, p.Nombre, u.Abreviatura
        FROM PRODUCTOS p
        INNER JOIN UNIDAD_MEDIDA u
            ON p.Id_unidad = u.Id_unidad
        ORDER BY p.Nombre
        """
    )


def obtener_id_usuario():
    """Busca el Id del usuario que tiene la sesión iniciada."""
    filas = consultar(
        "SELECT Id_usuario FROM USUARIO WHERE Correo = %s LIMIT 1",
        (st.session_state.get("usuario", ""),)
    )

    if filas:
        return filas[0][0]

    return None


def obtener_compras(busqueda="", id_proveedor=None, id_sede=None):
    consulta = """
    SELECT
        c.Id_compra,
        c.Fecha,
        pr.Nombre,
        s.nombre,
        CONCAT(u.Nombre, ' ', u.Apellido),
        c.Metodo_pago,
        COALESCE(SUM(d.Cantidad * d.precio_compra), 0)
    FROM COMPRAS c
    INNER JOIN PROVEEDORES pr
        ON c.Id_proveedor = pr.Id_proveedor
    INNER JOIN Sede s
        ON c.Id_sede = s.id_sede
    INNER JOIN USUARIO u
        ON c.Id_usuario = u.Id_usuario
    LEFT JOIN DETALLE_COMPRA d
        ON d.Id_compra = c.Id_compra
    WHERE
        (%s = '' OR CAST(c.Id_compra AS CHAR) LIKE %s
         OR pr.Nombre LIKE %s)
        AND (%s IS NULL OR c.Id_proveedor = %s)
        AND (%s IS NULL OR c.Id_sede = %s)
    GROUP BY
        c.Id_compra, c.Fecha, pr.Nombre, s.nombre,
        u.Nombre, u.Apellido, c.Metodo_pago
    ORDER BY c.Fecha DESC, c.Id_compra DESC
    """

    termino = f"%{busqueda.strip()}%"

    return consultar(
        consulta,
        (
            busqueda.strip(),
            termino,
            termino,
            id_proveedor,
            id_proveedor,
            id_sede,
            id_sede
        )
    )


def obtener_detalle(id_compra):
    return consultar(
        """
        SELECT
            p.Nombre,
            d.Cantidad,
            u.Abreviatura,
            d.precio_compra,
            d.Cantidad * d.precio_compra
        FROM DETALLE_COMPRA d
        INNER JOIN PRODUCTOS p
            ON d.Id_producto = p.Id_producto
        INNER JOIN UNIDAD_MEDIDA u
            ON p.Id_unidad = u.Id_unidad
        WHERE d.Id_compra = %s
        ORDER BY p.Nombre
        """,
        (id_compra,)
    )


def registrar_compra(
    id_proveedor,
    id_usuario,
    id_sede,
    fecha,
    metodo_pago,
    lineas
):
    """
    Guarda la compra, su detalle y suma los productos al inventario,
    todo en una sola transacción. Devuelve el Id de la compra,
    o None si hubo un error (en ese caso no se guarda nada).
    """
    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return None

        cursor = conexion.cursor()

        cursor.execute(
            """
            INSERT INTO COMPRAS
            (Id_proveedor, Fecha, Id_usuario, Id_sede, Metodo_pago)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (id_proveedor, fecha, id_usuario, id_sede, metodo_pago)
        )

        id_compra = cursor.lastrowid

        for linea in lineas:
            cursor.execute(
                """
                INSERT INTO DETALLE_COMPRA
                (Id_compra, Id_producto, Cantidad, precio_compra)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    id_compra,
                    linea["id_producto"],
                    linea["cantidad"],
                    linea["precio"]
                )
            )

            # Entrada al inventario de la sede
            cursor.execute(
                """
                SELECT Id_inventario
                FROM INVENTARIO
                WHERE Id_producto = %s AND Id_sede = %s
                LIMIT 1
                """,
                (linea["id_producto"], id_sede)
            )

            registro = cursor.fetchone()

            if registro:
                cursor.execute(
                    """
                    UPDATE INVENTARIO
                    SET Existencia = Existencia + %s,
                        Id_compra = %s
                    WHERE Id_inventario = %s
                    """,
                    (linea["cantidad"], id_compra, registro[0])
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO INVENTARIO
                    (Id_producto, Existencia, Id_compra, Id_sede)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        linea["id_producto"],
                        linea["cantidad"],
                        id_compra,
                        id_sede
                    )
                )

        conexion.commit()

        return id_compra

    except Exception as error:
        if conexion is not None:
            conexion.rollback()

        st.error(
            f"Error al registrar la compra: {error}"
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
# PANTALLA DEL MÓDULO
# ==============================
def mostrar_compra():
    st.header("Gestión de compras")

    # Mensaje que se guarda antes de recargar la página
    mensaje = st.session_state.pop("mensaje_compra", None)
    if mensaje:
        st.success(mensaje)

    if "lineas_compra" not in st.session_state:
        st.session_state["lineas_compra"] = []

    proveedores = obtener_proveedores()
    sedes = obtener_sedes()

    if not proveedores:
        st.warning(
            "Primero debe registrar un proveedor."
        )
        return

    if not sedes:
        st.warning(
            "Primero debe registrar una sede."
        )
        return

    # -----------------------------------
    # LISTADO
    # -----------------------------------
    st.subheader("Historial de compras")

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        busqueda = st.text_input(
            "Buscar compra",
            placeholder="ID de compra o nombre del proveedor"
        )

    with col2:
        opciones_proveedor = {"Todos los proveedores": None}

        for proveedor in proveedores:
            opciones_proveedor[proveedor[1]] = proveedor[0]

        proveedor_filtro = st.selectbox(
            "Filtrar por proveedor",
            list(opciones_proveedor.keys())
        )

    with col3:
        opciones_sede = {"Todas las sedes": None}

        for sede in sedes:
            opciones_sede[sede[1]] = sede[0]

        sede_filtro = st.selectbox(
            "Filtrar por sede",
            list(opciones_sede.keys())
        )

    compras = obtener_compras(
        busqueda,
        opciones_proveedor[proveedor_filtro],
        opciones_sede[sede_filtro]
    )

    if compras:
        tabla = pd.DataFrame(
            [
                (
                    c[0],
                    c[1],
                    c[2],
                    c[3],
                    c[4],
                    c[5],
                    float(c[6])
                )
                for c in compras
            ],
            columns=[
                "ID",
                "Fecha",
                "Proveedor",
                "Sede",
                "Registrada por",
                "Método de pago",
                "Total ($)"
            ]
        )

        st.dataframe(
            tabla,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            f"Compras encontradas: {len(compras)}"
        )

        # ---- Detalle de una compra ----
        compra = st.selectbox(
            "Ver el detalle de una compra",
            compras,
            format_func=lambda c: f"{c[0]} - {c[2]} ({c[1]})",
            key="compra_detalle"
        )

        detalle = obtener_detalle(compra[0])

        if detalle:
            tabla_detalle = pd.DataFrame(
                [
                    (
                        d[0],
                        float(d[1]),
                        d[2],
                        float(d[3]),
                        float(d[4])
                    )
                    for d in detalle
                ],
                columns=[
                    "Producto",
                    "Cantidad",
                    "Unidad",
                    "Precio unitario ($)",
                    "Subtotal ($)"
                ]
            )

            st.dataframe(
                tabla_detalle,
                use_container_width=True,
                hide_index=True
            )

            st.caption(
                f"Total de la compra: ${float(compra[6]):,.2f}"
            )
        else:
            st.info(
                "Esta compra no tiene productos registrados."
            )
    else:
        st.info(
            "No se encontraron compras."
        )

    st.divider()

    # -----------------------------------
    # REGISTRAR COMPRA
    # -----------------------------------
    st.subheader("Registrar nueva compra")

    if st.session_state.get("id_rol") not in ROLES_PUEDEN_COMPRAR:
        st.info(
            "Solo los encargados del CD y de las tiendas "
            "pueden registrar compras."
        )
        return

    productos = obtener_productos()

    if not productos:
        st.warning(
            "Primero debe registrar productos."
        )
        return

    # La sede del usuario aparece seleccionada por defecto
    indice_sede = next(
        (
            i for i, s in enumerate(sedes)
            if s[0] == st.session_state.get("id_sede")
        ),
        0
    )

    col1, col2 = st.columns(2)

    with col1:
        proveedor = st.selectbox(
            "Proveedor",
            proveedores,
            format_func=lambda p: p[1],
            key="compra_proveedor"
        )

        fecha = st.date_input(
            "Fecha de la compra",
            value=date.today(),
            key="compra_fecha"
        )

    with col2:
        sede = st.selectbox(
            "Sede",
            sedes,
            index=indice_sede,
            format_func=lambda s: s[1],
            key="compra_sede"
        )

        metodo_pago = st.selectbox(
            "Método de pago",
            METODOS_PAGO,
            key="compra_metodo"
        )

    st.markdown("**Productos de la compra**")

    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        producto = st.selectbox(
            "Producto",
            productos,
            format_func=lambda p: f"{p[0]} - {p[1]} ({p[2]})",
            key="compra_producto"
        )

    with col2:
        cantidad = st.number_input(
            "Cantidad",
            min_value=0.0,
            step=1.0,
            format="%.2f",
            key="compra_cantidad"
        )

    with col3:
        precio = st.number_input(
            "Precio unitario ($)",
            min_value=0.0,
            step=0.05,
            format="%.2f",
            key="compra_precio"
        )

    if st.button("Agregar al detalle"):
        ya_agregado = any(
            linea["id_producto"] == producto[0]
            for linea in st.session_state["lineas_compra"]
        )

        if cantidad <= 0 or precio <= 0:
            st.warning(
                "La cantidad y el precio deben ser mayores que cero."
            )
        elif ya_agregado:
            st.warning(
                "Ese producto ya está en el detalle. "
                "Quítelo y agréguelo de nuevo con la cantidad correcta."
            )
        else:
            st.session_state["lineas_compra"].append(
                {
                    "id_producto": producto[0],
                    "nombre": producto[1],
                    "unidad": producto[2],
                    "cantidad": cantidad,
                    "precio": precio
                }
            )

    lineas = st.session_state["lineas_compra"]

    if lineas:
        total = 0.0

        for i, linea in enumerate(lineas):
            subtotal = linea["cantidad"] * linea["precio"]
            total += subtotal

            c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 2])

            c1.write(linea["nombre"])
            c2.write(f'{linea["cantidad"]:,.2f} {linea["unidad"]}')
            c3.write(f'${linea["precio"]:,.2f}')
            c4.write(f"${subtotal:,.2f}")

            if c5.button("Quitar", key=f"quitar_linea_{i}"):
                lineas.pop(i)
                st.rerun()

        st.write(f"**Total de la compra: ${total:,.2f}**")
    else:
        st.info(
            "Aún no hay productos en el detalle."
        )

    if st.button("Registrar compra"):
        if not lineas:
            st.warning(
                "Agregue al menos un producto a la compra."
            )
        else:
            id_usuario = obtener_id_usuario()

            if id_usuario is None:
                st.warning(
                    "No se pudo identificar al usuario de la sesión."
                )
            else:
                id_compra = registrar_compra(
                    proveedor[0],
                    id_usuario,
                    sede[0],
                    fecha,
                    metodo_pago,
                    lineas
                )

                if id_compra is not None:
                    st.session_state["lineas_compra"] = []
                    st.session_state["mensaje_compra"] = (
                        f"Compra {id_compra} registrada correctamente "
                        "y agregada al inventario."
                    )
                    st.rerun()
