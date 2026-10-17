# The desktop tray only reads ICO files, whose payloads can be PNG or BMP.
# Pillow's default hook collects every image codec, including an 8 MB AVIF DLL.
hiddenimports = ['PIL.IcoImagePlugin', 'PIL.PngImagePlugin', 'PIL.BmpImagePlugin']
