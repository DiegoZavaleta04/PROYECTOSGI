import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion

# Roles que pueden registrar movimientos:
# 1 = Encargado CD, 2 = Encargado tienda
ROLES_PUEDEN_MOVER = (1, 2)

TIPOS_MOVIMIENTO = ["Entrada", "Salida", "Ajuste"]


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


def ejecutar(consulta, parametros=()):
    """Devuelve las filas afectadas, o None si hubo un error."""
    conexion = None
    cursor = None

    try:
        conexion = obtener_conexion()

        if conexion is None:
            return None

        cursor = conexion.cursor()
        cursor.execute(consulta, parametros)
        conexion.commit()

        return cursor.rowcount

    except Exception as error:
        if conexion is not None:
            conexion.rollback()

        st.error(
            f"Error al guardar los datos: {error}"
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


def obtener_inventario(busqueda="", id_sede=None):
    consulta = """
    SELECT
        i.Id_inventario,
        p.Id_producto,
        p.Nombre,
        c.nombre,
        u.Abreviatura,
        s.nombre,
        i.Existencia,
        i.Id_sede
    FROM INVENTARIO i
    INNER JOIN PRODUCTOS p
        ON i.Id_producto = p.Id_producto
    INNER JOIN Categoria c
        ON p.Id_categoria = c.id_categoria
    INNER JOIN UNIDAD_MEDIDA u
        ON p.Id_unidad = u.Id_unidad
    INNER JOIN Sede s
        ON i.Id_sede = s.id_sede
    WHERE
        (%s = '' OR p.Nombre LIKE %s
         OR CAST(p.Id_producto AS CHAR) LIKE %s)
        AND (%s IS NULL OR i.Id_sede = %s)
    ORDER BY s.nombre, p.Nombre
    """

    termino = f"%{busqueda.strip()}%"

    return consultar(
        consulta,
        (
            busqueda.strip(),
            termino,
            termino,
            id_sede,
            id_sede
        )
    )


def aplicar_movimiento(tipo, id_producto, id_sede, cantidad):
    """
    Registra una entrada, salida o ajuste.
    Devuelve (True, mensaje) si se guardó, o (False, mensaje).
    Si el mensaje es None, el error ya se mostró en pantalla.
    """
    registro = consultar(
        """
        SELECT Id_inventario
        FROM INVENTARIO
        WHERE Id_producto = %s AND Id_sede = %s
        LIMIT 1
        """,
        (id_producto, id_sede)
    )

    if tipo == "Entrada":
        if registro:
            filas = ejecutar(
                """
                UPDATE INVENTARIO
                SET Existencia = Existencia + %s
                WHERE Id_inventario = %s
                """,
                (cantidad, registro[0][0])
            )
        else:
            filas = ejecutar(
                """
                INSERT INTO INVENTARIO
                (Id_producto, Existencia, Id_sede)
                VALUES (%s, %s, %s)
                """,
                (id_producto, cantidad, id_sede)
            )

        if filas is None:
            return False, None

        return True, "Entrada registrada correctamente."

    if tipo == "Salida":
        if not registro:
            return False, (
                "Ese producto no tiene existencias "
                "en la sede seleccionada."
            )

        filas = ejecutar(
            """
            UPDATE INVENTARIO
            SET Existencia = Existencia - %s
            WHERE Id_inventario = %s
              AND Existencia >= %s
            """,
            (cantidad, registro[0][0], cantidad)
        )

        if filas is None:
            return False, None

        if filas == 0:
            return False, (
                "La existencia disponible no alcanza "
                "para esa salida."
            )

        return True, "Salida registrada correctamente."

    # Ajuste: deja la existencia con el valor indicado
    if registro:
        curso.execute(
            """
            UPDATE INVENTARIO
            SET Existencia = Existencia + %s
            Id_compra= %s
            WHERE Id_inventario = %s
            """,
            (linea["cantidad"],id_compra, registro[0])
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
                id_compraa,
                id_sede
            )
        )
        conexion.comit()

    if filas is None:
        return False, None

    return True, "Existencia ajustada correctamente."


# ==============================
# PANTALLA DEL MÓDULO
# ==============================
def mostrar_inventario():
    st.header("Gestión de inventario")

    # Mensaje que se guarda antes de recargar la página
    mensaje = st.session_state.pop("mensaje_inventario", None)
    if mensaje:
        st.success(mensaje)

    sedes = obtener_sedes()

    if not sedes:
        st.warning(
            "Primero debe registrar una sede."
        )
        return

    # -----------------------------------
    # LISTADO
    # -----------------------------------
    st.subheader("Existencias por sede")

    col1, col2 = st.columns([2, 1])

    with col1:
        busqueda = st.text_input(
            "Buscar producto",
            placeholder="Nombre o ID del producto"
        )

    with col2:
        opciones_filtro = {"Todas las sedes": None}

        for sede in sedes:
            opciones_filtro[sede[1]] = sede[0]

        sede_filtro = st.selectbox(
            "Filtrar por sede",
            list(opciones_filtro.keys())
        )

    inventario = obtener_inventario(
        busqueda,
        opciones_filtro[sede_filtro]
    )

    if inventario:
        tabla = pd.DataFrame(
            [
                (
                    i[0],
                    i[2],
                    i[3],
                    i[5],
                    float(i[6]),
                    i[4]
                )
                for i in inventario
            ],
            columns=[
                "ID",
                "Producto",
                "Categoría",
                "Sede",
                "Existencia",
                "Unidad"
            ]
        )

        st.dataframe(
            tabla,
            use_container_width=True,
            hide_index=True
        )

        st.caption(
            f"Registros encontrados: {len(inventario)}"
        )
    else:
        st.info(
            "No hay existencias registradas."
        )

    st.divider()

    # -----------------------------------
    # REGISTRAR MOVIMIENTO
    # -----------------------------------
    st.subheader("Registrar movimiento")

    if st.session_state.get("id_rol") not in ROLES_PUEDEN_MOVER:
        st.info(
            "Solo los encargados del CD y de las tiendas "
            "pueden registrar movimientos de inventario."
        )
        return

    productos = obtener_productos()

    if not productos:
        st.warning(
            "Primero debe registrar productos."
        )
        return

    tipo = st.radio(
        "Tipo de movimiento",
        TIPOS_MOVIMIENTO,
        horizontal=True
    )

    # La sede del usuario aparece seleccionada por defecto
    indice_sede = next(
        (
            i for i, s in enumerate(sedes)
            if s[0] == st.session_state.get("id_sede")
        ),
        0
    )

    with st.form(f"form_movimiento_{tipo}"):
        producto = st.selectbox(
            "Producto",
            productos,
            format_func=lambda p: f"{p[0]} - {p[1]} ({p[2]})"
        )

        sede = st.selectbox(
            "Sede",
            sedes,
            index=indice_sede,
            format_func=lambda s: s[1]
        )

        if tipo == "Ajuste":
            cantidad = st.number_input(
                "Nueva existencia",
                min_value=0.0,
                step=1.0,
                format="%.2f"
            )
        else:
            cantidad = st.number_input(
                "Cantidad",
                min_value=0.0,
                step=1.0,
                format="%.2f"
            )

        guardar = st.form_submit_button(
            f"Registrar {tipo.lower()}"
        )

    if guardar:
        if tipo != "Ajuste" and cantidad <= 0:
            st.warning(
                "La cantidad debe ser mayor que cero."
            )
        else:
            guardado, resultado = aplicar_movimiento(
                tipo,
                producto[0],
                sede[0],
                cantidad
            )

            if guardado:
                st.session_state["mensaje_inventario"] = resultado
                st.rerun()
            elif resultado:
                st.warning(resultado)
