import fitz

pdf = fitz.open("input/sample.pdf")

print("Total Pages:", len(pdf))