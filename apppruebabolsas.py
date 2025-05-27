import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from collections import defaultdict

# === Expresiones regulares ===
ORDER_REGEX = re.compile(r'\b(SO-|USS|SOC|AMZ)-?(\d+)\b')
SHIPMENT_REGEX = re.compile(r'\b(SH\d{5,})\b')
PICKUP_REGEX = re.compile(r'Customer\s*Pickup|Cust\s*Pickup|CUSTPICKUP', re.IGNORECASE)
QUANTITY_REGEX = re.compile(r'(\d+)\s*(?:EA|PCS|PC|Each)', re.IGNORECASE)
SHIPPING_2DAY_REGEX = re.compile(r'Shipping\s*Method:\s*2\s*day', re.IGNORECASE)


# === Funciones auxiliares ===
def extract_identifiers(text):
    order_match = ORDER_REGEX.search(text)
    shipment_match = SHIPMENT_REGEX.search(text)
    order_id = f"{order_match.group(1).rstrip('-')}-{order_match.group(2)}" if order_match else None
    shipment_id = shipment_match.group(1) if shipment_match else None
    return order_id, shipment_id

def extract_part_numbers(text):
    """
    Extrae números de parte del texto.
    Prioritiza las coincidencias más largas y asegura que un número de parte más corto
    no se cuente si es parte de un número de parte más largo identificado 
    en la misma posición.
    Retorna un diccionario con los números de parte encontrados como claves y valor 1.
    """
    part_counts = {}
    text_upper = text.upper()
    
    # Usamos las claves originales del diccionario PART_DESCRIPTIONS
    # para determinar qué números de parte estamos buscando.
    all_part_keys = list(PART_DESCRIPTIONS.keys())

    for p_short in all_part_keys:
        # Patrón para encontrar p_short como una "palabra completa"
        # (considerando que '-' no es parte de \w)
        pattern_short = r'(?<!\w)' + re.escape(p_short) + r'(?!\w)'
        found_standalone_match_for_p_short = False
        
        # Iteramos sobre todas las posibles coincidencias de p_short en el texto
        for match_short in re.finditer(pattern_short, text_upper):
            match_short_start_index = match_short.start()
            is_this_match_shadowed_by_a_longer_one = False
            
            # Verificamos si esta coincidencia específica de p_short está "opacada"
            # por un número de parte más largo (p_long) que también es válido y 
            # comienza en la misma posición.
            for p_long in all_part_keys:
                if len(p_long) > len(p_short) and \
                   p_short == p_long[:len(p_short)] and \
                   text_upper.startswith(p_long, match_short_start_index):
                    
                    # p_short es un prefijo de p_long, y p_long aparece en el texto
                    # comenzando en la misma posición que p_short.
                    # Ahora, verificamos si este p_long es una "palabra completa" válida aquí.
                    # (es decir, si p_long no está seguido por un carácter de palabra \w)
                    
                    end_of_p_long_index = match_short_start_index + len(p_long)
                    is_p_long_standalone_here = False
                    if end_of_p_long_index == len(text_upper): # p_long está al final del texto
                        is_p_long_standalone_here = True
                    else:
                        char_after_p_long = text_upper[end_of_p_long_index]
                        # Si el carácter después de p_long NO es un carácter de palabra (\w)
                        if not re.match(r'\w', char_after_p_long):
                            is_p_long_standalone_here = True
                    
                    if is_p_long_standalone_here:
                        is_this_match_shadowed_by_a_longer_one = True
                        break # Esta coincidencia de p_short está opacada, no necesitamos verificar más p_longs.
            
            if not is_this_match_shadowed_by_a_longer_one:
                # Esta ocurrencia de p_short es independiente (no forma parte de un p_long en esta posición).
                found_standalone_match_for_p_short = True
                break # Hemos encontrado una instancia válida de p_short, así que debe incluirse en los resultados.
        
        if found_standalone_match_for_p_short:
            part_counts[p_short] = 1
            
    return part_counts

def extract_relations(text, order_id, shipment_id):
    """Extrae relaciones entre códigos, órdenes y SH"""
    relations = []
    text_upper = text.upper()
    
    for part_num in PART_DESCRIPTIONS:
        pattern = r'(?<!\w)' + re.escape(part_num) + r'(?!\w)'
        if re.search(pattern, text_upper) and order_id and shipment_id:
            relations.append({
                "Orden": order_id,
                "Código": part_num,
                "Descripción": PART_DESCRIPTIONS[part_num],
                "SH": shipment_id
            })
    return relations


# === Definición correcta de partes (diccionario) ===
PART_DESCRIPTIONS = {
    'B-PG-081-BLK': '2023 PXG Deluxe Cart Bag - Black',
    'B-PG-082-WHT': '2023 PXG Lightweight Cart Bag - White/Black',
    'B-PG-172': '2025 Stars & Stripes LW Carry Stand Bag',
    'B-PG-172-BGRY': 'Xtreme Carry Stand Bag - Black',
    'B-PG-172-BLACK': 'Xtreme Carry Stand Bag - Freedom - Black',
    'B-PG-172-DB': 'Deluxe Carry Stand Bag - Black',
    'B-PG-172-DKNSS': 'Deluxe Carry Stand Bag - Darkness',
    'B-PG-172-DW': 'Deluxe Carry Stand Bag - White',
    'B-PG-172-GREEN': 'Xtreme Carry Stand Bag - Freedom - Green',
    'B-PG-172-GREY': 'Xtreme Carry Stand Bag - Freedom - Grey',
    'B-PG-172-NAVY': 'Xtreme Carry Stand Bag - Freedom - Navy',
    'B-PG-172-TAN': 'Xtreme Carry Stand Bag - Freedom - Tan',
    'B-PG-172-WBLK': 'Xtreme Carry Stand Bag - White',
    'B-PG-173': '2025 Stars & Stripes Hybrid Stand Bag',
    'B-PG-173-BGRY': 'Xtreme Hybrid Stand Bag - Black',
    'B-PG-173-BO': 'Deluxe Hybrid Stand Bag - Black',
    'B-PG-173-DKNSS': 'Deluxe Hybrid Stand Bag - Darkness',
    'B-PG-173-WBLK': 'Xtreme Hybrid Stand Bag - White',
    'B-PG-173-WO': 'Deluxe Hybrid Stand Bag - White',
    'B-PG-244': 'Xtreme Cart Bag - White',
    'B-PG-245': '2025 Stars & Stripes Cart Bag',
    'B-PG-245-BLK': 'Deluxe Cart Bag B2 - Black',
    'B-PG-245-WHT': 'Deluxe Cart Bag B2 - White',
    'B-PG-246-POLY': 'Minimalist Carry Stand Bag - Black',
    'B-UGB8-EP': '2020 Carry Stand Bag - Black'
}


def create_relations_table(relations):
    """Crea una tabla PDF con las relaciones orden-código-SH"""
    if not relations:
        return None
    
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    
    # Título
    page.insert_text((50, y), "RELACIÓN ÓRDENES - CÓDIGOS - SH", 
                    fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30
    
    # Encabezados
    headers = ["Orden", "Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
    page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
    page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
    y += 20
    
    # Convertir a DataFrame para ordenar
    df = pd.DataFrame(relations)
    df = df.sort_values(by=["Orden", "Código"])
    
    # Datos
    for _, row in df.iterrows():
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
            
        page.insert_text((50, y), row["Orden"], fontsize=10)
        page.insert_text((150, y), row["Código"], fontsize=10)
        
        # Descripción en múltiples líneas si es necesario
        desc = row["Descripción"]
        if len(desc) > 30:
            page.insert_text((300, y), desc[:30], fontsize=9)
            page.insert_text((300, y + 12), desc[30:], fontsize=9)
            y += 12
        else:
            page.insert_text((300, y), desc, fontsize=10)
            
        page.insert_text((500, y), row["SH"], fontsize=10)
        y += 25 if len(desc) > 30 else 15
    
    return doc

def insert_divider_page(doc, label):
    """Crea una página divisoria con texto de etiqueta"""
    page = doc.new_page()
    text = f"=== {label.upper()} ==="
    page.insert_text(
        point=(72, 72),
        text=text,
        fontsize=18,
        fontname="helv",
        color=(0, 0, 0)
    )


def parse_pdf(file_bytes):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    relations = []
    two_day_sh = set()  # Para almacenar SH con método 2 day
    last_order_id = None
    last_shipment_id = None

    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text()
        order_id, shipment_id = extract_identifiers(text)
        
        # Detectar shipping method 2 day
        if SHIPPING_2DAY_REGEX.search(text) and shipment_id:
            two_day_sh.add(shipment_id)
        
        if not order_id:
            order_id = last_order_id
        else:
            last_order_id = order_id

        if not shipment_id:
            shipment_id = last_shipment_id
        else:
            last_shipment_id = shipment_id

        part_numbers = extract_part_numbers(text)
        page_relations = extract_relations(text, order_id, shipment_id)
        relations.extend(page_relations)

        pages.append({
            "number": i,
            "text": text,
            "order_id": order_id,
            "shipment_id": shipment_id,
            "part_numbers": part_numbers,
            "page": page,
            "parent": doc,
            "is_2day": SHIPPING_2DAY_REGEX.search(text) is not None
        })

    return pages, relations, two_day_sh

def group_codes_by_family(relations):
    """Agrupa los códigos por familia principal"""
    # Convertir a DataFrame
    df = pd.DataFrame(relations)
    
    # Extraer familia base (ej: B-PG-172 de B-PG-172-BGRY)
    df['Familia'] = df['Código'].apply(lambda x: x.split('-')[0] + '-' + x.split('-')[1] + '-' + x.split('-')[2])
    
    # Ordenar por Familia y luego por Código
    df = df.sort_values(by=['Familia', 'Código'])
    
    return df


def display_interactive_table(relations):
    """Muestra una tabla interactiva con códigos agrupados por familia"""
    if not relations:
        st.warning("No se encontraron relaciones entre órdenes, códigos y SH")
        return
    
    # Agrupar por familia
    df = group_codes_by_family(relations)
    
    # Formatear códigos para mostrar jerarquía
    def format_code(row):
        base_family = row['Familia']
        full_code = row['Código']
        if full_code == base_family:
            return full_code
        else:
            return "└─ " + full_code.replace(base_family + '-', '')
    
    df['Código (Agrupado)'] = df.apply(format_code, axis=1)
    
    st.subheader("Relación Detallada de Órdenes, Códigos y SH (Agrupados por Familia)")
    
    # Mostrar solo columnas relevantes
    display_df = df[['Orden', 'Código (Agrupado)', 'Descripción', 'SH']]
    
    st.dataframe(
        display_df,
        column_config={
            "Descripción": st.column_config.TextColumn(width="large"),
            "SH": st.column_config.TextColumn(width="medium"),
            "Código (Agrupado)": st.column_config.TextColumn(width="medium", 
                                                          help="Códigos agrupados por familia")
        },
        hide_index=True,
        use_container_width=True
    )
    
    # Opción para descargar
    csv = df[['Orden', 'Código', 'Descripción', 'SH']].to_csv(index=False, encoding='utf-8')
    st.download_button(
        "Descargar como CSV",
        data=csv,
        file_name='relacion_ordenes_codigos_sh.csv',
        mime='text/csv'
    )


def create_relations_table(relations):
    """Crea una tabla PDF con códigos agrupados por familia"""
    if not relations:
        return None
    
    # Agrupar por familia
    df = group_codes_by_family(relations)
    
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50
    
    # Título
    title = "RELACIÓN ÓRDENES - CÓDIGOS (AGRUPADOS) - SH"
    page.insert_text((50, y), title, fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30
    
    # Encabezados
    headers = ["Orden", "Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
    page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
    page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
    y += 20
    
    current_family = None
    
    for _, row in df.iterrows():
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
            # Reinsertar encabezados en nueva página
            page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
            page.insert_text((150, y), headers[1], fontsize=12, fontname="helv")
            page.insert_text((300, y), headers[2], fontsize=12, fontname="helv")
            page.insert_text((500, y), headers[3], fontsize=12, fontname="helv")
            y += 20
            
        family = row['Familia']
        code = row['Código']
        
        # Mostrar familia principal si cambió
        if family != current_family:
            page.insert_text((50, y), row['Orden'], fontsize=10)
            page.insert_text((150, y), family, fontsize=10, fontname="helv-b")
            page.insert_text((300, y), PART_DESCRIPTIONS.get(family, ""), fontsize=10)
            page.insert_text((500, y), row['SH'], fontsize=10)
            y += 15
            current_family = family
        
        # Mostrar variante si es diferente a la familia base
        if code != family:
            page.insert_text((50, y), "", fontsize=10)  # Dejar orden en blanco
            page.insert_text((150, y), "  " + code.replace(family + '-', ''), fontsize=10)
            page.insert_text((300, y), PART_DESCRIPTIONS.get(code, ""), fontsize=10)
            page.insert_text((500, y), row['SH'], fontsize=10)
            y += 15
    
    return doc

# === Nueva función para crear página de SH 2 day ===
def create_2day_shipping_page(two_day_sh_list):
    """Crea una página con la lista de SH con método 2 day"""
    if not two_day_sh_list:
        return None
    
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72
    
    # Título
    page.insert_text((72, y), "ÓRDENES CON SHIPPING METHOD: 2 DAY", 
                    fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30
    
    # Lista de SH
    for sh in sorted(two_day_sh_list):
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 72
        page.insert_text((72, y), sh, fontsize=12)
        y += 20
    
    page.insert_text((72, y + 20), f"Total de órdenes 2 day: {len(two_day_sh_list)}", 
                     fontsize=14, color=(0, 0, 1))
    
    return doc

def create_summary_page(order_data, build_keys, shipment_keys, pickup_flag):
    all_orders = set(build_keys) | set(shipment_keys)
    unmatched_build = set(build_keys) - set(shipment_keys)
    unmatched_ship = set(shipment_keys) - set(build_keys)
    pickup_orders = [oid for oid in all_orders if order_data[oid]["pickup"]] if pickup_flag else []

    lines = [
        "Tequila Order Summary",
        "",
        f"Total Unique Orders: {len(all_orders)}",
        f"Orders with Build Sheets Only: {len(unmatched_build)}",
        f"Orders with Shipments Only: {len(unmatched_ship)}",
        f"Orders with Both: {len(all_orders) - len(unmatched_build) - len(unmatched_ship)}"
    ]
    if pickup_flag:
        lines.append(f"Customer Pickup Orders: {len(pickup_orders)}")

    summary_doc = fitz.open()
    y = 72
    page = summary_doc.new_page(width=595, height=842)
    for line in lines:
        if y > 770:
            page = summary_doc.new_page(width=595, height=842)
            y = 72
        page.insert_text((72, y), line, fontsize=12)
        y += 14
    return summary_doc


def get_build_order_list(build_pages):
    seen = set()
    order = []
    for p in build_pages:
        oid = p["order_id"]
        if oid and oid not in seen:
            seen.add(oid)
            order.append(oid)
    return order


def group_by_order(pages, classify_pickup=False):
    order_map = defaultdict(lambda: {"pages": [], "pickup": False, "part_numbers": defaultdict(int)})
    for page in pages:
        oid = page.get("order_id")  # Usa .get() para evitar KeyError
        if not oid:
            continue
        order_map[oid]["pages"].append(page)
        if classify_pickup:
            text = page.get("text", "")
            if PICKUP_REGEX.search(text):
                order_map[oid]["pickup"] = True
        for part_num, qty in page.get("part_numbers", {}).items():
            order_map[oid]["part_numbers"][part_num] += qty
    return order_map


def create_part_numbers_summary(order_data):
    part_appearances = defaultdict(int)

    # Acumular las apariciones de cada número de parte
    for oid, data in order_data.items():
        part_numbers = data.get("part_numbers", {}) # Asumiendo que esto viene de extract_part_numbers
        for part_num, count in part_numbers.items():
            if part_num in PART_DESCRIPTIONS: # Solo considerar partes conocidas
                part_appearances[part_num] += count

    if not part_appearances:
        return None # No hay nada que reportar

    doc = fitz.open() # Crear un nuevo documento PDF
    page = doc.new_page(width=595, height=842) # Página A4 estándar
    
    y_coordinate = 72 # Posición Y inicial para escribir texto (desde arriba)
    left_margin_code = 50
    left_margin_desc = 150
    left_margin_count = 450

    # Escribir encabezados de la tabla
    headers = ["Código", "Descripción", "Apariciones"]
    page.insert_text((left_margin_code, y_coordinate), headers[0], 
                      fontsize=12, fontname="Helvetica") # Cambiado a Helvetica, quitado set_simple
    page.insert_text((left_margin_desc, y_coordinate), headers[1], 
                      fontsize=12, fontname="Helvetica") # Cambiado a Helvetica, quitado set_simple
    page.insert_text((left_margin_count, y_coordinate), headers[2], 
                      fontsize=12, fontname="Helvetica") # Cambiado a Helvetica, quitado set_simple
    y_coordinate += 25 # Espacio después de los encabezados

    # Escribir los datos de cada número de parte
    for part_num in sorted(part_appearances.keys()): # Ordenar por número de parte
        count = part_appearances[part_num]
        if count == 0: # Omitir si no hay apariciones (aunque defaultdict(int) no debería permitirlo aquí)
            continue
        
        # Lógica para nueva página si el contenido excede el alto
        if y_coordinate > 750: # Dejar un margen inferior
            page = doc.new_page(width=595, height=842)
            y_coordinate = 72
            # Opcional: Re-escribir encabezados en la nueva página
            page.insert_text((left_margin_code, y_coordinate), headers[0], 
                              fontsize=12, fontname="Helvetica")
            page.insert_text((left_margin_desc, y_coordinate), headers[1], 
                              fontsize=12, fontname="Helvetica")
            page.insert_text((left_margin_count, y_coordinate), headers[2], 
                              fontsize=12, fontname="Helvetica")
            y_coordinate += 25

        description = PART_DESCRIPTIONS[part_num]
        
        # Código de la parte (usa fuente predeterminada si no se especifica fontname)
        page.insert_text((left_margin_code, y_coordinate), part_num, fontsize=10)

        # Descripción (con manejo de texto largo)
        # (usa fuente predeterminada si no se especifica fontname)
        if len(description) > 40: # Aproximadamente 40 caracteres para el ancho de descripción
            page.insert_text((left_margin_desc, y_coordinate), description[:40], fontsize=9)
            page.insert_text((left_margin_desc, y_coordinate + 12), description[40:], fontsize=9)
            line_height = 25 # Mayor altura si la descripción tiene dos líneas
        else:
            page.insert_text((left_margin_desc, y_coordinate), description, fontsize=10)
            line_height = 15 # Altura normal

        # Conteo de apariciones (usa fuente predeterminada si no se especifica fontname)
        page.insert_text((left_margin_count, y_coordinate), str(count), fontsize=10)
        
        y_coordinate += line_height

    # Escribir el total general
    total_appearances = sum(part_appearances.values())
    y_coordinate += 20 # Espacio antes del total
    
    if y_coordinate > 780: # Revisar si el total cabe en la página actual
        page = doc.new_page(width=595, height=842)
        y_coordinate = 72

    page.insert_text(
        (left_margin_code, y_coordinate),
        f"TOTAL GENERAL DE APARICIONES: {total_appearances}",
        fontsize=14,
        color=(0, 0, 1), # Color azul
        fontname="Helvetica" # Cambiado a Helvetica, quitado set_simple
    )

    return doc

def merge_documents(build_order, build_map, ship_map, order_meta, pickup_flag, relations, two_day_sh):
    doc = fitz.open()
    pickups = [oid for oid in build_order if order_meta[oid]["pickup"]] if pickup_flag else []

    # 1. Insertar tabla de relaciones
    relations_table = create_relations_table(relations)
    if relations_table:
        doc.insert_pdf(relations_table)
        insert_divider_page(doc, "Resumen de Partes")
    
    # 2. Insertar página de SH 2 day
    two_day_page = create_2day_shipping_page(two_day_sh)
    if two_day_page:
        doc.insert_pdf(two_day_page)
        insert_divider_page(doc, "Documentos Principales")
    
    # 3. Insertar resumen de partes
    part_summary = create_part_numbers_summary(order_meta)
    if part_summary:
        doc.insert_pdf(part_summary)
        insert_divider_page(doc, "Documentos Principales")

    # Insertar páginas de órdenes
    def insert_order_pages(order_list):
        for oid in order_list:
            # Insertar build pages
            for p in build_map.get(oid, {}).get("pages", []):
                src_page = p["parent"][p["number"]]
                doc.insert_pdf(p["parent"], from_page=p["number"], to_page=p["number"])
            
            # Insertar ship pages
            for p in ship_map.get(oid, {}).get("pages", []):
                src_page = p["parent"][p["number"]]
                doc.insert_pdf(p["parent"], from_page=p["number"], to_page=p["number"])

    # Insertar pickups primero si está habilitado
    if pickup_flag and pickups:
        insert_divider_page(doc, "Customer Pickup Orders")
        insert_order_pages(pickups)

    # Insertar otras órdenes
    others = [oid for oid in build_order if oid not in pickups]
    if others:
        insert_divider_page(doc, "Other Orders")
        insert_order_pages(others)

    return doc

# === Interfaz de Streamlit ===
st.title("Tequila Build/Shipment PDF Processor")

build_file = st.file_uploader("Upload Build Sheets PDF", type="pdf")
ship_file = st.file_uploader("Upload Shipment Pick Lists PDF", type="pdf")
pickup_flag = st.checkbox("Summarize Customer Pickup orders", value=True)

if build_file and ship_file:
    build_bytes = build_file.read()
    ship_bytes = ship_file.read()

    # Procesar ambos PDFs
    build_pages, build_relations, build_two_day = parse_pdf(build_bytes)
    ship_pages, ship_relations, ship_two_day = parse_pdf(ship_bytes)

    # Combinar todo
    original_pages = build_pages + ship_pages
    all_relations = build_relations + ship_relations
    all_two_day = build_two_day.union(ship_two_day)
    all_meta = group_by_order(original_pages, classify_pickup=pickup_flag)

    # Mostrar tabla interactiva
    display_interactive_table(all_relations)

    # Mostrar SH con método 2 day
    if all_two_day:
        st.subheader("Órdenes con Shipping Method: 2 day")
        st.write(", ".join(sorted(all_two_day)))
    else:
        st.warning("No se encontraron órdenes con Shipping Method: 2 day")

    if st.button("Generate Merged Output"):
        build_map = group_by_order(build_pages)
        ship_map = group_by_order(ship_pages)
        build_order = get_build_order_list(build_pages)

        # Generar resúmenes
        summary = create_summary_page(all_meta, build_map.keys(), ship_map.keys(), pickup_flag)
        merged = merge_documents(build_order, build_map, ship_map, all_meta, pickup_flag, all_relations, all_two_day)

        # Insertar resumen al inicio
        if summary:
            merged.insert_pdf(summary, start_at=0)

        # Botón de descarga
        st.download_button(
            "Download Merged Output PDF",
            data=merged.tobytes(),
            file_name="Tequila_Merged_Output.pdf"
        )
