"""
Precio al que el Centro de Distribucion (CD) le vende a una tienda, y
comprobacion de que le conviene a la tienda.
Guardar este archivo como config/precios_cd.py

REGLA
    precio del CD a la tienda = costo del CD x (1 + MARGEN_OPERATIVO)
    El CD solo puede venderle a la tienda si ese precio es MENOR que el
    mejor precio al que la tienda compra el producto a sus otros
    proveedores.

COSTO DEL CD (METODO_COSTO)
    "promedio": costo promedio ponderado de todas las compras del CD de
                ese producto (el "costo global" del documento).
    "ultimo":   precio de la compra mas reciente del CD.

PRECIO DE REFERENCIA DE LA TIENDA
    Para cada proveedor de la tienda (menos el CD) se toma el precio de su
    compra mas reciente de ese producto, y de todos ellos el MENOR.

Todos los precios son por unidad de venta del producto (asi se guardan en
DETALLE_COMPRA.precio_compra).

USO (por ejemplo, en el modulo de ventas, cuando el cliente es una tienda):

    from config.precios_cd import evaluar_precio_cd

    r = evaluar_precio_cd(id_producto, id_tienda)
    if r["permitido"]:
        precio = r["precio_cd"]       # precio que se le cobra a la tienda
    else:
        st.warning(r["mensaje"])      # no se puede vender ese producto
"""

from decimal import ROUND_CEILING, Decimal

from config.conexion import obtener_conexion


# ==============================
# PARAMETROS (AJUSTAR)
# ==============================
# Margen de gastos operativos sobre el costo del CD.
# 0.08 = 8 %. !! Es un valor de ejemplo: definanlo con el ingeniero !!
MARGEN_OPERATIVO = Decimal("0.08")

METODO_COSTO = "promedio"       # "promedio" o "ultimo"

# Decimales del precio. Debe coincidir con la columna de la base
# (DETALLE_VENTA.Precio_venta). Con DECIMAL(x,2) use "0.01"; si la
# cambian a DECIMAL(x,4), use "0.0001".
# El precio se redondea HACIA ARRIBA, para que el CD nunca cobre menos
# que su costo mas el margen.
DECIMALES = Decimal("0.01")


def _fmt(valor):
    """Muestra un precio con los mismos decimales de DECIMALES."""
    cifras = max(0, -DECIMALES.as_tuple().exponent)

    return f"{valor:,.{cifras}f}"


# ==============================
# CONSULTAS
# ==============================
def _a_decimal(valor):
    return Decimal(str(valor))


def _nombre_cd(cursor):
    cursor.execute(
        "SELECT nombre FROM Sede WHERE Tipo = 'CD' LIMIT 1"
    )
    fila = cursor.fetchone()

    return fila[0] if fila else None


def costo_cd(cursor, id_producto):
    """Costo al que el CD adquiere el producto, o None si no lo ha comprado."""
    if METODO_COSTO == "ultimo":
        cursor.execute(
            """
            SELECT d.precio_compra
            FROM DETALLE_COMPRA d
            INNER JOIN COMPRAS c ON d.Id_compra = c.Id_compra
            INNER JOIN Sede s ON c.Id_sede = s.id_sede
            WHERE s.Tipo = 'CD' AND d.Id_producto = %s
            ORDER BY c.Fecha DESC, c.Id_compra DESC
            LIMIT 1
            """,
            (id_producto,)
        )
    else:
        cursor.execute(
            """
            SELECT SUM(d.Cantidad * d.precio_compra) / SUM(d.Cantidad)
            FROM DETALLE_COMPRA d
            INNER JOIN COMPRAS c ON d.Id_compra = c.Id_compra
            INNER JOIN Sede s ON c.Id_sede = s.id_sede
            WHERE s.Tipo = 'CD' AND d.Id_producto = %s
            """,
            (id_producto,)
        )

    fila = cursor.fetchone()

    if fila is None or fila[0] is None:
        return None

    return _a_decimal(fila[0])


def mejor_precio_proveedor_tienda(cursor, id_producto, id_tienda):
    """
    Menor de los ultimos precios que la tienda pago a sus proveedores
    (sin contar al CD), o None si la tienda nunca ha comprado el producto
    a otro proveedor.
    """
    nombre_cd = _nombre_cd(cursor)

    cursor.execute(
        """
        SELECT c.Id_proveedor, d.precio_compra
        FROM DETALLE_COMPRA d
        INNER JOIN COMPRAS c ON d.Id_compra = c.Id_compra
        INNER JOIN PROVEEDORES pr ON c.Id_proveedor = pr.Id_proveedor
        WHERE c.Id_sede = %s
          AND d.Id_producto = %s
          AND pr.Nombre <> %s
        ORDER BY c.Fecha DESC, c.Id_compra DESC
        """,
        (id_tienda, id_producto, nombre_cd or "")
    )

    # Las filas vienen de la mas reciente a la mas antigua: se queda con
    # la primera de cada proveedor
    ultimo_por_proveedor = {}

    for id_proveedor, precio in cursor.fetchall():
        if id_proveedor not in ultimo_por_proveedor:
            ultimo_por_proveedor[id_proveedor] = _a_decimal(precio)

    if not ultimo_por_proveedor:
        return None

    return min(ultimo_por_proveedor.values())


# ==============================
# EVALUACION
# ==============================
def _resultado(permitido, mensaje, costo=None, precio=None, referencia=None):
    return {
        "permitido": permitido,
        "costo_cd": costo,
        "precio_cd": precio,
        "precio_referencia": referencia,
        "mensaje": mensaje,
    }


def _evaluar(cursor, id_producto, id_tienda):
    costo = costo_cd(cursor, id_producto)

    if costo is None:
        return _resultado(
            False,
            "El CD no tiene compras registradas de este producto, "
            "por lo que no se puede calcular su costo."
        )

    precio_cd = (costo * (1 + MARGEN_OPERATIVO)).quantize(
        DECIMALES, rounding=ROUND_CEILING
    )

    referencia = mejor_precio_proveedor_tienda(
        cursor, id_producto, id_tienda
    )

    if referencia is None:
        return _resultado(
            True,
            "La tienda no tiene el precio de otro proveedor para "
            "comparar; se vende al precio del CD.",
            costo, precio_cd, None
        )

    if precio_cd < referencia:
        return _resultado(
            True,
            f"Precio del CD ${_fmt(precio_cd)} menor que el de su "
            f"proveedor ${_fmt(referencia)}.",
            costo, precio_cd, referencia
        )

    return _resultado(
        False,
        f"No se puede vender: el precio del CD (${_fmt(precio_cd)}) "
        f"no es menor que el de los proveedores de la tienda "
        f"(${_fmt(referencia)}).",
        costo, precio_cd, referencia
    )


def evaluar_precio_cd(id_producto, id_tienda, cursor=None):
    """
    Devuelve un diccionario con:
      permitido          True/False
      costo_cd           costo al que el CD adquiere el producto (o None)
      precio_cd          costo + margen operativo (o None)
      precio_referencia  mejor precio de los proveedores de la tienda (o None)
      mensaje            texto para mostrar al usuario

    Si se pasa un cursor (por ejemplo, dentro de la transaccion de la
    venta) se usa ese; si no, abre su propia conexion.
    """
    if cursor is not None:
        return _evaluar(cursor, id_producto, id_tienda)

    conexion = obtener_conexion()

    if conexion is None:
        return _resultado(
            False,
            "No se pudo conectar con la base de datos."
        )

    cursor_propio = None

    try:
        cursor_propio = conexion.cursor()
        return _evaluar(cursor_propio, id_producto, id_tienda)

    finally:
        if cursor_propio is not None:
            cursor_propio.close()

        conexion.close()
