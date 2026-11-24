from datetime import date

import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# PERMISOS
# ==============================

CLAVE_ROL = "id_rol"
CLAVE_SEDE = "id_sede"

ROL_ENCARGADO_CD = "encargado cd"
ROL_VENDEDOR_CD = "vendedor cd"
ROL_ENCARGADO_TIENDA = "encargado tienda"
ROL_VENDEDOR_TIENDA = "vendedor tienda"

METODOS_PAGO = ["Efectivo", "Tarjeta", "Transferencia"]


# ==============================
# CONVERSIONES DE PRESENTACION
# ==============================
# Abreviaturas (en minusculas) con las que tienes registrada la libra en la
# tabla UNIDAD_MEDIDA. !! REVISA con: SELECT * FROM UNIDAD_MEDIDA; !!
UNIDADES_LIBRA = ("lb", "lbs", "libra", "libras")

# Un quintal equivale a 100 libras.
LIBRAS_POR_QUINTAL = 100

PRESENTACION_QUINTAL = "Quintal (100 lb)"
PRESENTACION_CAJA = "Caja / lote (indicar unidades que trae)"


# ==============================
# FUNCIONES DE PERMISOS
# ==============================

def obtener_nombre_rol():
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


def obtener_permisos():
    id_sede = st.session_state.get(CLAVE_SEDE)
    rol = obtener_nombre_rol()

    if rol is None or id_sede is None:
        return None, False

    if rol in (ROL_ENCARGADO_CD, ROL_ENCARGADO_TIENDA):
        return id_sede, True

    if rol in (ROL_VENDEDOR_CD, ROL_VENDEDOR_TIENDA):
        return id_sede, False

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
        st.error(f"Error al consultar los datos: {error}")
        return []

    finally:
        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


def obtener_proveedores(id_sede):
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
    return consultar(
        """
        SELECT id_sede, nombre
        FROM Sede
        WHERE id_sede = %s
        """,
        (id_sede,)
    )


def obtener_productos():
    return consultar(
        """
        SELECT
            p.Id_producto,
            p.Nombre,
            u.Abreviatura,
            p.Id_unidad
        FROM PRODUCTOS p
        INNER JOIN UNIDAD_MEDIDA u
            ON p.Id_unidad = u.Id_unidad
        ORDER BY p.Nombre
        """
    )


def obtener_id_usuario():
    filas = consultar(
        """
        SELECT Id_usuario
        FROM USUARIO
        WHERE Correo = %s
        LIMIT 1
        """,
        (st.session_state.get("usuario", ""),)
    )

    return filas[0][0] if filas else None


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
        c.Id_compra,
        c.Fecha,
        pr.Nombre,
        s.nombre,
        u.Nombre,
        u.Apellido,
        c.Metodo_pago
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
    """
    Consulta el detalle de la compra.
    Muestra la unidad registrada en el detalle.
    Para compras antiguas sin unidad, utiliza la unidad del producto.
    """

    return consultar(
        """
        SELECT
            p.Nombre,
            d.Cantidad,
            COALESCE(ud.Abreviatura, ub.Abreviatura),
            d.precio_compra,
            d.Cantidad * d.precio_compra
        FROM DETALLE_COMPRA d
        INNER JOIN COMPRAS c
            ON d.Id_compra = c.Id_compra
        INNER JOIN PRODUCTOS p
            ON d.Id_producto = p.Id_producto
        INNER JOIN UNIDAD_MEDIDA ub
            ON p.Id_unidad = ub.Id_unidad
        LEFT JOIN UNIDAD_MEDIDA ud
            ON d.Id_unidad = ud.Id_unidad
        WHERE d.Id_compra = %s
          AND c.Id_sede = %s
        ORDER BY p.Nombre
        """,
        (id_compra, id_sede)
    )


# ==============================
# REGISTRAR COMPRA
# ==============================

def registrar_compra(
    id_proveedor,
    id_usuario,
    id_sede,
    fecha,
    metodo_pago,
    lineas
):

    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return None

        cursor = conexion.cursor()

        # Verificar que el proveedor pertenezca a la sede
        cursor.execute(
            """
            SELECT 1
            FROM PROVEEDORES
            WHERE Id_proveedor = %s
              AND Id_sede = %s
            LIMIT 1
            """,
            (id_proveedor, id_sede)
        )

        if cursor.fetchone() is None:
            raise ValueError(
                "El proveedor no pertenece a la sede de la compra."
            )

        # Registrar encabezado
        cursor.execute(
            """
            INSERT INTO COMPRAS
            (
                Id_proveedor,
                Fecha,
                Id_usuario,
                Id_sede,
                Metodo_pago
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                id_proveedor,
                fecha,
                id_usuario,
                id_sede,
                metodo_pago
            )
        )

        id_compra = cursor.lastrowid

        # Registrar detalle y actualizar inventario
        for linea in lineas:

            # Se guarda siempre en la unidad de venta del producto
            # (ya convertida: libras, unidades, etc.)
            cursor.execute(
                """
                INSERT INTO DETALLE_COMPRA
                (
                    Id_compra,
                    Id_producto,
                    Cantidad,
                    Id_unidad,
                    precio_compra
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    id_compra,
                    linea["id_producto"],
                    linea["cantidad"],
                    linea["id_unidad"],
                    linea["precio"]
                )
            )
             # Relacion producto-proveedor: se crea o se actualiza con el
            # precio y la fecha de esta compra
            cursor.execute(
                """
                SELECT 1
                FROM PRODUCTO_PROVEEDOR
                WHERE Id_producto = %s
                  AND Id_proveedor = %s
                LIMIT 1
                """,
                (linea["id_producto"], id_proveedor)
            )

            if cursor.fetchone():
                cursor.execute(
                    """
                    UPDATE PRODUCTO_PROVEEDOR
                    SET Precio_ofrecido = %s,
                        Fecha_actualizacion = %s
                    WHERE Id_producto = %s
                      AND Id_proveedor = %s
                    """,
                    (
                        linea["precio"],
                        fecha,
                        linea["id_producto"],
                        id_proveedor
                    )
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO PRODUCTO_PROVEEDOR
                    (
                        Id_producto,
                        Id_proveedor,
                        Precio_ofrecido,
                        Fecha_actualizacion
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        linea["id_producto"],
                        id_proveedor,
                        linea["precio"],
                        fecha
                    )
                )
            # Buscar inventario del producto en la sede
            cursor.execute(
                """
                SELECT Id_inventario
                FROM INVENTARIO
                WHERE Id_producto = %s
                  AND Id_sede = %s
                LIMIT 1
                """,
                (linea["id_producto"], id_sede)
            )

            registro = cursor.fetchone()

            if registro:

                # Sumar las unidades al inventario
                cursor.execute(
                    """
                    UPDATE INVENTARIO
                    SET Existencia = Existencia + %s,
                        Id_compra = %s
                    WHERE Id_inventario = %s
                    """,
                    (
                        linea["cantidad"],
                        id_compra,
                        registro[0]
                    )
                )

            else:

                # Crear inventario si el producto aún no existe
                cursor.execute(
                    """
                    INSERT INTO INVENTARIO
                    (
                        Id_producto,
                        Existencia,
                        Id_compra,
                        Id_sede
                    )
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

        st.error(f"Error al registrar la compra: {error}")

        return None

    finally:

        if cursor is not None:
            cursor.close()

        if conexion is not None and conexion.is_connected():
            conexion.close()


# ==============================
# PANTALLA DE COMPRAS
# ==============================

def mostrar_compra():

    st.header("Gestión de compras")

    # Permisos
    sede_usuario, puede_registrar = obtener_permisos()

    if sede_usuario is None:
        st.error("No tiene permisos para ver las compras.")
        return

    mensaje = st.session_state.pop("mensaje_compra", None)

    if mensaje:
        st.success(mensaje)

    if "lineas_compra" not in st.session_state:
        st.session_state["lineas_compra"] = []

    sedes = obtener_sedes(sede_usuario)
    proveedores = obtener_proveedores(sede_usuario)

    if not sedes:
        st.warning("No se encontró la sede del usuario.")
        return

    # =================================
    # HISTORIAL DE COMPRAS
    # =================================

    st.subheader("Historial de compras")

    col1, col2, col3 = st.columns([2, 1, 1])

    with col1:
        busqueda = st.text_input(
            "Buscar compra",
            placeholder="ID de compra o nombre del proveedor"
        )

    with col2:

        opciones_proveedor = {
            "Todos los proveedores": None
        }

        for proveedor_item in proveedores:
            opciones_proveedor[proveedor_item[1]] = proveedor_item[0]

        proveedor_filtro = st.selectbox(
            "Filtrar por proveedor",
            list(opciones_proveedor.keys())
        )

    with col3:

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

        st.caption(f"Compras encontradas: {len(compras)}")

        compra = st.selectbox(
            "Ver el detalle de una compra",
            compras,
            format_func=lambda c: f"{c[0]} - {c[2]} ({c[1]})",
            key="compra_detalle"
        )

        detalle = obtener_detalle(
            compra[0],
            sede_usuario
        )

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
            st.info("Esta compra no tiene productos registrados.")

    else:
        st.info("No se encontraron compras.")

    # Los vendedores solo consultan
    if not puede_registrar:
        return

    st.divider()

    # =================================
    # REGISTRAR NUEVA COMPRA
    # =================================

    st.subheader("Registrar nueva compra")

    if not proveedores:
        st.warning(
            "Su sede no tiene proveedores registrados. "
            "Primero debe registrar un proveedor."
        )
        return

    productos = obtener_productos()

    if not productos:
        st.warning("Primero debe registrar productos.")
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

    producto = st.selectbox(
        "Producto",
        productos,
        format_func=lambda p: f"{p[0]} - {p[1]} ({p[2]})",
        key="compra_producto"
    )

    unidad_producto = producto[2]
    es_libra = str(unidad_producto).strip().lower() in UNIDADES_LIBRA

    # =================================
    # PRESENTACION DE LA COMPRA
    # =================================
    # El inventario siempre se guarda en la unidad en que se vende el
    # producto. Aqui se indica en que presentacion se compro y el sistema
    # hace la conversion.

    texto_directo = f"Directo ({unidad_producto})"

    opciones_presentacion = [texto_directo]

    # El quintal solo tiene sentido en productos que se venden por libra
    if es_libra:
        opciones_presentacion.append(PRESENTACION_QUINTAL)

    opciones_presentacion.append(PRESENTACION_CAJA)

    presentacion = st.selectbox(
        "¿En qué presentación compró el producto?",
        opciones_presentacion,
        key="compra_presentacion"
    )

    if presentacion == PRESENTACION_QUINTAL:

        clave = "quintal"
        factor = float(LIBRAS_POR_QUINTAL)
        etiqueta_cantidad = "Cantidad de quintales"
        etiqueta_precio = "Precio por quintal ($)"

        st.info(
            f"1 quintal = {LIBRAS_POR_QUINTAL} libras. "
            "El sistema lo convierte automáticamente."
        )

    elif presentacion == PRESENTACION_CAJA:

        clave = "caja"
        etiqueta_cantidad = "Cantidad de cajas"
        etiqueta_precio = "Precio por caja ($)"

        st.info(
            "Indique cuántas unidades trae cada caja. "
            "Puede cambiar según el producto."
        )

        factor = st.number_input(
            f"Unidades ({unidad_producto}) que trae cada caja",
            min_value=1.0,
            value=1.0,
            step=1.0,
            key="compra_unidades_caja"
        )

    else:

        clave = "directo"
        factor = 1.0
        etiqueta_cantidad = f"Cantidad ({unidad_producto})"
        etiqueta_precio = f"Precio por {unidad_producto} ($)"

    col1, col2 = st.columns(2)

    with col1:

        cantidad_presentacion = st.number_input(
            etiqueta_cantidad,
            min_value=0.0,
            value=0.0,
            step=1.0,
            key=f"compra_cantidad_{clave}"
        )

    with col2:

        precio_presentacion = st.number_input(
            etiqueta_precio,
            min_value=0.0,
            value=0.0,
            step=0.05,
            format="%.2f",
            key=f"compra_precio_{clave}"
        )

    # Conversion a la unidad de venta
    cantidad_final = cantidad_presentacion * factor
    precio_unitario = precio_presentacion / factor
    precio_ingresado = precio_presentacion

    if factor != 1:

        st.write(
            f"**Ingresará al inventario:** "
            f"{cantidad_final:,.2f} {unidad_producto}"
        )

        st.write(
            f"**Precio equivalente por {unidad_producto}:** "
            f"${precio_unitario:,.4f}"
        )

    st.write(
        f"**Total de la compra de este producto:** "
        f"${cantidad_presentacion * precio_presentacion:,.2f}"
    )

    # =================================
    # AGREGAR PRODUCTO AL DETALLE
    # =================================

    if st.button("Agregar al detalle"):

        ya_agregado = any(
            linea["id_producto"] == producto[0]
            for linea in st.session_state["lineas_compra"]
        )

        if cantidad_final <= 0:

            st.warning(
                "La cantidad debe ser mayor que cero."
            )

        elif precio_ingresado <= 0:

            st.warning(
                "El precio debe ser mayor que cero."
            )

        elif ya_agregado:

            st.warning(
                "Ese producto ya está en el detalle. "
                "Quítelo y agréguelo de nuevo."
            )

        else:

            # Se guarda la cantidad ya convertida a la unidad de venta
            st.session_state["lineas_compra"].append(
                {
                    "id_producto": producto[0],
                    "nombre": producto[1],
                    "unidad": producto[2],
                    "id_unidad": producto[3],
                    "cantidad": cantidad_final,
                    "precio": precio_unitario
                }
            )

            st.success(
                f"Se agregaron {cantidad_final:,.2f} "
                f"{producto[2]} de {producto[1]}."
            )

    # =================================
    # MOSTRAR DETALLE
    # =================================

    lineas = st.session_state["lineas_compra"]

    if lineas:

        total = 0.0

        st.markdown("**Detalle de productos agregados**")

        for i, linea in enumerate(lineas):

            subtotal = linea["cantidad"] * linea["precio"]
            total += subtotal

            c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 2])

            c1.write(linea["nombre"])

            c2.write(
                f'{linea["cantidad"]:,.2f} {linea["unidad"]}'
            )

            c3.write(
                f'${linea["precio"]:,.4f}'
            )

            c4.write(
                f"${subtotal:,.2f}"
            )

            if c5.button("Quitar", key=f"quitar_linea_{i}"):

                lineas.pop(i)
                st.rerun()

        st.write(f"**Total de la compra: ${total:,.2f}**")

    else:

        st.info("Aún no hay productos en el detalle.")

    # =================================
    # REGISTRAR COMPRA
    # =================================

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
