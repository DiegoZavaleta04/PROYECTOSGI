
import pandas as pd
import streamlit as st

from config.conexion import obtener_conexion


# ==========================================================
# 1. ROLES Y PERMISOS
# ==========================================================

ROL_ENCARGADO_CD = 1
ROL_ENCARGADO_TIENDA = 2
ROL_VENDEDOR_CD = 3
ROL_VENDEDOR_TIENDA = 4
ROL_ADMINISTRADOR = 5

ROLES_PUEDEN_VER = (1, 2, 3, 4)
ROLES_PUEDEN_MOVER = (1, 2)

TIPOS_MOVIMIENTO = ["Entrada", "Salida", "Ajuste"]


# ==========================================================
# 2. FUNCIONES DE CONEXIÓN
# ==========================================================

def consultar(sql, parametros=None):

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(sql, parametros or ())
        resultados = cursor.fetchall()
        cursor.close()

        return resultados

    except Exception as e:
        st.error(f"Error al consultar los datos: {e}")
        return []

    finally:
        conexion.close()


def ejecutar(sql, parametros=None):

    conexion = obtener_conexion()

    try:
        cursor = conexion.cursor()
        cursor.execute(sql, parametros or ())
        conexion.commit()
        cursor.close()

        return True

    except Exception as e:
        conexion.rollback()
        st.error(f"Error al ejecutar la operación: {e}")
        return False

    finally:
        conexion.close()


# ==========================================================
# 3. OBTENER PRODUCTOS DEL CATÁLOGO COMÚN
# ==========================================================

def obtener_productos():

    sql = """
        SELECT
            Id_producto,
            Nombre
        FROM PRODUCTOS
        ORDER BY Nombre
    """

    return consultar(sql)


# ==========================================================
# 4. CONSULTAR INVENTARIO POR SEDE
# ==========================================================

def obtener_inventario(busqueda="", id_sede=None):

    sql = """
        SELECT
            I.Id_inventario,
            P.Id_producto,
            P.Nombre AS Producto,
            I.Existencia
        FROM INVENTARIO I
        INNER JOIN PRODUCTOS P
            ON I.Id_producto = P.Id_producto
        WHERE I.Id_sede = %s
    """

    parametros = [id_sede]

    if busqueda:
        sql += " AND P.Nombre LIKE %s"
        parametros.append(f"%{busqueda}%")

    sql += " ORDER BY P.Nombre"

    resultados = consultar(sql, parametros)

    columnas = [
        "ID inventario",
        "ID producto",
        "Producto",
        "Existencia"
    ]

    return pd.DataFrame(resultados, columns=columnas)


# ==========================================================
# 5. REGISTRAR MOVIMIENTOS
# ==========================================================

def aplicar_movimiento(tipo, id_producto, id_sede, cantidad):

    if tipo == "Ajuste":

        if cantidad < 0:
            st.error("La existencia no puede ser negativa.")
            return False

    else:

        if cantidad <= 0:
            st.error("La cantidad debe ser mayor que cero.")
            return False

    conexion = obtener_conexion()
    cursor = None

    try:

        cursor = conexion.cursor()

        # Buscar el producto en el inventario de la sede
        sql_buscar = """
            SELECT Id_inventario, Existencia
            FROM INVENTARIO
            WHERE Id_producto = %s
            AND Id_sede = %s
            FOR UPDATE
        """

        cursor.execute(
            sql_buscar,
            (id_producto, id_sede)
        )

        resultado = cursor.fetchone()

        # ------------------------------------------
        # ENTRADA
        # ------------------------------------------

        if tipo == "Entrada":

            if resultado:

                sql = """
                    UPDATE INVENTARIO
                    SET Existencia = Existencia + %s
                    WHERE Id_producto = %s
                    AND Id_sede = %s
                """

                cursor.execute(
                    sql,
                    (cantidad, id_producto, id_sede)
                )

            else:

                sql = """
                    INSERT INTO INVENTARIO
                    (Id_producto, Id_sede, Existencia)
                    VALUES (%s, %s, %s)
                """

                cursor.execute(
                    sql,
                    (id_producto, id_sede, cantidad)
                )

        # ------------------------------------------
        # SALIDA
        # ------------------------------------------

        elif tipo == "Salida":

            if not resultado:
                st.error(
                    "El producto no tiene existencias en esta sede."
                )
                conexion.rollback()
                return False

            existencia_actual = resultado[1]

            if existencia_actual < cantidad:
                st.error(
                    f"Existencia insuficiente. "
                    f"Disponible: {existencia_actual}"
                )
                conexion.rollback()
                return False

            sql = """
                UPDATE INVENTARIO
                SET Existencia = Existencia - %s
                WHERE Id_producto = %s
                AND Id_sede = %s
            """

            cursor.execute(
                sql,
                (cantidad, id_producto, id_sede)
            )

        # ------------------------------------------
        # AJUSTE
        # ------------------------------------------

        elif tipo == "Ajuste":

            if resultado:

                sql = """
                    UPDATE INVENTARIO
                    SET Existencia = %s
                    WHERE Id_producto = %s
                    AND Id_sede = %s
                """

                cursor.execute(
                    sql,
                    (cantidad, id_producto, id_sede)
                )

            else:

                sql = """
                    INSERT INTO INVENTARIO
                    (Id_producto, Id_sede, Existencia)
                    VALUES (%s, %s, %s)
                """

                cursor.execute(
                    sql,
                    (id_producto, id_sede, cantidad)
                )

        conexion.commit()
        return True

    except Exception as e:

        conexion.rollback()
        st.error(f"Error al registrar el movimiento: {e}")
        return False

    finally:

        if cursor:
            cursor.close()

        conexion.close()


# ==========================================================
# 6. MOSTRAR MÓDULO DE INVENTARIO
# ==========================================================

def mostrar_inventario():

    id_rol = st.session_state.get("id_rol")
    id_sede_usuario = st.session_state.get("id_sede")

    # ------------------------------------------
    # VALIDAR ROL Y SEDE
    # ------------------------------------------

    try:
        id_rol = int(id_rol)
        id_sede_usuario = int(id_sede_usuario)

    except (TypeError, ValueError):
        st.error("No se pudo identificar el rol o la sede del usuario.")
        return

    if id_rol not in ROLES_PUEDEN_VER:
        st.error("No tienes permisos para acceder al inventario.")
        return

    # ------------------------------------------
    # ENCABEZADO
    # ------------------------------------------

    st.title("Control de inventario")

    st.write(
        "Consulta las existencias de los productos "
        "correspondientes a tu sede."
    )

    # ------------------------------------------
    # CONSULTAR EXISTENCIAS
    # ------------------------------------------

    st.subheader("Existencias disponibles")

    busqueda = st.text_input(
        "Buscar producto",
        placeholder="Escribe el nombre del producto..."
    )

    df = obtener_inventario(
        busqueda,
        id_sede_usuario
    )

    if df.empty:

        st.info(
            "No hay productos registrados en el inventario de esta sede."
        )

    else:

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

    # ------------------------------------------
    # PERMISOS PARA MOVIMIENTOS
    # ------------------------------------------

    if id_rol not in ROLES_PUEDEN_MOVER:

        st.info(
            "Tu rol permite consultar el inventario, "
            "pero no registrar movimientos."
        )

        return

    # ------------------------------------------
    # FORMULARIO DE MOVIMIENTOS
    # ------------------------------------------

    st.divider()

    st.subheader("Registrar movimiento")

    productos = obtener_productos()

    if not productos:
        st.warning("No hay productos registrados en el catálogo.")
        return

    opciones_productos = {
        f"{producto[1]} (ID: {producto[0]})": producto[0]
        for producto in productos
    }

    with st.form("form_movimiento_inventario"):

        tipo = st.selectbox(
            "Tipo de movimiento",
            TIPOS_MOVIMIENTO
        )

        producto_seleccionado = st.selectbox(
            "Producto",
            list(opciones_productos.keys())
        )

        if tipo == "Ajuste":

            cantidad = st.number_input(
                "Nueva existencia",
                min_value=0,
                step=1
            )

        else:

            cantidad = st.number_input(
                "Cantidad",
                min_value=1,
                step=1
            )

        guardar = st.form_submit_button(
            "Registrar movimiento",
            use_container_width=True
        )

        if guardar:

            id_producto = opciones_productos[
                producto_seleccionado
            ]

            resultado = aplicar_movimiento(
                tipo,
                id_producto,
                id_sede_usuario,
                cantidad
            )

            if resultado:

                st.success("Movimiento registrado correctamente.")
                st.rerun()
