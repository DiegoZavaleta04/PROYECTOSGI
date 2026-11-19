import streamlit as st
import pandas as pd

from modulos import productos_service as servicio


# -----------------------------------
# PERMISOS DEL MÓDULO PRODUCTOS
# -----------------------------------

ROLES_PUEDEN_VER = (1, 2, 3, 4)
ROLES_PUEDEN_GESTIONAR = (2,)


# -----------------------------------
# REGLA DE VENTA DEL PRODUCTO
# -----------------------------------
# Lo mas pequeno que se puede vender de un producto.
OPCIONES_VENTA = {
    "Solo unidades enteras (1, 2, 3...)": 1.0,
    "Medias (0.5, 1, 1.5...)": 0.5,
    "Hasta cuartos (0.25, 0.5, 0.75...)": 0.25,
}

TEXTO_REGLA = {
    1.0: "Enteras",
    0.5: "Medias",
    0.25: "Cuartos",
}


def texto_regla(valor):
    try:
        return TEXTO_REGLA.get(float(valor), str(valor))
    except (TypeError, ValueError):
        return "Enteras"


def render():

    id_rol = st.session_state.get("id_rol")

    # Validar acceso al módulo
    if id_rol not in ROLES_PUEDEN_VER:
        st.error("No tienes permisos para acceder al módulo de productos.")
        st.stop()

    puede_gestionar = id_rol in ROLES_PUEDEN_GESTIONAR

    st.title("Gestión de productos")
    st.write("Consulta, registra y actualiza los productos de la cooperativa.")

    # PESTAÑA DE PRODUCTOS
    tab_productos, tab_categorias, tab_unidades = st.tabs(
        ["Productos", "Categorías", "Unidades de medida"]
    )

    # -----------------------------------
    # PRODUCTOS
    # -----------------------------------

    with tab_productos:

        st.subheader("Listado de productos")

        col1, col2 = st.columns([2, 1])

        with col1:
            busqueda = st.text_input(
                "Buscar producto",
                placeholder="Escribe el nombre o ID del producto"
            )

        with col2:
            categorias = servicio.listar_categorias()

            opciones_categoria = {
                "Todas las categorías": None
            }

            for categoria in categorias:
                opciones_categoria[categoria["nombre"]] = categoria["id_categoria"]

            categoria_seleccionada = st.selectbox(
                "Filtrar por categoría",
                list(opciones_categoria.keys())
            )

        id_categoria = opciones_categoria[categoria_seleccionada]

        try:
            productos = servicio.listar_productos(
                busqueda,
                id_categoria
            )

            if productos:
                df = pd.DataFrame(productos)

                df = df.rename(columns={
                    "Id_producto": "ID",
                    "Nombre": "Producto",
                    "Descripcion": "Descripción",
                    "Categoria": "Categoría",
                    "Unidad": "Unidad de medida",
                    "Abreviatura": "Abreviatura"
                })

                df["Se vende en"] = df["Incremento_venta"].apply(
                    texto_regla
                )

                columnas = [
                    "ID",
                    "Producto",
                    "Descripción",
                    "Categoría",
                    "Unidad de medida",
                    "Abreviatura",
                    "Se vende en"
                ]

                st.dataframe(
                    df[columnas],
                    use_container_width=True,
                    hide_index=True
                )

                st.caption(f"Total de productos encontrados: {len(productos)}")

            else:
                st.info("No se encontraron productos.")

        except Exception as error:
            st.error(f"No se pudieron consultar los productos: {error}")

        st.divider()

        # REGISTRAR PRODUCTO
        if puede_gestionar:

            st.subheader("Registrar nuevo producto")

            try:
                categorias = servicio.listar_categorias()
                unidades = servicio.listar_unidades()

                if not categorias:
                    st.warning("Primero debes registrar una categoría.")

                elif not unidades:
                    st.warning("Primero debes registrar una unidad de medida.")

                else:
                    with st.form("form_nuevo_producto"):

                        nombre = st.text_input("Nombre del producto")

                        descripcion = st.text_area(
                            "Descripción",
                            max_chars=255
                        )

                        opciones_cat = {
                            c["nombre"]: c["id_categoria"]
                            for c in categorias
                        }

                        opciones_uni = {
                            f'{u["Nombre"]} ({u["Abreviatura"]})': u["Id_unidad"]
                            for u in unidades
                        }

                        categoria = st.selectbox(
                            "Categoría",
                            list(opciones_cat.keys())
                        )

                        unidad = st.selectbox(
                            "Unidad de medida",
                            list(opciones_uni.keys())
                        )

                        regla = st.selectbox(
                            "¿Cómo se vende este producto?",
                            list(OPCIONES_VENTA.keys()),
                            help=(
                                "Define la cantidad mínima que se puede "
                                "vender. Ejemplo: la crema en botella puede "
                                "venderse por cuartos de botella."
                            )
                        )

                        guardar = st.form_submit_button(
                            "Registrar producto",
                            use_container_width=True
                        )

                        if guardar:
                            servicio.crear_producto(
                                nombre,
                                descripcion,
                                opciones_uni[unidad],
                                opciones_cat[categoria],
                                OPCIONES_VENTA[regla]
                            )

                            st.success("Producto registrado correctamente.")
                            st.rerun()

            except Exception as error:
                st.error(f"No se pudo registrar el producto: {error}")

            st.divider()

            # EDITAR PRODUCTO
            st.subheader("Editar producto")

            try:
                productos_editar = servicio.listar_productos()

                if productos_editar:

                    opciones_productos = {
                        f'{p["Id_producto"]} - {p["Nombre"]}': p
                        for p in productos_editar
                    }

                    seleccionado = st.selectbox(
                        "Selecciona el producto que deseas editar",
                        list(opciones_productos.keys()),
                        key="producto_editar"
                    )

                    producto = opciones_productos[seleccionado]

                    categorias = servicio.listar_categorias()
                    unidades = servicio.listar_unidades()

                    if categorias and unidades:

                        with st.form("form_editar_producto"):

                            nuevo_nombre = st.text_input(
                                "Nombre",
                                value=producto["Nombre"]
                            )

                            nueva_descripcion = st.text_area(
                                "Descripción",
                                value=producto["Descripcion"] or ""
                            )

                            opciones_cat = {
                                c["nombre"]: c["id_categoria"]
                                for c in categorias
                            }

                            opciones_uni = {
                                f'{u["Nombre"]} ({u["Abreviatura"]})': u["Id_unidad"]
                                for u in unidades
                            }

                            categoria_actual = next(
                                (
                                    nombre
                                    for nombre, id_cat in opciones_cat.items()
                                    if id_cat == producto["Id_categoria"]
                                ),
                                list(opciones_cat.keys())[0]
                            )

                            unidad_actual = next(
                                (
                                    nombre
                                    for nombre, id_uni in opciones_uni.items()
                                    if id_uni == producto["Id_unidad"]
                                ),
                                list(opciones_uni.keys())[0]
                            )

                            nueva_categoria = st.selectbox(
                                "Categoría",
                                list(opciones_cat.keys()),
                                index=list(opciones_cat.keys()).index(categoria_actual)
                            )

                            nueva_unidad = st.selectbox(
                                "Unidad de medida",
                                list(opciones_uni.keys()),
                                index=list(opciones_uni.keys()).index(unidad_actual)
                            )

                            reglas = list(OPCIONES_VENTA.keys())

                            regla_actual = next(
                                (
                                    nombre
                                    for nombre, valor in OPCIONES_VENTA.items()
                                    if valor == float(
                                        producto.get("Incremento_venta") or 1
                                    )
                                ),
                                reglas[0]
                            )

                            nueva_regla = st.selectbox(
                                "¿Cómo se vende este producto?",
                                reglas,
                                index=reglas.index(regla_actual)
                            )

                            actualizar = st.form_submit_button(
                                "Guardar cambios",
                                use_container_width=True
                            )

                            if actualizar:

                                servicio.actualizar_producto(
                                    producto["Id_producto"],
                                    nuevo_nombre,
                                    nueva_descripcion,
                                    opciones_uni[nueva_unidad],
                                    opciones_cat[nueva_categoria],
                                    OPCIONES_VENTA[nueva_regla]
                                )

                                st.success("Producto actualizado correctamente.")
                                st.rerun()

                    else:
                        st.warning(
                            "Necesitas tener categorías y unidades registradas para editar."
                        )

                else:
                    st.info("No hay productos registrados para editar.")

            except Exception as error:
                st.error(f"No se pudo editar el producto: {error}")

    # -----------------------------------
    # CATEGORÍAS
    # -----------------------------------

    with tab_categorias:

        st.subheader("Categorías de productos")

        try:
            categorias = servicio.listar_categorias()

            if categorias:
                df_cat = pd.DataFrame(categorias)

                df_cat = df_cat.rename(columns={
                    "id_categoria": "ID",
                    "nombre": "Categoría"
                })

                st.dataframe(
                    df_cat,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No hay categorías registradas.")

            if puede_gestionar:

                st.divider()
                st.subheader("Registrar categoría")

                with st.form("form_categoria"):

                    nombre_categoria = st.text_input(
                        "Nombre de la categoría"
                    )

                    guardar_categoria = st.form_submit_button(
                        "Guardar categoría",
                        use_container_width=True
                    )

                    if guardar_categoria:
                        servicio.crear_categoria(nombre_categoria)
                        st.success("Categoría registrada correctamente.")
                        st.rerun()

        except Exception as error:
            st.error(f"Error en categorías: {error}")

    # -----------------------------------
    # UNIDADES DE MEDIDA
    # -----------------------------------

    with tab_unidades:

        st.subheader("Unidades de medida")

        try:
            unidades = servicio.listar_unidades()

            if unidades:
                df_uni = pd.DataFrame(unidades)

                df_uni = df_uni.rename(columns={
                    "Id_unidad": "ID",
                    "Nombre": "Unidad",
                    "Abreviatura": "Abreviatura"
                })

                st.dataframe(
                    df_uni,
                    use_container_width=True,
                    hide_index=True
                )
            else:
                st.info("No hay unidades registradas.")

            if puede_gestionar:

                st.divider()
                st.subheader("Registrar unidad de medida")

                with st.form("form_unidad"):

                    nombre_unidad = st.text_input(
                        "Nombre de la unidad"
                    )

                    abreviatura = st.text_input(
                        "Abreviatura"
                    )

                    guardar_unidad = st.form_submit_button(
                        "Guardar unidad",
                        use_container_width=True
                    )

                    if guardar_unidad:
                        servicio.crear_unidad(
                            nombre_unidad,
                            abreviatura
                        )

                        st.success("Unidad registrada correctamente.")
                        st.rerun()

        except Exception as error:
            st.error(f"Error en unidades: {error}")
