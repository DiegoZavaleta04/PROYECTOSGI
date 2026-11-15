from datetime import date

import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# PERMISOS
# ==============================
# Claves de st.session_state donde guardas los datos del usuario
# al iniciar sesion. Cambialas si en tu login se llaman distinto.
CLAVE_ROL = "id_rol"
CLAVE_SEDE = "id_sede"

# Nombres de los roles tal como estan en la tabla Rol (se comparan sin
# importar mayusculas o minusculas). Se usan NOMBRES y no numeros de id
# para que el modulo no dependa del orden en que se crearon los roles.
# !! REVISA que coincidan con tu tabla Rol (SELECT * FROM Rol;) !!
ROL_ENCARGADO_CD = "encargado cd"
ROL_VENDEDOR_CD = "vendedor cd"
ROL_ENCARGADO_TIENDA = "encargado tienda"
ROL_VENDEDOR_TIENDA = "vendedor tienda"

# El rol Administrador NO aparece: no tiene acceso a las compras.

METODOS_PAGO = ["Efectivo", "Tarjeta", "Transferencia"]


def obtener_nombre_rol():
    """Devuelve el nombre del rol del usuario (en minusculas), o None."""
    id_rol = st.session_state.get(CLAVE_ROL)

    if id_rol is None:
        return None

    # Se guarda en la sesion para no consultar la base en cada recarga
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


def obtener_permisos():
    """
    Devuelve (id_sede, puede_registrar).

    - Administrador: sin acceso a las compras.
    - Encargado del CD / de tienda: ve y registra las compras de SU sede.
    - Vendedor del CD / de tienda: solo ve las compras de SU sede.

    Si el usuario no tiene acceso devuelve (None, False).
    """
    id_sede = st.session_state.get(CLAVE_SEDE)
    rol = obtener_nombre_rol()

    if rol is None or id_sede is None:
        return None, False

    if rol in (ROL_ENCARGADO_CD, ROL_ENCARGADO_TIENDA):
        return id_sede, True

    if rol in (ROL_VENDEDOR_CD, ROL_VENDEDOR_TIENDA):
        return id_sede, False

    # Administrador, rol desconocido o sin sede asignada: sin acceso
    return None, False


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


def obtener_proveedores(id_sede):
    """Solo los proveedores registrados por la sede indicada."""
    return consultar(
        """
        SELECT Id_proveedor, Nombre
        FROM PROVEEDORES
        WHERE Id_sede = %s
        ORDER BY Nombre
        """,
        (id_sede,)
    )


def obtener_sedes(id_sede):
    """Solo la sede indicada (la del usuario)."""
    return consultar(
        "SELECT id_sede, nombre FROM Sede WHERE id_sede = %s",
        (id_sede,)
    )


def obtener_productos():
    return consultar(
        """
        SELECT p.Id_producto, p.Nombre, u.Abreviatura, p.Id_unidad 
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


def obtener_detalle(id_compra, id_sede):
    """El detalle de una compra, solo si pertenece a la sede indicada."""
    return consultar(
        """
        SELECT
            p.Nombre,
            d.Cantidad,
            u.Abreviatura,
            d.precio_compra,
            d.Cantidad * d.precio_compra
        FROM DETALLE_COMPRA d
        INNER JOIN COMPRAS c
            ON d.Id_compra = c.Id_compra
        INNER JOIN PRODUCTOS p
            ON d.Id_producto = p.Id_producto
        INNER JOIN UNIDAD_MEDIDA u
            ON p.Id_unidad = u.Id_unidad
        WHERE d.Id_compra = %s
          AND c.Id_sede = %s
        ORDER BY p.Nombre
        """,
        (id_compra, id_sede)
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

        # Seguridad: el proveedor debe pertenecer a la sede de la compra
        cursor.execute(
            """
            SELECT 1
            FROM PROVEEDORES
            WHERE Id_proveedor = %s AND Id_sede = %s
            LIMIT 1
            """,
            (id_proveedor, id_sede)
        )

        if cursor.fetchone() is None:
            raise ValueError(
                "El proveedor no pertenece a la sede de la compra."
            )

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
                # Buscamos el Id_unidad que le pertenece al producto
                cursor.execute(
                    "SELECT Id_unidad FROM PRODUCTOS WHERE Id_producto = %s LIMIT 1",
                    (linea["id_producto"],)
                )
                id_unidad_producto = cursor.fetchone()[0]

                # Insertamos en INVENTARIO incluyendo la columna Id_unidad
                cursor.execute(
                    """
                    INSERT INTO INVENTARIO
                    (Id_producto, Existencia, Id_compra, Id_sede, Id_unidad)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        linea["id_producto"],
                        linea["cantidad"],
                        id_compra,
                        id_sede,
                        id_unidad_producto
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

    # ---- Permisos del usuario actual ----
    sede_usuario, puede_registrar = obtener_permisos()
st.write("DEBUG:", {
    "id_rol": st.session_state.get(CLAVE_ROL),
    "id_sede": st.session_state.get(CLAVE_SEDE),
    "rol": obtener_nombre_rol(),
    "sede_usuario": sede_usuario,
    "puede_registrar": puede_registrar,
})
    if sede_usuario is None:
        st.error(
            "No tiene permisos para ver las compras."
        )
        return

    # Mensaje que se guarda antes de recargar la página
    mensaje = st.session_state.pop("mensaje_compra", None)
    if mensaje:
        st.success(mensaje)

    if "lineas_compra" not in st.session_state:
        st.session_state["lineas_compra"] = []

    # Solo la sede del usuario y los proveedores de esa sede
    sedes = obtener_sedes(sede_usuario)
    proveedores = obtener_proveedores(sede_usuario)

    if not sedes:
        st.warning(
            "No se encontró la sede del usuario."
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
        # Filtro fijo: cada usuario solo ve las compras de su sede
        st.text_input(
            "Sede",
            value=sedes[0][1],
            disabled=True
        )

    compras = obtener_compras(
        busqueda,
        opciones_proveedor[proveedor_filtro],
        sede_usuario
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

        detalle = obtener_detalle(compra[0], sede_usuario)

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

    # Los vendedores solo consultan: aqui termina su pantalla
    if not puede_registrar:
        return

    st.divider()

    # -----------------------------------
    # REGISTRAR COMPRA
    # -----------------------------------
    st.subheader("Registrar nueva compra")

    if not proveedores:
        st.warning(
            "Su sede no tiene proveedores registrados. "
            "Primero debe registrar un proveedor."
        )
        return

    productos = obtener_productos()

    if not productos:
        st.warning(
            "Primero debe registrar productos."
        )
        return

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
        # La compra siempre se registra en la sede del usuario
        st.text_input(
            "Sede",
            value=sedes[0][1],
            disabled=True,
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
                    sede_usuario,
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
