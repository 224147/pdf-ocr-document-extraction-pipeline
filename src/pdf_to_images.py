import fitz
import os

pdf_path = "input/sample.pdf"

pdf = fitz.open(pdf_path)

os.makedirs("output/images", exist_ok=True)

for page_num in range(len(pdf)):

    page = pdf.load_page(page_num)

    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

    image_path = f"output/images/page_{page_num+1}.png"

    pix.save(image_path)

    print("Saved:", image_path)

print("Done")