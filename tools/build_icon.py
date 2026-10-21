from pathlib import Path
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parents[1]
im=Image.new('RGBA',(256,256),(0,0,0,0));d=ImageDraw.Draw(im)
d.rounded_rectangle((8,8,248,248),radius=51,fill='#087f75')
d.polygon([(128,39),(217,128),(128,217),(39,128)],fill='white')
d.polygon([(128,66),(190,128),(128,190),(66,128)],fill='#087f75')
d.polygon([(128,91),(165,128),(128,165),(91,128)],fill='#f5c76b')
im.save(root/'assets/workbench.png')
im.save(root/'assets/workbench.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
