from PySide6.QtGui import QPixmap
import os

src = r'c:\Users\kk980\Developments\assyManager\client\assets\app_icon.png'
dst = r'c:\Users\kk980\Developments\assyManager\client\assets\app_icon_fixed.png'

if os.path.exists(src):
    pm = QPixmap(src)
    print(f'Original: {pm.width()}x{pm.height()}')
    if not pm.isNull():
        resized = pm.scaled(256, 256)
        resized.save(dst)
        print('Saved resized icon.')
    else:
        print('Failed to load image.')
else:
    print('Src not found.')
