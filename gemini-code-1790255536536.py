import streamlit as st
import re
import io
import zipfile
from pathlib import Path
from pypdf import PdfReader

st.set_page_config(page_title="BOE to Obsidian", page_icon="📚", layout="centered")

st.title("📚 BOE a Obsidian Markdown")
st.write("Sube el PDF consolidado del BOE para generar las notas organizadas por Libros.")

# Formulario de entrada
pdf_file = st.file_uploader("Sube el PDF de la Ley", type=["pdf"])
terminacion = st.text_input("Sigla para los artículos (ej. LEC, CC, CP)", value="BOE").strip()

if st.button("Procesar y Generar Notas", disabled=not pdf_file):
    with st.spinner("Procesando documento... Esto puede tardar unos segundos."):
        reader = PdfReader(pdf_file)
        texto_raw = ""
        for page in reader.pages:
            texto_raw += (page.extract_text() or "") + "\n"

        pos_inicio = texto_raw.find("TEXTO CONSOLIDADO")
        texto_util = texto_raw[pos_inicio if pos_inicio != -1 else 0:]
        texto_util = re.sub(
            r'BOLETÍN OFICIAL DEL ESTADO\s*\n\s*LEGISLACIÓN CONSOLIDADA\s*\n\s*Página \d+',
            '',
            texto_util
        )

        # Detectar división por Libros o Títulos
        hay_libros = re.search(r'\nLIBRO\s+(?:PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|I|II|III|IV|V)\b', texto_util, re.IGNORECASE)
        divisiones = []

        if hay_libros:
            pattern_div = re.compile(r'\n((?:TÍTULO PRELIMINAR|LIBRO\s+[^\n]+))\n', re.IGNORECASE)
            matches_div = list(pattern_div.finditer(texto_util))
            for i, m in enumerate(matches_div):
                nombre_div = re.sub(r'[\.\:\,\;\/]', '', m.group(1).strip())
                nombre_carpeta = re.sub(r'\s+', '_', nombre_div)
                start = m.start()
                end = matches_div[i+1].start() if i+1 < len(matches_div) else len(texto_util)
                divisiones.append((nombre_carpeta, start, end))
        else:
            pattern_div = re.compile(r'\n((?:TÍTULO PRELIMINAR|TÍTULO\s+[^\n]+))\n', re.IGNORECASE)
            matches_div = list(pattern_div.finditer(texto_util))
            if matches_div:
                for i, m in enumerate(matches_div):
                    nombre_div = re.sub(r'[\.\:\,\;\/]', '', m.group(1).strip())
                    nombre_carpeta = re.sub(r'\s+', '_', nombre_div)[:50]
                    start = m.start()
                    end = matches_div[i+1].start() if i+1 < len(matches_div) else len(texto_util)
                    divisiones.append((nombre_carpeta, start, end))
            else:
                divisiones.append(("Articulos", 0, len(texto_util)))

        pattern_art = re.compile(r'(?:^|\n)Artículo\s+([0-9]+(?:\s+[a-z]+)?)\.\s*')
        pos_dispos = re.search(r'\nDisposición adicional', texto_util, re.IGNORECASE)
        limite_global = pos_dispos.start() if pos_dispos else len(texto_util)

        # Crear archivo ZIP en memoria (BytesIO)
        zip_buffer = io.BytesIO()
        total_creados = 0

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            for carpeta, start, end in divisiones:
                end_efectivo = min(end, limite_global) if start < limite_global else end
                sec_txt = texto_util[start:end_efectivo]
                matches_art = list(pattern_art.finditer(sec_txt))

                for i, m in enumerate(matches_art):
                    num_art = re.sub(r'\s+', ' ', m.group(1).strip())
                    art_start = m.end()
                    art_end = matches_art[i+1].start() if i+1 < len(matches_art) else len(sec_txt)

                    raw_block = sec_txt[art_start:art_end]
                    lineas = [l.strip() for l in raw_block.split('\n') if l.strip()]
                    if not lineas:
                        continue

                    primer_salto = raw_block.find('\n')
                    tiene_epigrafe = primer_salto != 0 and bool(raw_block[:primer_salto].strip())

                    if tiene_epigrafe:
                        partes_tit, partes_cuerpo = [], []
                        en_cuerpo = False
                        for l in lineas:
                            if not en_cuerpo:
                                partes_tit.append(l)
                                if l.endswith('.') or l.endswith(')') or l.endswith('»'):
                                    en_cuerpo = True
                            else:
                                partes_cuerpo.append(l)
                        titulo_art = " ".join(partes_tit).strip()
                        cuerpo_art = "\n\n".join(partes_cuerpo).strip()
                    else:
                        titulo_art = ""
                        cuerpo_art = "\n\n".join(lineas).strip()

                    nombre_fichero = re.sub(r'[\\/*?:"<>|]', '', f"Art. {num_art} {terminacion}.md")
                    
                    if titulo_art:
                        md_content = f"# Art. {num_art} {terminacion}\n\n**{titulo_art}**\n\n{cuerpo_art}\n"
                    else:
                        md_content = f"# Art. {num_art} {terminacion}\n\n{cuerpo_art}\n"

                    # Ruta dentro del ZIP
                    zip_path = f"{terminacion}_Obsidian/{carpeta}/{nombre_fichero}"
                    zipf.writestr(zip_path, md_content.encode("utf-8"))
                    total_creados += 1

        zip_buffer.seek(0)
        st.success(f"¡Listo! Se han generado {total_creados} notas Markdown.")
        
        st.download_button(
            label="📥 Descargar ZIP para Obsidian",
            data=zip_buffer,
            file_name=f"{terminacion}_Obsidian.zip",
            mime="application/zip"
        )