from datetime import date

import altair as alt
import pandas as pd
import streamlit as st
from config.conexion import obtener_conexion


# ==============================
# CONFIGURACION
# ==============================
CLAVE_ROL = "id_rol"
CLAVE_SEDE = "id_sede"

# Roles que ven TODAS las sedes (Encargado CD y Administrador)
ROLES_COMPLETO = (1, 5)

# Roles que solo ven SU sede (la de su usuario)
ROLES_UNA_SEDE = (2,)

# Cuantos productos se muestran en los rankings
TOP_PRODUCTOS = 10

# Existencia a partir de la cual un producto se considera "bajo stock"
UMBRAL_STOCK_BAJO = 10

# Segundos que se guardan los datos antes de volver a consultar la base.
# El boton "Actualizar datos" los refresca al instante.
SEGUNDOS_CACHE = 120


# ==============================
# BASE DE DATOS Y PERMISOS
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


def tiene_acceso():
    """True si el rol del usuario puede entrar a los informes."""
    return st.session_state.get(CLAVE_ROL) in ROLES_COMPLETO + ROLES_UNA_SEDE


def ve_solo_su_sede():
    """True si el rol del usuario solo puede ver los datos de su sede."""
    return st.session_state.get(CLAVE_ROL) in ROLES_UNA_SEDE


def a_dataframe(filas, columnas, decimales=(), enteras=()):
    df = pd.DataFrame([tuple(f) for f in filas], columns=columnas)

    for c in decimales:
        df[c] = df[c].astype(float)

    for c in enteras:
        df[c] = df[c].astype(int)

    return df


# Se consulta pocas veces y se guarda en cache: la base solo permite
# unas pocas conexiones abiertas a la vez.
@st.cache_data(ttl=SEGUNDOS_CACHE, show_spinner=False)
def cargar_sedes():
    filas = consultar(
        "SELECT id_sede, nombre, tipo FROM Sede ORDER BY nombre"
    )

    return a_dataframe(
        filas,
        ["id_sede", "sede", "tipo"],
        enteras=["id_sede"]
    )


@st.cache_data(ttl=SEGUNDOS_CACHE, show_spinner=False)
def cargar_ventas(desde, hasta):
    """Una fila por cada producto vendido, dentro del rango de fechas."""
    filas = consultar(
        """
        SELECT
            v.Id_venta,
            v.Fecha,
            v.Id_sede,
            v.Metodo_pago,
            d.Id_producto,
            p.Nombre,
            d.Cantidad,
            d.Precio_venta,
            COALESCE(ud.Abreviatura, ub.Abreviatura)
        FROM VENTAS v
        INNER JOIN DETALLE_VENTA d
            ON d.Id_venta = v.Id_venta
        INNER JOIN PRODUCTOS p
            ON d.Id_producto = p.Id_producto
        INNER JOIN UNIDAD_MEDIDA ub
            ON p.Id_unidad = ub.Id_unidad
        LEFT JOIN UNIDAD_MEDIDA ud
            ON d.Id_unidad = ud.Id_unidad
        WHERE v.Fecha BETWEEN %s AND %s
        """,
        (desde, hasta)
    )

    df = a_dataframe(
        filas,
        [
            "id_venta", "fecha", "id_sede", "metodo",
            "id_producto", "producto", "cantidad", "precio", "unidad"
        ],
        decimales=["cantidad", "precio"],
        enteras=["id_venta", "id_sede", "id_producto"]
    )
    df["fecha"] = pd.to_datetime(df["fecha"])

    return df


@st.cache_data(ttl=SEGUNDOS_CACHE, show_spinner=False)
def cargar_compras():
    """
    Todas las compras (no solo las del periodo): sirven para calcular
    el costo promedio de cada producto.
    """
    filas = consultar(
        """
        SELECT
            c.Id_compra,
            c.Fecha,
            c.Id_sede,
            d.Id_producto,
            d.Cantidad,
            d.precio_compra
        FROM COMPRAS c
        INNER JOIN DETALLE_COMPRA d
            ON d.Id_compra = c.Id_compra
        """
    )

    df = a_dataframe(
        filas,
        [
            "id_compra", "fecha", "id_sede",
            "id_producto", "cantidad", "precio"
        ],
        decimales=["cantidad", "precio"],
        enteras=["id_compra", "id_sede", "id_producto"]
    )
    df["fecha"] = pd.to_datetime(df["fecha"])

    return df


@st.cache_data(ttl=SEGUNDOS_CACHE, show_spinner=False)
def cargar_inventario():
    filas = consultar(
        """
        SELECT
            i.Id_sede,
            i.Id_producto,
            p.Nombre,
            i.Existencia,
            u.Abreviatura
        FROM INVENTARIO i
        INNER JOIN PRODUCTOS p
            ON i.Id_producto = p.Id_producto
        INNER JOIN UNIDAD_MEDIDA u
            ON p.Id_unidad = u.Id_unidad
        """
    )

    return a_dataframe(
        filas,
        ["id_sede", "id_producto", "producto", "existencia", "unidad"],
        decimales=["existencia"],
        enteras=["id_sede", "id_producto"]
    )


# ==============================
# CALCULOS
# ==============================
def calcular_costos(compras):
    """
    Costo promedio de compra por unidad de cada producto:
    - por sede (lo que esa sede pago por el producto), y
    - global (promedio de todas las sedes), para cuando una sede
      vende algo que no tiene compras registradas.
    """
    if compras.empty:
        return compras.head(0), compras.head(0)

    c = compras.copy()
    c["total"] = c["cantidad"] * c["precio"]

    por_sede = c.groupby(["id_sede", "id_producto"], as_index=False).agg(
        total=("total", "sum"),
        cant=("cantidad", "sum")
    )
    por_sede["costo_sede"] = (
        por_sede["total"] / por_sede["cant"].where(por_sede["cant"] > 0)
    )

    glob = c.groupby("id_producto", as_index=False).agg(
        total=("total", "sum"),
        cant=("cantidad", "sum")
    )
    glob["costo_global"] = (
        glob["total"] / glob["cant"].where(glob["cant"] > 0)
    )

    return (
        por_sede[["id_sede", "id_producto", "costo_sede"]],
        glob[["id_producto", "costo_global"]]
    )


def agregar_costos(df, por_sede, glob):
    """Agrega costo_unit (y sin_costo) a un DataFrame con id_sede e id_producto."""
    df = df.copy()

    if df.empty or por_sede.empty:
        df["costo_unit"] = 0.0
        df["sin_costo"] = True
        return df

    df = df.merge(por_sede, on=["id_sede", "id_producto"], how="left")
    df = df.merge(glob, on="id_producto", how="left")

    costo = df["costo_sede"].fillna(df["costo_global"])

    df["sin_costo"] = costo.isna()
    df["costo_unit"] = costo.fillna(0.0)

    return df.drop(columns=["costo_sede", "costo_global"])


def resumen_sedes(sedes, v, compras_p, inv):
    """Una fila por sede con sus indicadores del periodo."""
    ventas = v.groupby("id_sede").agg(
        ventas=("id_venta", "nunique"),
        ingresos=("ingreso", "sum"),
        costo=("costo", "sum"),
        ganancia=("ganancia", "sum")
    )

    compras = compras_p.groupby("id_sede")["total"].sum().rename("compras")
    inventario = inv.groupby("id_sede")["valor"].sum().rename("inventario")

    r = (
        sedes.set_index("id_sede")[["sede", "tipo"]]
        .join(ventas)
        .join(compras)
        .join(inventario)
    )

    for c in ["ventas", "ingresos", "costo", "ganancia",
              "compras", "inventario"]:
        r[c] = r[c].fillna(0)

    r["margen"] = (
        r["ganancia"] / r["ingresos"].where(r["ingresos"] > 0) * 100
    ).fillna(0)

    return r.reset_index()


def preparar(sedes, ventas, compras, inventario, desde, hasta):
    por_sede, glob = calcular_costos(compras)

    v = agregar_costos(ventas, por_sede, glob)
    v["ingreso"] = v["cantidad"] * v["precio"]
    v["costo"] = v["cantidad"] * v["costo_unit"]
    v["ganancia"] = v["ingreso"] - v["costo"]
    v["mes"] = v["fecha"].dt.strftime("%Y-%m")
    v = v.merge(sedes[["id_sede", "sede"]], on="id_sede", how="left")

    inv = agregar_costos(inventario, por_sede, glob)
    inv["valor"] = inv["existencia"] * inv["costo_unit"]

    compras_p = compras[
        (compras["fecha"] >= pd.Timestamp(desde))
        & (compras["fecha"] <= pd.Timestamp(hasta))
    ].copy()
    compras_p["total"] = compras_p["cantidad"] * compras_p["precio"]

    resumen = resumen_sedes(sedes, v, compras_p, inv)

    return v, compras_p, inv, resumen


def margen_porcentaje(ganancia, ingresos):
    return ganancia / ingresos * 100 if ingresos > 0 else 0.0


# ==============================
# COMPONENTES VISUALES
# ==============================
def dinero(valor):
    return f"${valor:,.2f}"


def fila_kpis(indicadores):
    columnas = st.columns(len(indicadores))

    for columna, (titulo, valor, ayuda) in zip(columnas, indicadores):
        columna.metric(titulo, valor, help=ayuda)


def barras(df, categoria, valor, titulo, etiqueta, horizontal=False,
           formato=",.2f"):
    """Grafico de barras ordenado de mayor a menor."""
    if df.empty:
        st.info("No hay datos para graficar en este periodo.")
        return

    df = df.copy()
    df[categoria] = df[categoria].astype(str)

    if horizontal:
        x = alt.X(f"{valor}:Q", title=etiqueta)
        y = alt.Y(f"{categoria}:N", sort="-x", title=None)
    else:
        x = alt.X(
            f"{categoria}:N",
            sort="-y",
            title=None,
            axis=alt.Axis(labelAngle=-30)
        )
        y = alt.Y(f"{valor}:Q", title=etiqueta)

    grafico = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=x,
            y=y,
            tooltip=[
                alt.Tooltip(f"{categoria}:N", title="Detalle"),
                alt.Tooltip(f"{valor}:Q", title=etiqueta, format=formato)
            ]
        )
        .properties(title=titulo, height=300)
    )

    st.altair_chart(grafico, use_container_width=True)


def grafico_top_productos(v, clave):
    modo = st.radio(
        "Ordenar los productos por",
        ["Unidades vendidas", "Ingresos ($)", "Ganancia ($)"],
        horizontal=True,
        key=f"orden_productos_{clave}"
    )

    campo = {
        "Unidades vendidas": "cantidad",
        "Ingresos ($)": "ingreso",
        "Ganancia ($)": "ganancia"
    }[modo]

    if v.empty:
        st.info("No hay ventas en este periodo.")
        return

    top = (
        v.groupby("producto", as_index=False)
        .agg(
            cantidad=("cantidad", "sum"),
            ingreso=("ingreso", "sum"),
            ganancia=("ganancia", "sum")
        )
        .sort_values(campo, ascending=False)
        .head(TOP_PRODUCTOS)
    )

    barras(
        top,
        "producto",
        campo,
        f"Top {TOP_PRODUCTOS} productos más vendidos",
        modo,
        horizontal=True
    )

    if campo == "cantidad":
        st.caption(
            "Las unidades mezclan libras, unidades, etc. "
            "Para comparar productos distintos conviene usar Ingresos."
        )


def resumen_ejecutivo(resumen, v, inv):
    """Conclusiones en texto, listas para presentar a gerencia."""
    ingresos = resumen["ingresos"].sum()

    if ingresos <= 0:
        return ["No hay ventas registradas en el periodo seleccionado."]

    ganancia = resumen["ganancia"].sum()
    margen = margen_porcentaje(ganancia, ingresos)

    lineas = [
        f"En el periodo se vendieron **{dinero(ingresos)}** y la ganancia "
        f"bruta estimada fue de **{dinero(ganancia)}** "
        f"(margen de **{margen:.1f}%**)."
    ]

    con_ventas = resumen[resumen["ingresos"] > 0]

    mejor = con_ventas.loc[con_ventas["ganancia"].idxmax()]
    participacion = (
        mejor["ganancia"] / ganancia * 100 if ganancia > 0 else 0
    )
    lineas.append(
        f"La sede con mayor ganancia es **{mejor['sede']}** "
        f"({dinero(mejor['ganancia'])}, {participacion:.0f}% del total)."
    )

    if len(con_ventas) > 1:
        mayor_margen = con_ventas.loc[con_ventas["margen"].idxmax()]
        menor_margen = con_ventas.loc[con_ventas["margen"].idxmin()]

        lineas.append(
            f"Mayor margen: **{mayor_margen['sede']}** "
            f"({mayor_margen['margen']:.1f}%). "
            f"Menor margen: **{menor_margen['sede']}** "
            f"({menor_margen['margen']:.1f}%)."
        )

    sin_ventas = resumen[resumen["ingresos"] <= 0]["sede"].tolist()

    if sin_ventas:
        lineas.append(
            "Sedes sin ventas en el periodo: **"
            + ", ".join(sin_ventas)
            + "**."
        )

    por_producto = v.groupby("producto")["ingreso"].sum()
    estrella = por_producto.idxmax()
    lineas.append(
        f"El producto que más ingresos genera es **{estrella}** "
        f"({dinero(por_producto.max())})."
    )

    sin_existencia = int((inv["existencia"] <= 0).sum())
    bajo_stock = int(
        ((inv["existencia"] > 0) & (inv["existencia"] <= UMBRAL_STOCK_BAJO))
        .sum()
    )

    if sin_existencia or bajo_stock:
        lineas.append(
            f"Alerta de inventario: **{sin_existencia}** productos sin "
            f"existencia y **{bajo_stock}** con existencia baja "
            f"(menos de {UMBRAL_STOCK_BAJO + 1})."
        )

    if v["sin_costo"].any():
        ingreso_sin_costo = v.loc[v["sin_costo"], "ingreso"].sum()
        lineas.append(
            f"Atención: {dinero(ingreso_sin_costo)} de las ventas son de "
            "productos sin compras registradas, por lo que su costo se "
            "tomó como $0 y la ganancia de ese monto está sobrestimada."
        )

    return lineas


# ==============================
# BALANCE GENERAL
# ==============================
def mostrar_balance(v, compras_p, inv, resumen):
    ingresos = resumen["ingresos"].sum()
    ganancia = resumen["ganancia"].sum()
    n_ventas = int(resumen["ventas"].sum())
    compras_total = resumen["compras"].sum()

    fila_kpis([
        ("Ingresos por ventas", dinero(ingresos),
         "Total vendido en el periodo."),
        ("Ganancia bruta estimada", dinero(ganancia),
         "Ventas menos el costo promedio de compra de lo vendido."),
        ("Margen de ganancia",
         f"{margen_porcentaje(ganancia, ingresos):.1f}%",
         "Ganancia bruta entre ingresos."),
        ("Cantidad de ventas", f"{n_ventas:,}",
         "Número de ventas registradas."),
    ])

    fila_kpis([
        ("Ticket promedio",
         dinero(ingresos / n_ventas if n_ventas else 0),
         "Monto promedio por venta."),
        ("Compras del periodo", dinero(compras_total),
         "Dinero invertido en compras a proveedores."),
        ("Ingresos menos compras", dinero(ingresos - compras_total),
         "Flujo neto: lo vendido menos lo comprado en el periodo."),
        ("Valor del inventario", dinero(resumen["inventario"].sum()),
         "Existencias actuales valoradas a su costo promedio."),
    ])

    st.subheader("Resumen ejecutivo")

    for linea in resumen_ejecutivo(resumen, v, inv):
        st.markdown(f"- {linea}")

    st.subheader("Comparativo entre sedes")

    c1, c2 = st.columns(2)

    with c1:
        barras(resumen, "sede", "ingresos",
               "Ingresos por sede", "Ingresos ($)")

    with c2:
        barras(resumen, "sede", "ganancia",
               "Ganancia bruta por sede", "Ganancia ($)")

    c3, c4 = st.columns(2)

    with c3:
        barras(resumen, "sede", "ventas",
               "Cantidad de ventas por sede", "Ventas", formato=",.0f")

    with c4:
        barras(resumen, "sede", "margen",
               "Margen de ganancia por sede", "Margen (%)", formato=".1f")

    st.subheader("Evolución mensual")

    if v.empty:
        st.info("No hay ventas en este periodo.")
    else:
        e1, e2 = st.columns(2)

        with e1:
            st.caption("Ingresos por mes y sede ($)")
            st.line_chart(
                v.pivot_table(
                    index="mes",
                    columns="sede",
                    values="ingreso",
                    aggfunc="sum"
                ).fillna(0)
            )

        with e2:
            st.caption("Ingresos y ganancia totales por mes ($)")
            st.line_chart(
                v.groupby("mes")[["ingreso", "ganancia"]]
                .sum()
                .rename(columns={
                    "ingreso": "Ingresos",
                    "ganancia": "Ganancia"
                })
            )

    st.subheader("Productos más vendidos (todas las sedes)")
    grafico_top_productos(v, "general")

    st.subheader("Tabla comparativa")

    tabla = resumen.rename(columns={
        "sede": "Sede",
        "tipo": "Tipo",
        "ventas": "Ventas",
        "ingresos": "Ingresos ($)",
        "costo": "Costo de lo vendido ($)",
        "ganancia": "Ganancia bruta ($)",
        "margen": "Margen (%)",
        "compras": "Compras ($)",
        "inventario": "Valor inventario ($)"
    })[[
        "Sede", "Tipo", "Ventas", "Ingresos ($)",
        "Costo de lo vendido ($)", "Ganancia bruta ($)", "Margen (%)",
        "Compras ($)", "Valor inventario ($)"
    ]].sort_values("Ganancia bruta ($)", ascending=False)

    st.dataframe(
        tabla,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Ventas": st.column_config.NumberColumn(format="%d"),
            "Ingresos ($)": st.column_config.NumberColumn(format="$%.2f"),
            "Costo de lo vendido ($)":
                st.column_config.NumberColumn(format="$%.2f"),
            "Ganancia bruta ($)":
                st.column_config.NumberColumn(format="$%.2f"),
            "Margen (%)": st.column_config.NumberColumn(format="%.1f%%"),
            "Compras ($)": st.column_config.NumberColumn(format="$%.2f"),
            "Valor inventario ($)":
                st.column_config.NumberColumn(format="$%.2f"),
        }
    )

    st.download_button(
        "Descargar comparativo (CSV)",
        tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name="comparativo_sedes.csv",
        mime="text/csv"
    )


# ==============================
# INFORME POR SEDE
# ==============================
def mostrar_sede(fila, v, compras_p, inv):
    """fila = fila de `resumen` de la sede; v, compras_p, inv ya filtrados."""
    clave = str(int(fila["id_sede"]))

    ingresos = fila["ingresos"]
    ganancia = fila["ganancia"]
    n_ventas = int(fila["ventas"])

    st.caption(f"Tipo de sede: {fila['tipo']}")

    fila_kpis([
        ("Ingresos por ventas", dinero(ingresos), None),
        ("Ganancia bruta estimada", dinero(ganancia), None),
        ("Margen de ganancia",
         f"{margen_porcentaje(ganancia, ingresos):.1f}%", None),
        ("Cantidad de ventas", f"{n_ventas:,}", None),
    ])

    fila_kpis([
        ("Ticket promedio",
         dinero(ingresos / n_ventas if n_ventas else 0), None),
        ("Compras del periodo", dinero(fila["compras"]), None),
        ("Ingresos menos compras",
         dinero(ingresos - fila["compras"]), None),
        ("Valor del inventario", dinero(fila["inventario"]), None),
    ])

    if v.empty:
        st.info("Esta sede no tiene ventas en el periodo seleccionado.")
    else:
        g1, g2 = st.columns(2)

        with g1:
            st.caption("Ingresos y ganancia por mes ($)")
            st.line_chart(
                v.groupby("mes")[["ingreso", "ganancia"]]
                .sum()
                .rename(columns={
                    "ingreso": "Ingresos",
                    "ganancia": "Ganancia"
                })
            )

        with g2:
            st.caption("Cantidad de ventas por mes")
            st.bar_chart(
                v.groupby("mes")["id_venta"]
                .nunique()
                .rename("Ventas")
            )

        p1, p2 = st.columns([3, 2])

        with p1:
            grafico_top_productos(v, clave)

        with p2:
            por_metodo = (
                v.groupby("metodo", as_index=False)["ingreso"].sum()
            )
            barras(
                por_metodo,
                "metodo",
                "ingreso",
                "Ingresos por método de pago",
                "Ingresos ($)"
            )

        st.subheader("Detalle de productos vendidos")

        detalle = (
            v.groupby(["producto", "unidad"], as_index=False)
            .agg(
                cantidad=("cantidad", "sum"),
                ingreso=("ingreso", "sum"),
                ganancia=("ganancia", "sum")
            )
            .sort_values("ingreso", ascending=False)
            .rename(columns={
                "producto": "Producto",
                "unidad": "Unidad",
                "cantidad": "Cantidad vendida",
                "ingreso": "Ingresos ($)",
                "ganancia": "Ganancia ($)"
            })
        )

        st.dataframe(
            detalle,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Cantidad vendida":
                    st.column_config.NumberColumn(format="%.2f"),
                "Ingresos ($)":
                    st.column_config.NumberColumn(format="$%.2f"),
                "Ganancia ($)":
                    st.column_config.NumberColumn(format="$%.2f"),
            }
        )

    st.subheader("Inventario de la sede")

    umbral = st.number_input(
        "Mostrar productos con existencia menor o igual a",
        min_value=0,
        value=UMBRAL_STOCK_BAJO,
        step=1,
        key=f"umbral_{clave}"
    )

    bajos = (
        inv[inv["existencia"] <= umbral]
        .sort_values("existencia")
        [["producto", "existencia", "unidad"]]
        .rename(columns={
            "producto": "Producto",
            "existencia": "Existencia",
            "unidad": "Unidad"
        })
    )

    if bajos.empty:
        st.success("Ningún producto está por debajo de ese nivel.")
    else:
        st.warning(f"{len(bajos)} productos requieren reabastecimiento.")
        st.dataframe(bajos, use_container_width=True, hide_index=True)


# ==============================
# PANTALLA DEL MODULO
# ==============================
def mostrar_informes():
    st.header("Informes gerenciales")

    # Solo los roles 1, 3 y 5 entran a este modulo
    if not tiene_acceso():
        st.error("No tiene permisos para ver los informes.")
        return

    # El rol 3 solo ve su sede: se necesita saber cual es
    solo_su_sede = ve_solo_su_sede()
    mi_sede = None

    if solo_su_sede:
        mi_sede = st.session_state.get(CLAVE_SEDE)

        if mi_sede is None:
            st.error("Su usuario no tiene una sede asignada.")
            return

        mi_sede = int(mi_sede)

    hoy = date.today()

    col1, col2 = st.columns([3, 1])

    with col1:
        rango = st.date_input(
            "Periodo del informe",
            value=(date(hoy.year, 1, 1), hoy),
            key="informes_rango"
        )

    with col2:
        st.write("")
        st.write("")
        if st.button("Actualizar datos", key="informes_actualizar"):
            st.cache_data.clear()
            st.rerun()

    # Mientras se elige la segunda fecha el rango esta incompleto
    if not isinstance(rango, (tuple, list)) or len(rango) != 2:
        st.info("Seleccione la fecha inicial y la fecha final.")
        return

    desde, hasta = rango

    sedes = cargar_sedes()
    ventas = cargar_ventas(desde, hasta)
    compras = cargar_compras()
    inventario = cargar_inventario()

    # Rol 3: se recorta todo a su sede ANTES de calcular.
    # Las compras NO se recortan: se necesitan completas para el costo
    # promedio (preparar() ya las separa por sede, y el resumen solo
    # incluye las sedes que quedaron en `sedes`).
    if solo_su_sede:
        sedes = sedes[sedes["id_sede"] == mi_sede]
        ventas = ventas[ventas["id_sede"] == mi_sede]
        inventario = inventario[inventario["id_sede"] == mi_sede]

    if sedes.empty:
        if solo_su_sede:
            st.warning("No se encontró la sede asignada a su usuario.")
        else:
            st.warning("No hay sedes registradas.")
        return

    v, compras_p, inv, resumen = preparar(
        sedes, ventas, compras, inventario, desde, hasta
    )

    st.caption(
        f"Periodo: {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}. "
        "Ganancia bruta estimada = ventas menos el costo promedio de "
        "compra de lo vendido. No incluye gastos operativos "
        "(salarios, alquiler, servicios)."
    )

    # Rol 3: directo al informe de su sede, sin balance general ni pestañas
    if solo_su_sede:
        fila = resumen.iloc[0]
        st.subheader(fila["sede"])

        mostrar_sede(
            fila,
            v[v["id_sede"] == mi_sede],
            compras_p[compras_p["id_sede"] == mi_sede],
            inv[inv["id_sede"] == mi_sede]
        )
        return

    # Roles 1 y 5: balance general + una pestaña por sede
    nombres = ["Balance general"] + resumen["sede"].tolist()
    pestanas = st.tabs(nombres)

    with pestanas[0]:
        mostrar_balance(v, compras_p, inv, resumen)

    for pestana, (_, fila) in zip(pestanas[1:], resumen.iterrows()):
        id_sede = fila["id_sede"]

        with pestana:
            mostrar_sede(
                fila,
                v[v["id_sede"] == id_sede],
                compras_p[compras_p["id_sede"] == id_sede],
                inv[inv["id_sede"] == id_sede]
            )
