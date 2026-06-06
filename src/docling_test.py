from docling.document_converter import DocumentConverter

converter = DocumentConverter()

result = converter.convert(
    "input/sample.pdf"
)

markdown = result.document.export_to_markdown()

print(markdown[:2000])