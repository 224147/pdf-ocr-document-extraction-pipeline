import easyocr

reader = easyocr.Reader(['en'])

result = reader.readtext(
    "output/images/page_1.png"
)

for item in result:
    print(item[1])