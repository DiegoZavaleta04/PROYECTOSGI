import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion
from config.precios_cd import evaluar_precio_cd


# ==============================
# CONFIGURACION (AJUSTAR SI HACE FALTA)
# ==============================
CLAVE_USUARIO = "usuario"   # en tu sesion guarda el correo
CLAVE_SEDE = "id_sede"
CLAVE_ROL = "id_rol"

# Roles que pueden vender y ver ventas:
# 1 Encargado CD, 2 Encargado tienda, 3 Vendedor CD, 4 Vendedor tienda.
# El Administrador (5) no puede vender ni ver las ventas.
ROLES_VENDEN = (1, 2, 3, 4)

# La venta a una TIENDA de la red solo puede hacerse desde el CD: se
# decide por el tipo de la sede del usuario (Sede.Tipo = 'CD'), no por el
# numero de rol. Esas ventas llevan el precio que calcula el sistema.

METODOS_PAGO = ["Efectivo", "Tarjeta", "Transferencia"]

# Nombres de las tablas EXACTAMENTE como aparecen en phpMyAdmin
# (importan las mayusculas y minusculas)
T_USUARIO = "USUARIO"
T_SEDE = "Sede"
T_CLIENTE = "CLIENTE"
T_PRODUCTOS = "PRODUCTOS"
T_UNIDAD = "UNIDAD_MEDIDA"
T_INVENTARIO = "INVENTARIO"
T_VENTAS = "VENTAS"
T_DETALLE_VENTA = "DETALLE_VENTA"

# Columnas del DUI y del NIT en la tabla de clientes (revisa en phpMyAdmin)
C_CLIENTE_DUI = "DUI"
C_CLIENTE_NIT = "NIT"

# Columna de CLIENTE que dice a que tienda de la red representa el cliente
# (NULL en los clientes normales). Hay que agregarla a la tabla:
#   ALTER TABLE CLIENTE ADD COLUMN Id_tienda INT NULL;
C_CLIENTE_TIENDA = "Id_tienda"


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


def obtener_tiendas():
    """Las tiendas de la red (sedes de tipo TIENDA)."""
    return consultar(
        f"""
        SELECT id_sede, nombre
        FROM {T_SEDE}
        WHERE Tipo = 'TIENDA'
        ORDER BY nombre
        """
    )


def obtener_productos(id_sede):
    """Solo los productos con existencia en el inventario de la sede."""
    return consultar(
        f"""
        SELECT
            p.Id_producto,
            p.Nombre,
            u.Abreviatura,
            p.Id_unidad,
            i.Existencia,
            p.Incremento_venta
        FROM {T_INVENTARIO} i
        INNER JOIN {T_PRODUCTOS} p
            ON i.Id_producto = p.Id_producto
        INNER JOIN {T_UNIDAD} u
            ON p.Id_unidad = u.Id_unidad
        WHERE i.Id_sede = %s
          AND i.Existencia > 0
        ORDER BY p.Nombre
        """,
        (id_sede,)
    )


def obtener_ventas_recientes(id_sede):
    return consultar(
        f"""
        SELECT
            v.Id_venta,
            v.Fecha,
            c.Nombre,
            CONCAT(u.Nombre, ' ', u.Apellido),
            v.Metodo_pago,
            COALESCE(SUM(d.Cantidad * d.Precio_venta), 0)
        FROM {T_VENTAS} v
        INNER JOIN {T_CLIENTE} c
            ON v.Id_cliente = c.Id_cliente
        INNER JOIN {T_USUARIO} u
            ON v.Id_usuario = u.Id_usuario
        LEFT JOIN {T_DETALLE_VENTA} d
            ON d.Id_venta = v.Id_venta
        WHERE v.Id_sede = %s
        GROUP BY
            v.Id_venta, v.Fecha, c.Nombre,
            u.Nombre, u.Apellido, v.Metodo_pago
        ORDER BY v.Id_venta DESC
        LIMIT 20
        """,
        (id_sede,)
    )


def obtener_o_crear_cliente(cursor, id_sede, nombre, dui, nit, telefono):
    """
    Cliente normal. Si ya existe un cliente con ese DUI (o NIT) en la
    sede, se reutiliza; si no, se crea uno nuevo. Devuelve su Id.
    """
    fila = None

    if dui:
        cursor.execute(
            f"""
            SELECT Id_cliente
            FROM {T_CLIENTE}
            WHERE {C_CLIENTE_DUI} = %s AND Id_sede = %s
            LIMIT 1
            """,
            (dui, id_sede)
        )
        fila = cursor.fetchone()

    if fila is None and nit:
        cursor.execute(
            f"""
            SELECT Id_cliente
            FROM {T_CLIENTE}
            WHERE {C_CLIENTE_NIT} = %s AND Id_sede = %s
            LIMIT 1
            """,
            (nit, id_sede)
        )
        fila = cursor.fetchone()

    if fila is None and not dui and not nit:
        # Sin documentos: se reutiliza un cliente con el mismo
        # nombre que tampoco tenga documentos
        cursor.execute(
            f"""
            SELECT Id_cliente
            FROM {T_CLIENTE}
            WHERE Nombre = %s
              AND ({C_CLIENTE_DUI} IS NULL OR {C_CLIENTE_DUI} = '')
              AND ({C_CLIENTE_NIT} IS NULL OR {C_CLIENTE_NIT} = '')
              AND {C_CLIENTE_TIENDA} IS NULL
              AND Id_sede = %s
            LIMIT 1
            """,
            (nombre, id_sede)
        )
        fila = cursor.fetchone()

    if fila:
        id_cliente = fila[0]
        cursor.execute(
            f"""
            UPDATE {T_CLIENTE}
            SET Nombre = %s,
                Telefono = COALESCE(%s, Telefono),
                {C_CLIENTE_DUI} = COALESCE(%s, {C_CLIENTE_DUI}),
                {C_CLIENTE_NIT} = COALESCE(%s, {C_CLIENTE_NIT})
            WHERE Id_cliente = %s
            """,
            (nombre, telefono, dui, nit, id_cliente)
        )
        return id_cliente

    cursor.execute(
        f"""
        INSERT INTO {T_CLIENTE}
        (Nombre, {C_CLIENTE_DUI}, {C_CLIENTE_NIT}, Telefono, Id_sede)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (nombre, dui, nit, telefono, id_sede)
    )

    return cursor.lastrowid


def obtener_o_crear_cliente_tienda(
    cursor,
    id_sede,
    id_tienda,
    nombre_tienda,
    telefono_tienda
):
    """
    Cliente que representa a una tienda de la red. Se reutiliza el que ya
    exista para esa tienda; si no, se crea. Devuelve su Id.
    """
    cursor.execute(
        f"""
        SELECT Id_cliente
        FROM {T_CLIENTE}
        WHERE {C_CLIENTE_TIENDA} = %s
        LIMIT 1
        """,
        (id_tienda,)
    )

    fila = cursor.fetchone()

    if fila:
        return fila[0]

    cursor.execute(
        f"""
        INSERT INTO {T_CLIENTE}
        (Nombre, Telefono, Id_sede, {C_CLIENTE_TIENDA})
        VALUES (%s, %s, %s, %s)
        """,
        (nombre_tienda, telefono_tienda, id_sede, id_tienda)
    )

    return cursor.lastrowid


def registrar_venta(
    fecha,
    id_usuario,
    id_sede,
    metodo_pago,
    datos_cliente,
    lineas,
    id_tienda=None
):
    """
    Guarda el cliente, la venta, su detalle y descuenta el inventario
    de la sede, todo en una sola transaccion: si algo falla,
    no se guarda nada.

    datos_cliente = (nombre, dui, nit, telefono)
    El DUI, el NIT y el telefono son opcionales. Si ya existe un cliente
    con ese DUI (o NIT) en la sede, se reutiliza; si no, se crea uno nuevo.

    id_tienda: si no es None, es una venta del CD a esa tienda. En ese
    caso el precio de cada linea lo fija el sistema (costo del CD mas
    margen operativo) y solo se permite si es menor que el de los
    proveedores de la tienda.

    Devuelve el Id de la venta, o None si hubo error.
    """
    nombre, dui, nit, telefono = datos_cliente

    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return None

        cursor = conexion.cursor()

        # ---- Regla de venta: se revisa en la base, no solo en pantalla ----
        for linea in lineas:
            cursor.execute(
                f"""
                SELECT Incremento_venta
                FROM {T_PRODUCTOS}
                WHERE Id_producto = %s
                """,
                (linea["id_producto"],)
            )

            fila_regla = cursor.fetchone()
            incremento = a_incremento(
                fila_regla[0] if fila_regla else None
            )

            if not cantidad_valida(linea["cantidad"], incremento):
                raise ValueError(
                    f"{linea['producto']} solo se vende "
                    f"{texto_incremento(incremento, linea['abreviatura'])}."
                )

        # ---- Venta del CD a una tienda: origen, destino y precios ----
        fila_destino = None

        if id_tienda is not None:
            cursor.execute(
                f"SELECT Tipo FROM {T_SEDE} WHERE id_sede = %s",
                (id_sede,)
            )
            fila_origen = cursor.fetchone()

            if not fila_origen or str(fila_origen[0]).upper() != "CD":
                raise ValueError(
                    "Solo el Centro de Distribución puede venderle "
                    "a una tienda."
                )

            cursor.execute(
                f"SELECT Tipo, nombre, Telefono FROM {T_SEDE} "
                "WHERE id_sede = %s",
                (id_tienda,)
            )
            fila_destino = cursor.fetchone()

            if not fila_destino or str(fila_destino[0]).upper() != "TIENDA":
                raise ValueError(
                    "La sede de destino debe ser una tienda."
                )

            # El precio lo fija el sistema, nunca lo escribe el usuario
            lineas = [dict(linea) for linea in lineas]

            for linea in lineas:
                evaluacion = evaluar_precio_cd(
                    linea["id_producto"],
                    id_tienda,
                    cursor
                )

                if not evaluacion["permitido"]:
                    raise ValueError(
                        f"{linea['producto']}: {evaluacion['mensaje']}"
                    )

                linea["precio"] = float(evaluacion["precio_cd"])

        # ---- Cliente ----
        if id_tienda is not None:
            id_cliente = obtener_o_crear_cliente_tienda(
                cursor,
                id_sede,
                id_tienda,
                fila_destino[1],
                fila_destino[2]
            )
        else:
            id_cliente = obtener_o_crear_cliente(
                cursor,
                id_sede,
                nombre,
                dui,
                nit,
                telefono
            )

        # ---- Venta (siempre asociada a la sede del usuario) ----
        cursor.execute(
            f"""
            INSERT INTO {T_VENTAS}
            (Fecha, Id_usuario, Id_sede, Id_cliente, Metodo_pago)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (fecha, id_usuario, id_sede, id_cliente, metodo_pago)
        )

        id_venta = cursor.lastrowid

        # ---- Detalle ----
        cursor.executemany(
            f"""
            INSERT INTO {T_DETALLE_VENTA}
            (Id_venta, Id_producto, Cantidad, Id_unidad, Precio_venta)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (
                    id_venta,
                    linea["id_producto"],
                    linea["cantidad"],
                    linea["id_unidad"],
                    linea["precio"]
                )
                for linea in lineas
            ]
        )

        # ---- Salida del inventario de la sede ----
        for linea in lineas:
            cursor.execute(
                f"""
                UPDATE {T_INVENTARIO}
                SET Existencia = Existencia - %s,
                    Id_venta = %s
                WHERE Id_producto = %s
                  AND Id_sede = %s
                  AND Existencia >= %s
                """,
                (
                    linea["cantidad"],
                    id_venta,
                    linea["id_producto"],
                    id_sede,
                    linea["cantidad"]
                )
            )

            if cursor.rowcount == 0:
                raise ValueError(
                    "No hay existencia suficiente de "
                    f"{linea['producto']} en esta sede."
                )

        conexion.commit()
        return id_venta

    except ValueError as error:
        if conexion is not None:
            conexion.rollback()

        st.warning(str(error))
        return None

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


def documento_valido(valor, maximo):
    """Solo números y guiones, con una longitud máxima."""
    return (
        len(valor) <= maximo
        and all(c.isdigit() or c == "-" for c in valor)
    )


# ==============================
# REGLA DE VENTA DEL PRODUCTO
# ==============================
# PRODUCTOS.Incremento_venta es lo mas pequeno que se puede vender:
# 1 = solo enteros, 0.5 = medias, 0.25 = cuartos.
INCREMENTO_POR_DEFECTO = 1.0


def a_incremento(valor):
    """Convierte el valor de la base a float (1.0 si falta o no es valido)."""
    try:
        incremento = float(valor)
    except (TypeError, ValueError):
        return INCREMENTO_POR_DEFECTO

    return incremento if incremento > 0 else INCREMENTO_POR_DEFECTO


def cantidad_valida(cantidad, incremento):
    """True si la cantidad es multiplo exacto del incremento."""
    veces = cantidad / incremento

    return abs(veces - round(veces)) < 1e-6


def decimales_incremento(incremento):
    """Decimales que debe mostrar el campo de cantidad."""
    if incremento >= 1:
        return 0

    if incremento >= 0.5:
        return 1

    return 2


def texto_incremento(incremento, abreviatura):
    if incremento >= 1:
        return "solo en cantidades enteras"

    return f"de {incremento:g} en {incremento:g} {abreviatura}"


# ==============================
# VENTAS RECIENTES DE LA SEDE
# ==============================
def mostrar_ventas_recientes(id_sede):
    st.subheader("Ventas recientes de la sede")

    ventas = obtener_ventas_recientes(id_sede)

    if ventas:
        tabla_ventas = pd.DataFrame(
            [
                (v[0], v[1], v[2], v[3], v[4], float(v[5]))
                for v in ventas
            ],
            columns=[
                "ID",
                "Fecha",
                "Cliente",
                "Vendedor",
                "Método de pago",
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


# ==============================
# PANTALLA DEL MODULO
# ==============================
def mostrar_venta():
    st.header("Registrar nueva venta")

    # ---- Permisos ----
    id_rol = st.session_state.get(CLAVE_ROL)
    id_sede = st.session_state.get(CLAVE_SEDE)
    correo = st.session_state.get(CLAVE_USUARIO)

    # El administrador no puede vender ni ver las ventas
    if id_rol not in ROLES_VENDEN:
        st.warning(
            "No tiene permiso para registrar ni ver ventas."
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

    # Solo el CD puede venderle a una tienda de la red. Se decide por el
    # tipo de la sede del usuario (CD), no por el numero de rol.
    filas_tipo = consultar(
        f"SELECT Tipo FROM {T_SEDE} WHERE id_sede = %s",
        (id_sede,)
    )
    puede_a_tiendas = (
        bool(filas_tipo)
        and str(filas_tipo[0][0]).strip().upper() == "CD"
    )

    # Mensaje guardado antes de recargar la pagina
    mensaje = st.session_state.pop("mensaje_venta", None)
    if mensaje:
        st.success(mensaje)

    if "lineas_venta" not in st.session_state:
        st.session_state["lineas_venta"] = []

    # Limpiar los datos del cliente despues de registrar una venta
    # (debe hacerse antes de crear los campos)
    if st.session_state.pop("limpiar_cliente_venta", False):
        st.session_state["venta_cli_nombre"] = ""
        st.session_state["venta_cli_dui"] = ""
        st.session_state["venta_cli_nit"] = ""
        st.session_state["venta_cli_tel"] = ""
        st.session_state["venta_metodo_pago"] = None

    # Solo los productos con existencia en la sede del usuario
    productos = obtener_productos(id_sede)

    if not productos:
        st.warning(
            "No hay productos con existencia en esta sede."
        )
        st.divider()
        mostrar_ventas_recientes(id_sede)
        return

    existencias = {p[0]: float(p[4]) for p in productos}
    incrementos = {p[0]: a_incremento(p[5]) for p in productos}

    # -----------------------------------
    # DATOS DEL CLIENTE
    # -----------------------------------
    st.subheader("Datos del cliente")

    es_tienda = False
    id_tienda = None
    nombre_tienda = ""

    if puede_a_tiendas:
        tipo_venta = st.radio(
            "Tipo de venta",
            ["Cliente", "Tienda de la red"],
            horizontal=True,
            key="venta_tipo_cliente"
        )
        es_tienda = tipo_venta == "Tienda de la red"

    if es_tienda:
        tiendas = obtener_tiendas()

        if not tiendas:
            st.warning("No hay tiendas registradas.")
            st.divider()
            mostrar_ventas_recientes(id_sede)
            return

        tienda = st.selectbox(
            "Tienda que compra",
            tiendas,
            format_func=lambda t: t[1],
            key="venta_tienda"
        )

        id_tienda = tienda[0]
        nombre_tienda = tienda[1]

        st.caption(
            "El precio lo calcula el sistema: costo del CD más el margen "
            "operativo. Solo se vende si es menor que el de los "
            "proveedores de la tienda."
        )

        cliente_nombre = ""
        cliente_dui = ""
        cliente_nit = ""
        cliente_tel = ""

    else:
        col1, col2, col3, col4 = st.columns([2, 1, 1, 1])

        with col1:
            cliente_nombre = st.text_input(
                "Nombre del cliente",
                max_chars=100,
                key="venta_cli_nombre"
            )

        with col2:
            cliente_dui = st.text_input(
                "DUI (opcional)",
                max_chars=10,
                key="venta_cli_dui"
            )

        with col3:
            cliente_nit = st.text_input(
                "NIT (opcional)",
                max_chars=17,
                key="venta_cli_nit"
            )

        with col4:
            cliente_tel = st.text_input(
                "Teléfono (opcional)",
                max_chars=20,
                key="venta_cli_tel"
            )

    # Si cambia el destino (cliente o tienda), el detalle se reinicia,
    # porque los precios de una tienda no sirven para otro destino
    destino = ("tienda", id_tienda) if es_tienda else ("cliente", None)

    if st.session_state.get("venta_destino") != destino:
        st.session_state["lineas_venta"] = []
        st.session_state["venta_destino"] = destino

    # -----------------------------------
    # DATOS DE LA VENTA
    # -----------------------------------
    st.subheader("Datos de la venta")

    col5, col6, col7, col8 = st.columns(4)

    with col5:
        fecha = st.date_input("Fecha de la venta")

    with col6:
        st.text_input(
            "Sede",
            value=nombre_sede,
            disabled=True
        )

    with col7:
        st.text_input(
            "Vendedor",
            value=nombre_vendedor,
            disabled=True
        )

    with col8:
        metodo_pago = st.selectbox(
            "Método de pago",
            METODOS_PAGO,
            index=None,
            placeholder="Seleccione...",
            key="venta_metodo_pago"
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
            format_func=lambda p: (
                f"{p[0]} - {p[1]} ({p[2]}) "
                f"- Existencia: {float(p[4]):,.2f}"
            )
        )

    # Regla de venta del producto elegido
    incremento = incrementos[producto[0]]

    with colc:
        cantidad = st.number_input(
            f"Cantidad ({producto[2]})",
            min_value=0.0,
            step=incremento,
            format=f"%.{decimales_incremento(incremento)}f",
            key=f"venta_cantidad_{producto[0]}"
        )

    st.caption(
        f"{producto[1]} se vende "
        f"{texto_incremento(incremento, producto[2])}."
    )

    evaluacion = None

    with colpr:
        if es_tienda:
            # Precio fijado por el sistema (no se puede escribir)
            evaluacion = evaluar_precio_cd(producto[0], id_tienda)
            precio_cd = evaluacion["precio_cd"]

            st.text_input(
                "Precio unitario ($)",
                value=str(precio_cd) if precio_cd is not None else "-",
                disabled=True,
                key=f"venta_precio_cd_{producto[0]}_{id_tienda}"
            )

            precio = float(precio_cd) if precio_cd is not None else 0.0
        else:
            precio = st.number_input(
                "Precio unitario ($)",
                min_value=0.0,
                step=0.05,
                format="%.2f"
            )

    if es_tienda and evaluacion is not None:
        if evaluacion["permitido"]:
            st.success(evaluacion["mensaje"])
        else:
            st.error(evaluacion["mensaje"])

        if evaluacion["costo_cd"] is not None:
            referencia = evaluacion["precio_referencia"]

            st.caption(
                f"Costo del CD: ${evaluacion['costo_cd']:,.4f} | "
                f"Precio a la tienda: ${evaluacion['precio_cd']} | "
                "Mejor precio de la tienda: "
                f"{'$' + str(referencia) if referencia is not None else 'sin referencia'}"
            )

    if st.button("Agregar al detalle"):
        lineas = st.session_state["lineas_venta"]

        # Un producto no puede repetirse en la misma venta
        # (la llave de Detalle_venta es Id_venta + Id_producto),
        # asi que si ya existe se suma la cantidad.
        existente = next(
            (l for l in lineas if l["id_producto"] == producto[0]),
            None
        )

        ya_agregado = existente["cantidad"] if existente else 0
        disponible = existencias[producto[0]] - ya_agregado

        if es_tienda and not evaluacion["permitido"]:
            st.warning(evaluacion["mensaje"])
        elif cantidad <= 0:
            st.warning("La cantidad debe ser mayor que 0.")
        elif not cantidad_valida(cantidad, incremento):
            st.warning(
                f"{producto[1]} solo se vende "
                f"{texto_incremento(incremento, producto[2])}."
            )
        elif precio <= 0:
            st.warning("El precio debe ser mayor que 0.")
        elif cantidad > disponible:
            st.warning(
                f"Solo puede agregar {max(disponible, 0):,.2f} "
                f"{producto[2]} más: es la existencia disponible "
                "en la sede."
            )
        else:
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
        nombre_cli = cliente_nombre.strip()
        dui_cli = cliente_dui.strip()
        nit_cli = cliente_nit.strip()
        tel_cli = cliente_tel.strip()

        if es_tienda and id_tienda is None:
            st.warning(
                "Debe seleccionar la tienda."
            )
        elif not es_tienda and nombre_cli == "":
            st.warning(
                "Debe ingresar el nombre del cliente."
            )
        elif (
            not es_tienda
            and dui_cli != ""
            and not documento_valido(dui_cli, 10)
        ):
            st.warning(
                "El DUI solo puede tener números y guiones "
                "(máximo 10 caracteres)."
            )
        elif (
            not es_tienda
            and nit_cli != ""
            and not documento_valido(nit_cli, 17)
        ):
            st.warning(
                "El NIT solo puede tener números y guiones "
                "(máximo 17 caracteres)."
            )
        elif (
            not es_tienda
            and tel_cli != ""
            and not all(c.isdigit() or c in " +-()" for c in tel_cli)
        ):
            st.warning(
                "El teléfono solo puede tener números, "
                "espacios, + - ( )."
            )
        elif metodo_pago is None:
            st.warning(
                "Debe seleccionar el método de pago."
            )
        elif not lineas:
            st.warning(
                "Agregue al menos un producto al detalle."
            )
        else:
            id_venta = registrar_venta(
                fecha,
                id_usuario,
                id_sede,       # siempre la sede del usuario
                metodo_pago,
                (
                    nombre_cli,
                    dui_cli or None,
                    nit_cli or None,
                    tel_cli or None
                ),
                lineas,
                id_tienda=id_tienda if es_tienda else None
            )

            if id_venta:
                total = round(
                    sum(l["cantidad"] * l["precio"] for l in lineas),
                    2
                )
                st.session_state["lineas_venta"] = []
                st.session_state["limpiar_cliente_venta"] = True

                destino_texto = (
                    f" a la tienda {nombre_tienda}" if es_tienda else ""
                )

                st.session_state["mensaje_venta"] = (
                    f"Venta #{id_venta}{destino_texto} registrada "
                    f"correctamente. Total: ${total:,.2f}"
                )
                st.rerun()

    st.divider()

    mostrar_ventas_recientes(id_sede)
