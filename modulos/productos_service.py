
import mysql.connector
from conexion import obtener_conexion


class ErrorProducto(Exception):
    pass


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
            u.Abreviatura
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
def crear_producto(nombre, descripcion, id_unidad, id_categoria):

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
        (Nombre, Descripcion, Id_unidad, Id_categoria)
        VALUES (%s, %s, %s, %s)
    """

    return ejecutar(
        sql,
        (nombre, descripcion, id_unidad, id_categoria)
    )


# ACTUALIZAR PRODUCTO
def actualizar_producto(
    id_producto,
    nombre,
    descripcion,
    id_unidad,
    id_categoria
):

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
            Id_categoria = %s
        WHERE Id_producto = %s
    """

    ejecutar(
        sql,
        (
            nombre,
            descripcion,
            id_unidad,
            id_categoria,
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
