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


def parse_pdf(pdf_bytes):
    """
    Parses a PDF file, extracts relevant information, and returns it.

    Args:
        pdf_bytes: The content of the PDF file as bytes.

    Returns:
        A tuple containing:
        - A list of dictionaries, where each dictionary represents a page and contains
          the extracted information (order_id, shipment_id, part_numbers, text).
        - A list of relations (dictionaries) between order_id, part_num, description, and shipment_id.
        - A set of shipment IDs with "2 day" shipping.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    all_pages_data = []
    all_relations = []
    two_day_sh_list = set()

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        order_id, shipment_id = extract_identifiers(text)
        part_numbers = extract_part_numbers(text)

        if shipment_id and SHIPPING_2DAY_REGEX.search(text):
            two_day_sh_list.add(shipment_id)

        page_data = {
            "number": page_num,
            "order_id": order_id,
            "shipment_id": shipment_id,
            "part_numbers": part_numbers,
            "text": text,
            "parent": doc,  # Add the document object
        }
        all_pages_data.append(page_data)

        # Extract relations for this page
        if order_id and shipment_id:
            page_relations = extract_relations(text, order_id, shipment_id)
            all_relations.extend(page_relations)

    return all_pages_data, all_relations, two_day_sh_list

# === Definición CORRECTA y COMPLETA de partes (diccionario) ===
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
    'B-UGB8-EP': '2020 Carry Stand Bag - Black',

    # --- CÓDIGOS DE LAS IMÁGENES ---
   # image_fbd711.png (Golf Balls)
    'GB-DOZ-XTREME': 'Xtreme Golf Ball - Dozen',
    'GB-DOZ-XTTR-WHT': 'Xtreme Tour Golf Ball - White - Dozen',
    'GB-DOZ-XTTR-YEL': 'Xtreme Tour Golf Ball - Yellow - Dozen',
    'GB-DOZ-XTTRX-WHT': 'Xtreme Tour X Golf Ball - White - Dozen',

    # image_fb69b2.png y image_fbd6af.png (Hats/Caps y Gloves)
    'H-22PXG000013-BLK': 'Tall Visor - Black',
    'H-22PXG000013-WHT': 'Tall Visor - White',
    'H-22PXG000014-BLK': 'Sport Visor - Black',
    'H-22PXG000014-WHT': 'Sport Visor - White',
    'H-23PXG0000124-2-BG-OSFM': 'Dog Tag 6-Panel Snapback Cap - Black/Grey Logo - One Size',
    'H-23PXG0000124-2-BW-OSFM': 'Dog Tag 6-Panel Snapback Cap - Black/White Logo - One Size',
    'H-23PXG0000124-2-CG-OSFM': 'Dog Tag 6-Panel Snapback Cap - White/Grey Logo - One Size',
    'H-23PXG0000124-2-WG-OSFM': 'Dog Tag 6-Panel Snapback Cap - White/Grey Logo - One Size', # Duplicado, mantener si es diferente
    'H-23PXG000078-1-S-M': 'Tour Bush Hat - White - S/M',
    'H-23PXG000094-1-OSFM-BLK': 'Faceted Front Trucker Cap - Black - One Size',
    'H-23PXG000094-1-OSFM-WHT': 'Faceted Front Trucker Cap - White - One Size',
    'H-23PXG000101-BW-OSFM': 'Men\'s 6-Panel High Crown Snapback Cap - Black/White Logo - One Size',
    'H-23PXG000101-NW-OSFM': 'Men\'s 6-Panel High Crown Snapback Cap - Navy/White Logo - One Size',
    'H-23PXG000101-WB-OSFM': 'Men\'s 6-Panel High Crown Snapback Cap - White/Black Logo - One Size',
    'H-23PXG000101-WG-OSFM': 'Men\'s 6-Panel High Crown Snapback Cap - White/Grey Logo - One Size',
    'H-23PXG000123-BW-OSFM': 'Men\'s Dog Tag 6-Panel High Crown Snapback Cap - Black/White Logo - One Size',
    'H-23PXG000123-GB-OSFM': 'Men\'s Dog Tag 6-Panel High Crown Snapback Cap - Grey/Black Logo - One Size',
    'H-23PXG000123-WG-OSFM': 'Men\'s Dog Tag 6-Panel High Crown Snapback Cap - White/Grey Logo - One Size',
    'H-23PXG000125-BG-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - Black/Grey Logo - One Size',
    'H-23PXG000125-BW-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - Black/White Logo - One Size',
    'H-23PXG000125-GB-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - Grey/Black Logo - One Size',
    'H-23PXG000125-NW-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - Navy/White Logo - One Size',
    'H-23PXG000125-WG-OSFM': 'Men\'s Dog Tag 5-Panel Snapback Cap - White/Grey Logo - One Size',
    'H-23PXG000126-WN-OSFM': 'Stretch Snapback Hat - White - One Size', # Este es de image_fbd6af.png, lo he ajustado
    'H-23PXG000166-BLK-OSFM': 'Stretch Snapback Hat - Black - One Size',
    'H-23PXG000166-WHT-OSFM': 'Stretch Snapback Hat - White - One Size',
    'H-23PXG000167-BW-OSFM': 'Scottsdale Trucker Snapback Hat - Black/White Logo - One Size',
    'H-23PXG000167-GB-OSFM': 'Scottsdale Trucker Snapback Hat - Grey/Black Logo - One Size',
    'H-23PXG000167-WHT-OSFM': 'Scottsdale Trucker Snapback Hat - White - One Size',
    'H-23PXG000167-WW-OSFM': 'Scottsdale Trucker Snapback Hat - White/White Logo - One Size',
    'H-23PXG000168-BLK-OSFM': 'Stretch Patch Snapback Hat - Black - One Size',
    'H-23PXG000168-GRY-OSFM': 'Stretch Patch Snapback Hat - Grey - One Size',
    'H-23PXG000168-NVY-OSFM': 'Stretch Patch Snapback Hat - Navy - One Size',
    'H-23PXG000168-WHT-OSFM': 'Stretch Patch Snapback Hat - White - One Size',
    'H-24PXG000203-2-BLK-OSFM': 'Women\'s Metallic Minimalist - Unstructured Hat - Black - One Size',
    'H-24PXG000203-2-WHT-OSFM': 'Women\'s Metallic Minimalist - Unstructured Hat - White - One Size',
    'H-24PXG000214-1-BLK-OSFM': 'Camper Flat Bill Snapback Cap - Black - One Size',
    'H-24PXG000214-1-WHT-OSFM': 'Camper Flat Bill Snapback Cap - White - One Size',
    'H-24PXG000218-1-OSFM': '6 Panel Structured Low Crown Snapback Cap - Black - One Size',
    'H-24PXG000219-OSFM': 'Women\'s Metallic Minimalist - Unstructured Hat - Grey - One Size',
    'H-24PXG000229-OSFM': 'US Navy Structured Hat Snapback - One Size',
    'H-24PXG000235-BW-OSFM': 'Dog Tag 6-Panel Low Crown Snapback - Black/White Logo - One Size',
    'H-24PXG000235-GB-OSFM': 'Dog Tag 6-Panel Low Crown Snapback - Grey/Black Logo - One Size',
    'H-24PXG000235-WG-OSFM': 'Dog Tag 6-Panel Low Crown Snapback - White/Grey Logo - One Size',
    'H-24PXG000239-OSFM': 'Women\'s Metallic Minimalist - Unstructured Hat - Light Blue - One Size',
    'H-24PXG000276-OSFM': '2025 Stars & Stripes Low Crown Cap - One Size',
    'H-24PXG000277-OSFM': '2025 Stars & Stripes Dog Tag Cap - One Size',
    'H-24PXG000278-OSFM': '2025 Stars & Stripes High Crown Cap - One Size',
    'H-24PXG000282-OSFM': '2025 Stars & Stripes Trucker Cap - One Size',
    'H-25PXG000283-OSFM': '2025 Stars & Stripes Dog Tag Trucker - One Size',
    'H-USMC-ADJ': 'PXG USMC Unstructured Hat - Adjustable',

    # image_fbd658.png (Accessories)
    'HC-JT-4623': 'Tour Series Blade Headcover - Black',
    'A-UAC18-FM': 'PXG Wedge Brush - Chrome',
    'A-UAC17-FM': 'PXG Wedge Brush - Black',
    'A-ALIGNSTICKS-WHT': 'PXG Player Alignment Sticks - White',
    'A-NX10SLOPE-PXG': 'PXG NX10 Rangefinder Slope Edition - White',
    'A-UAC28-FM': 'PXG Milled Divot Tool (Weighted)',
    'A-IHC62918PXG-COP': 'PXG Magnetic Ball Marker & Cap Clip - Rose Gold',
    'A-IHC62920PXG-BLK': 'PXG Magnetic Ball Marker & Cap Clip - Black',
    'A-DUO-PXG': 'PXG Golf Speaker - White',
    'A-ICU55715PXG-ALS': 'PXG Deluxe Alignment Stick Cover',
    'A-DARKNESS-COASTER': 'PXG Darkness Coaster',
    'HC-JT-1053-KIT': 'PXG 2022 Iron Cover Kit',
    'A-UAC29-FM': 'PXG (DRKNSS) Divot Tool',
    'A-Q25240-ASM': 'Milled Starburst Ball Marker',
    'A-ZNP53374-1': 'Darkness Leather Wrapped Divot Tool',
    'A-JT-4697': 'Darkness Alignment Stick Cover - Black',
    'A-1IBM65819PXGCAT': 'Copper Cactus Ball Marker',
    'A-Q23192-ASM-2': 'Chrome Logo Ball Marker',
    'A-Q25645-ASM-1': '2025 Stars & Stripes Ball Marker',
    'A-1IBM65820PXG-DT': '2023 Darkness Dog Tag Ball Marker',

    # Guantes (de image_fbd6af.png, sección de abajo)
    'G4-65201011HML-BLK': 'Men\'s LH Players Glove - Black ML',
    'G4-65201019HML-BLK': 'Men\'s LH Players Glove - Black M',
    'G4-65201019HMW-BLK': 'Women\'s RH Players Glove - Black M',
    'G4-65201019LHL-BLK': 'Men\'s RH Players Glove - Black L',
    'G4-65201019LXL-BLK': 'Men\'s RH Players Glove - Black XL',
    'G4-65201019MLC-BLK': 'Men\'s RH Players Glove - Cadet Black M',
    'G4-65201019RSC-BLK': 'Men\'s RH Players Glove - Cadet Black S',
    'G4-65201019RLC-BLK': 'Men\'s RH Players Glove - Cadet Black L',
    'G4-65201019RMLC-BLK': 'Men\'s RH Players Glove - Cadet Black ML',
    'G4-65201019RXLC-BLK': 'Men\'s RH Players Glove - Cadet Black XL',
    'G4-65201019RXL-BLK': 'Men\'s RH Players Glove - Black XL',
    'G4-65201019L-BLK': 'Men\'s RH Players Glove - Black L', # Duplicado, asegurar que es distinto
    'G4-65201019HMW-WHT': 'Women\'s RH Players Glove - White M',
    'G4-65201019LHL-WHT': 'Men\'s RH Players Glove - White L',
    'G4-65201019RSC-WHT': 'Men\'s RH Players Glove - Cadet White S',
    'G4-65201019RMLC-WHT': 'Men\'s RH Players Glove - Cadet White ML',
    'G4-65201019RXLC-WHT': 'Men\'s RH Players Glove - Cadet White XL',
    'G4-65201019RLC-WHT': 'Men\'s RH Players Glove - Cadet White L',
    'G4-65201019RXL-WHT': 'Men\'s RH Players Glove - White XL',
    'G4-65201019RL-WHT': 'Men\'s RH Players Glove - White L',
    'G4-65201019LL-WHT': 'Men\'s LH Players Glove - White L',
    'G4-652021019L-WHT': 'Women\'s LH Players Glove - White L',
    'G4-652021019MW-WHT': 'Women\'s RH Players Glove - White M',
    'G4-652021019RX-WHT': 'Women\'s RH Players Glove - White XL',
    'G4-652021019S-WHT': 'Women\'s RH Players Glove - White S',
    'G4-652021019SC-WHT': 'Men\'s RH Players Glove - Cadet White S',
    'G4-652021019MLC-WHT': 'Men\'s RH Players Glove - Cadet White M',
    # Asegúrate de revisar si hay más guantes o cualquier otro ítem que no haya capturado.
}

def group_codes_by_family(relations):
    """
    Agrupa los códigos de partes por su "familia" (prefijo principal)
    para la tabla de relaciones.
    """
    grouped_data = []
    
    # Crea un DataFrame para facilitar la manipulación y el ordenamiento
    df_relations = pd.DataFrame(relations)
    
    # Agrupa por Orden y luego por Código para asegurar un ordenamiento consistente
    # y para identificar la "familia"
    for (orden, sh), group in df_relations.groupby(['Orden', 'SH']):
        # Ordena los códigos dentro de cada grupo para que la familia principal aparezca primero
        group = group.sort_values(by='Código', key=lambda x: x.apply(lambda y: (len(y), y)))
        
        # Identifica la "familia" del primer código (el más corto si hay prefijos)
        # O si prefieres, puedes tener una lógica más específica para definir la familia
        first_code = group['Código'].iloc[0]
        # Una forma simple de obtener la familia es el prefijo común o el código base
        # Por ejemplo, 'B-PG-172-BGRY' -> 'B-PG-172'
        family = first_code.split('-')
        # Si tiene al menos 3 partes (ej. B-PG-172-BGRY), toma las primeras 3 (B-PG-172)
        # Si es un código más corto (ej. B-PG-172), lo toma completo
        if len(family) >= 3 and family[0] in ['B', 'H', 'A', 'HC', 'G4', 'GB']: # Asegura que es un prefijo conocido
            family = "-".join(family[:3])
            # Verifica si la 'familia' existe como clave en PART_DESCRIPTIONS
            if family not in PART_DESCRIPTIONS:
                # Si no existe como clave exacta, usa el código original como familia
                family = first_code
        else:
            family = first_code # Si no cumple el patrón, el código es su propia familia


        # Agrega la fila de la "familia" (código base)
        grouped_data.append({
            "Orden": orden,
            "Código": family, # Usamos el código "familia"
            "Descripción": PART_DESCRIPTIONS.get(family, "Descripción no disponible"),
            "SH": sh,
            "Familia": family # Columna para agrupar en el PDF
        })

        # Agrega las "variantes" si son diferentes a la familia
        for _, row in group.iterrows():
            if row['Código'] != family:
                grouped_data.append({
                    "Orden": orden, # Orden es el mismo
                    "Código": row['Código'], # El código completo de la variante
                    "Descripción": PART_DESCRIPTIONS.get(row['Código'], "Descripción no disponible"),
                    "SH": sh, # SH es el mismo
                    "Familia": family # Asigna la misma familia para agrupamiento
                })
                
    return pd.DataFrame(grouped_data).sort_values(by=['Orden', 'Familia', 'Código'])


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
            # ! IMPORTANTE: Aquí se corrige la fuente a "Helvetica-Bold"
            page.insert_text((150, y), family, fontsize=10, fontname="Helvetica-Bold")
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

def display_interactive_table(relations):
    """
    Muestra una tabla interactiva de relaciones en Streamlit.
    """
    if not relations:
        st.info("No se encontraron relaciones para mostrar en la tabla interactiva.")
        return

    df = pd.DataFrame(relations)

    st.subheader("Tabla Interactiva de Relaciones (Órdenes, Códigos, SH)")
    
    # Using st.dataframe for a simple interactive table
    st.dataframe(df)



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

    for oid, data in order_data.items():
        part_numbers = data.get("part_numbers", {})
        for part_num, count in part_numbers.items():
            if part_num in PART_DESCRIPTIONS:
                part_appearances[part_num] += count

    if not part_appearances:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    
    y_coordinate = 72
    left_margin_code = 50
    left_margin_desc = 150
    left_margin_count = 450

    headers = ["Código", "Descripción", "Apariciones"]
    # MODIFICADO: Se eliminó fontname="Helvetica" para usar la fuente predeterminada
    page.insert_text((left_margin_code, y_coordinate), headers[0], fontsize=12)
    page.insert_text((left_margin_desc, y_coordinate), headers[1], fontsize=12)
    page.insert_text((left_margin_count, y_coordinate), headers[2], fontsize=12)
    y_coordinate += 25

    for part_num in sorted(part_appearances.keys()):
        count = part_appearances[part_num]
        if count == 0:
            continue
        
        if y_coordinate > 750:
            page = doc.new_page(width=595, height=842)
            y_coordinate = 72
            # MODIFICADO: Encabezados en nueva página también usan fuente predeterminada
            page.insert_text((left_margin_code, y_coordinate), headers[0], fontsize=12)
            page.insert_text((left_margin_desc, y_coordinate), headers[1], fontsize=12)
            page.insert_text((left_margin_count, y_coordinate), headers[2], fontsize=12)
            y_coordinate += 25

        description = PART_DESCRIPTIONS[part_num]
        
        page.insert_text((left_margin_code, y_coordinate), part_num, fontsize=10)

        if len(description) > 40:
            page.insert_text((left_margin_desc, y_coordinate), description[:40], fontsize=9)
            page.insert_text((left_margin_desc, y_coordinate + 12), description[40:], fontsize=9)
            line_height = 25
        else:
            page.insert_text((left_margin_desc, y_coordinate), description, fontsize=10)
            line_height = 15

        page.insert_text((left_margin_count, y_coordinate), str(count), fontsize=10)
        y_coordinate += line_height

    total_appearances = sum(part_appearances.values())
    y_coordinate += 20
    
    if y_coordinate > 780:
        page = doc.new_page(width=595, height=842)
        y_coordinate = 72

    # MODIFICADO: Se eliminó fontname="Helvetica" para usar la fuente predeterminada
    page.insert_text(
        (left_margin_code, y_coordinate),
        f"TOTAL GENERAL DE APARICIONES: {total_appearances}",
        fontsize=14,
        color=(0, 0, 1) # Color azul
    )

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

# --- NUEVAS FUNCIONES PARA CLASIFICAR Y GENERAR PDFs POR CATEGORÍA ---

def classify_item(item_code, item_description):
    """Clasifica un ítem en 'Pelotas', 'Gorras', 'Accesorios'."""
    item_code_upper = item_code.upper()
    item_description_upper = item_description.upper()

    if item_code_upper.startswith('GB-DOZ-') or "GOLF BALL" in item_description_upper:
        return "Pelotas"
    elif item_code_upper.startswith('H-') or ("HAT" in item_description_upper or "CAP" in item_description_upper):
        return "Gorras"
    # Accesorios - Si no es pelota ni gorra, y empieza con A- o HC- o G4- (guantes)
    elif item_code_upper.startswith(('A-', 'HC-', 'G4-')):
        return "Accesorios"
    return "Otros" # Para ítems que no encajan en ninguna categoría definida

def create_category_table(relations, category_name):
    """
    Crea una tabla PDF con un listado de códigos, descripciones y SH para una categoría específica.
    """
    unique_items_in_category = {} # Usaremos un diccionario para guardar el primer SH encontrado
    category_data = []

    for rel in relations:
        if classify_item(rel["Código"], rel["Descripción"]) == category_name:
            item_code = rel["Código"]
            item_description = rel["Descripción"]
            item_sh = rel["SH"] # Capturamos el SH

            # Si el código ya se ha añadido, no lo volvemos a añadir a unique_items_in_category
            # pero sí podemos actualizar el SH si queremos el último o el primero.
            # Por simplicidad, tomaremos el primer SH que encontremos para cada código.
            if item_code not in unique_items_in_category:
                unique_items_in_category[item_code] = {
                    "Descripción": item_description,
                    "SH": item_sh # Guardamos el SH asociado
                }

    # Construir category_data a partir del diccionario unique_items_in_category
    for code, details in unique_items_in_category.items():
        category_data.append({
            "Código": code,
            "Descripción": details["Descripción"],
            "SH": details["SH"] # Agregamos el SH aquí
        })

    if not category_data:
        return None

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 50

    # Título de la categoría
    page.insert_text((50, y), f"LISTADO DE {category_name.upper()}",
                     fontsize=16, color=(0, 0, 1), fontname="helv")
    y += 30

    # Encabezados - ¡Aquí es donde agregamos 'SH'!
    headers = ["Código", "Descripción", "SH"]
    page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
    page.insert_text((200, y), headers[1], fontsize=12, fontname="helv")
    page.insert_text((450, y), headers[2], fontsize=12, fontname="helv") # Ajustar posición para SH
    y += 20

    # Convertir a DataFrame para ordenar por Código
    df_category = pd.DataFrame(category_data).sort_values(by=["Código"])

    for _, row in df_category.iterrows():
        if y > 750:
            page = doc.new_page(width=595, height=842)
            y = 50
            # Reinsertar encabezados en nueva página
            page.insert_text((50, y), headers[0], fontsize=12, fontname="helv")
            page.insert_text((200, y), headers[1], fontsize=12, fontname="helv")
            page.insert_text((450, y), headers[2], fontsize=12, fontname="helv") # Reinsertar SH
            y += 20

        page.insert_text((50, y), row["Código"], fontsize=10)

        # Descripción en múltiples líneas si es necesario
        desc = row["Descripción"]
        if len(desc) > 50: # Ajustar el límite de caracteres para la descripción
            page.insert_text((200, y), desc[:50], fontsize=9)
            page.insert_text((200, y + 12), desc[50:], fontsize=9)
            y_offset_for_next_line = 12
        else:
            page.insert_text((200, y), desc, fontsize=10)
            y_offset_for_next_line = 0

        # Agregar el SH
        page.insert_text((450, y), row["SH"], fontsize=10) # Posición para el SH

        y += 15 + y_offset_for_next_line # Espacio entre filas, considerando la descripción multilinea

    return doc


def merge_documents(build_order, build_map, ship_map, order_meta, pickup_flag, all_relations, all_two_day):
    doc = fitz.open()
    pickups = [oid for oid in build_order if order_meta[oid]["pickup"]] if pickup_flag else []

    # 1. Insertar tabla de relaciones (con agrupamiento por familia)
    relations_table = create_relations_table(all_relations)
    if relations_table:
        doc.insert_pdf(relations_table)
        insert_divider_page(doc, "Resumen de Partes") # Separador

    # 2. Insertar página de SH 2 day
    two_day_page = create_2day_shipping_page(all_two_day)
    if two_day_page:
        doc.insert_pdf(two_day_page)
        insert_divider_page(doc, "Resumen de Apariciones de Partes") # Separador

    # 3. Insertar resumen de apariciones de partes
    part_summary = create_part_numbers_summary(order_meta)
    if part_summary:
        doc.insert_pdf(part_summary)
        insert_divider_page(doc, "Listado de Pelotas") # Separador

    # --- NUEVA SECCIÓN: Páginas por Categoría ---
    # 4. Insertar página de Pelotas
    pelotas_doc = create_category_table(all_relations, "Pelotas")
    if pelotas_doc:
        doc.insert_pdf(pelotas_doc)
        insert_divider_page(doc, "Listado de Gorras") # Separador para la siguiente categoría

    # 5. Insertar página de Gorras
    gorras_doc = create_category_table(all_relations, "Gorras")
    if gorras_doc:
        doc.insert_pdf(gorras_doc)
        insert_divider_page(doc, "Listado de Accesorios") # Separador para la siguiente categoría

    # 6. Insertar página de Accesorios
    accesorios_doc = create_category_table(all_relations, "Accesorios")
    if accesorios_doc:
        doc.insert_pdf(accesorios_doc)
        insert_divider_page(doc, "Documentos Principales") # Separador antes de los docs originales

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
