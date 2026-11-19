import mysql.connector
from config.conexion import obtener_conexion


class ErrorProducto(Exception):
    pass


# Reglas de venta: lo mas pequeno que se puede vender de un producto.
#   1    -> solo cantidades enteras (1, 2, 3...)
#   0.5  -> medias (0.5, 1, 1.5...)
#   0.25 -> hasta cuartos (0.25, 0.5, 0.75, 1...)
INCREMENTOS_VENTA = (1.0, 0.5, 0.25)


def validar_incremento(incremento):
    """Devuelve el incremento como float, o lanza ErrorProducto."""
    try:
        valor = float(incremento)
    except (TypeError, ValueError):
        raise ErrorProducto("La regla de venta no es válida.")

    if valor not in INCREMENTOS_VENTA:
        raise ErrorProducto(
            "La regla de venta debe ser 1, 0.5 o 0.25."
        )

    return valor


def consultar(sql, parametros=()):
    conexion = obtener_conexion()

    if conexion is None:
        raise ErrorProducto("No hay conexión con la base de datos.")

    cursor = None

    try:
        cursor = conexion.cursor(dictionary=True)
        cursor.execute(sql, parametros)
        return cursor.fetchall()

    except mysql.connector.Error as error:
        raise ErrorProducto(str(error)) from error

    finally:
        if cursor:
            cursor.close()
        conexion.close()


def ejecutar(sql, parametros=()):
    conexion = obtener_conexion()

    if conexion is None:
        raise ErrorProducto("No hay conexión con la base de datos.")

    cursor = None

    try:
        cursor = conexion.cursor()
        cursor.execute(sql, parametros)
        conexion.commit()
        return cursor.lastrowid

    except mysql.connector.Error as error:
        conexion.rollback()
        raise ErrorProducto(str(error)) from error

    finally:
        if cursor:
            cursor.close()
        conexion.close()


# CONSULTAR PRODUCTOS
def listar_productos(busqueda="", id_categoria=None):

    sql = """
        SELECT
            p.Id_producto,
            p.Nombre,
            p.Descripcion,
            p.Id_unidad,
            p.Id_categoria,
            c.nombre AS Categoria,
            u.Nombre AS Unidad,
            u.Abreviatura,
            p.Incremento_venta
        FROM PRODUCTOS p
        INNER JOIN Categoria c
            ON p.Id_categoria = c.id_categoria
        INNER JOIN UNIDAD_MEDIDA u
            ON p.Id_unidad = u.Id_unidad
        WHERE
            (%s = '' OR p.Nombre LIKE %s
             OR p.Descripcion LIKE %s
             OR CAST(p.Id_producto AS CHAR) LIKE %s)
            AND (%s IS NULL OR p.Id_categoria = %s)
        ORDER BY p.Nombre
    """

    termino = f"%{busqueda.strip()}%"

    return consultar(
        sql,
        (
            busqueda.strip(),
            termino,
            termino,
            termino,
            id_categoria,
            id_categoria
        )
    )


# CONSULTAR CATEGORIAS
def listar_categorias():

    sql = """
        SELECT id_categoria, nombre
        FROM Categoria
        ORDER BY nombre
    """

    return consultar(sql)


# CONSULTAR UNIDADES
def listar_unidades():

    sql = """
        SELECT Id_unidad, Nombre, Abreviatura
        FROM UNIDAD_MEDIDA
        ORDER BY Nombre
    """

    return consultar(sql)


# REGISTRAR PRODUCTO
def crear_producto(
    nombre,
    descripcion,
    id_unidad,
    id_categoria,
    incremento_venta=1
):

    incremento_venta = validar_incremento(incremento_venta)

    nombre = " ".join((nombre or "").split())
    descripcion = (descripcion or "").strip() or None

    if not nombre:
        raise ErrorProducto("El nombre es obligatorio.")

    if len(nombre) > 100:
        raise ErrorProducto("El nombre admite máximo 100 caracteres.")

    if descripcion and len(descripcion) > 255:
        raise ErrorProducto("La descripción admite máximo 255 caracteres.")

    if not id_unidad or not id_categoria:
        raise ErrorProducto("Selecciona una categoría y una unidad.")

    sql = """
        INSERT INTO PRODUCTOS
        (Nombre, Descripcion, Id_unidad, Id_categoria, Incremento_venta)
        VALUES (%s, %s, %s, %s, %s)
    """

    return ejecutar(
        sql,
        (nombre, descripcion, id_unidad, id_categoria, incremento_venta)
    )


# ACTUALIZAR PRODUCTO
def actualizar_producto(
    id_producto,
    nombre,
    descripcion,
    id_unidad,
    id_categoria,
    incremento_venta=None
):
    """
    Si incremento_venta es None, la regla de venta actual no se modifica.
    """

    if incremento_venta is not None:
        incremento_venta = validar_incremento(incremento_venta)

    nombre = " ".join((nombre or "").split())
    descripcion = (descripcion or "").strip() or None

    if not nombre:
        raise ErrorProducto("El nombre es obligatorio.")

    if len(nombre) > 100:
        raise ErrorProducto("El nombre admite máximo 100 caracteres.")

    if descripcion and len(descripcion) > 255:
        raise ErrorProducto("La descripción admite máximo 255 caracteres.")

    if not id_unidad or not id_categoria:
        raise ErrorProducto("Selecciona una categoría y una unidad.")

    sql = """
        UPDATE PRODUCTOS
        SET Nombre = %s,
            Descripcion = %s,
            Id_unidad = %s,
            Id_categoria = %s,
            Incremento_venta = COALESCE(%s, Incremento_venta)
        WHERE Id_producto = %s
    """

    ejecutar(
        sql,
        (
            nombre,
            descripcion,
            id_unidad,
            id_categoria,
            incremento_venta,
            id_producto
        )
    )


# REGISTRAR CATEGORIA
def crear_categoria(nombre):

    nombre = " ".join((nombre or "").split())

    if not nombre:
        raise ErrorProducto("El nombre de la categoría es obligatorio.")

    if len(nombre) > 80:
        raise ErrorProducto("Máximo 80 caracteres.")

    ejecutar(
        "INSERT INTO Categoria (nombre) VALUES (%s)",
        (nombre,)
    )


# REGISTRAR UNIDAD DE MEDIDA
def crear_unidad(nombre, abreviatura):

    nombre = " ".join((nombre or "").split())
    abreviatura = " ".join((abreviatura or "").split())

    if not nombre or not abreviatura:
        raise ErrorProducto("Completa todos los campos.")

    if len(nombre) > 50 or len(abreviatura) > 10:
        raise ErrorProducto("Verifica la longitud de los campos.")

    ejecutar(
        """
        INSERT INTO UNIDAD_MEDIDA
        (Nombre, Abreviatura)
        VALUES (%s, %s)
        """,
        (nombre, abreviatura)
    )
