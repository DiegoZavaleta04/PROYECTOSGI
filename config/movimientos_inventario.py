"""
Funciones para mover el INVENTARIO de una sede.

Guardar este archivo en la carpeta config (por ejemplo
config/movimientos_inventario.py) y usarlo asi:

    from config.movimientos_inventario import (
        sumar_existencia,
        restar_existencia,
        ajustar_existencia,
    )

REGLAS
- El inventario es POR SEDE: siempre se indica la sede del usuario que
  inicio sesion (st.session_state["id_sede"]). Nunca se toma de un campo
  que el usuario pueda cambiar.
- Todas las funciones reciben el CURSOR ABIERTO de quien las llama (la
  compra, la venta o el ajuste). Asi el movimiento de inventario y la
  operacion se guardan JUNTOS: quien llama hace commit al final, o
  rollback si ocurre un error.
- Si algo no es valido (cantidad, existencia insuficiente...) lanzan
  ValueError con un mensaje que se puede mostrar al usuario.
"""

from decimal import Decimal


def _a_decimal(valor):
    return Decimal(str(valor))


def _buscar_fila(cursor, id_producto, id_sede):
    """Busca (y bloquea) la fila del producto en el inventario de la sede."""
    cursor.execute(
        """
        SELECT Id_inventario, Existencia
        FROM INVENTARIO
        WHERE Id_producto = %s AND Id_sede = %s
        LIMIT 1
        FOR UPDATE
        """,
        (id_producto, id_sede)
    )

    return cursor.fetchone()


def _insertar_fila(cursor, id_producto, id_sede, existencia, id_compra=None):
    """
    Crea la fila del producto en el inventario de la sede.
    La unidad de medida NO se guarda aqui: se obtiene del producto
    (PRODUCTOS.Id_unidad).
    """
    cursor.execute(
        "SELECT 1 FROM PRODUCTOS WHERE Id_producto = %s LIMIT 1",
        (id_producto,)
    )

    if cursor.fetchone() is None:
        raise ValueError("El producto no existe en el catálogo.")

    cursor.execute(
        """
        INSERT INTO INVENTARIO
        (Id_producto, Existencia, Id_compra, Id_sede)
        VALUES (%s, %s, %s, %s)
        """,
        (id_producto, existencia, id_compra, id_sede)
    )


def sumar_existencia(cursor, id_producto, id_sede, cantidad, id_compra=None):
    """
    ENTRADA: suma la cantidad al inventario de la sede.
    Si el producto aun no esta en el inventario de la sede, lo crea.
    Usar al registrar una COMPRA (pasar el id_compra).
    """
    cantidad = _a_decimal(cantidad)

    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")

    fila = _buscar_fila(cursor, id_producto, id_sede)

    if fila is None:
        _insertar_fila(cursor, id_producto, id_sede, cantidad, id_compra)
        return

    if id_compra is not None:
        cursor.execute(
            """
            UPDATE INVENTARIO
            SET Existencia = Existencia + %s,
                Id_compra = %s
            WHERE Id_inventario = %s
            """,
            (cantidad, id_compra, fila[0])
        )
    else:
        cursor.execute(
            """
            UPDATE INVENTARIO
            SET Existencia = Existencia + %s
            WHERE Id_inventario = %s
            """,
            (cantidad, fila[0])
        )


def restar_existencia(cursor, id_producto, id_sede, cantidad, id_venta=None):
    """
    SALIDA: descuenta la cantidad del inventario de la sede.
    Lanza ValueError si el producto no tiene existencias en la sede o si
    la existencia no alcanza (en ese caso no se descuenta nada).
    Usar al registrar una VENTA (pasar el id_venta).
    """
    cantidad = _a_decimal(cantidad)

    if cantidad <= 0:
        raise ValueError("La cantidad debe ser mayor que cero.")

    fila = _buscar_fila(cursor, id_producto, id_sede)

    if fila is None:
        raise ValueError("El producto no tiene existencias en esta sede.")

    existencia_actual = _a_decimal(fila[1])

    if existencia_actual < cantidad:
        raise ValueError(
            f"Existencia insuficiente. Disponible: {existencia_actual}"
        )

    if id_venta is not None:
        cursor.execute(
            """
            UPDATE INVENTARIO
            SET Existencia = Existencia - %s,
                Id_venta = %s
            WHERE Id_inventario = %s
            """,
            (cantidad, id_venta, fila[0])
        )
    else:
        cursor.execute(
            """
            UPDATE INVENTARIO
            SET Existencia = Existencia - %s
            WHERE Id_inventario = %s
            """,
            (cantidad, fila[0])
        )


def ajustar_existencia(cursor, id_producto, id_sede, nueva_existencia):
    """
    AJUSTE: deja la existencia del producto en la cantidad indicada
    (por ejemplo, despues de un conteo fisico).
    """
    nueva_existencia = _a_decimal(nueva_existencia)

    if nueva_existencia < 0:
        raise ValueError("La existencia no puede ser negativa.")

    fila = _buscar_fila(cursor, id_producto, id_sede)

    if fila is None:
        _insertar_fila(cursor, id_producto, id_sede, nueva_existencia)
        return

    cursor.execute(
        """
        UPDATE INVENTARIO
        SET Existencia = %s
        WHERE Id_inventario = %s
        """,
        (nueva_existencia, fila[0])
    )
