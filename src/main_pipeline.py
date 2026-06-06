#Step 1
from docling.document_converter import DocumentConverter

converter = DocumentConverter()

result = converter.convert("input/sample.pdf")

docling_md = result.document.export_to_markdown()

#Step 2
import fitz
import easyocr
import os

reader = easyocr.Reader(['en'])

pdf = fitz.open("input/sample.pdf")

ocr_text = ""

os.makedirs("output/images", exist_ok=True)

for page_num in range(len(pdf)):

    page = pdf.load_page(page_num)

    pix = page.get_pixmap(matrix=fitz.Matrix(2,2))

    image_path = f"output/images/page_{page_num+1}.png"

    pix.save(image_path)

    result = reader.readtext(image_path)

    page_text = "\n".join(
        [item[1] for item in result]
    )

    ocr_text += f"\n\n## OCR Page {page_num+1}\n"

    ocr_text += page_text

#Step 3

final_markdown = f"""
# Document Extraction Pipeline Output

# Docling Content

{docling_md}

# OCR Content

{ocr_text}
"""

#step 4

with open(
    "output/final_output.md",
    "w",
    encoding="utf-8"
) as f:

    f.write(final_markdown)

#Step 5

import json

data = {
    "docling_content": docling_md,
    "ocr_content": ocr_text
}

with open(
    "output/final_output.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        data,
        f,
        indent=4,
        ensure_ascii=False
    )

