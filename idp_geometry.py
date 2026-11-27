"""Conservative ruled-grid proposals in normalized displayed-image coordinates."""
from io import BytesIO

def detect_grids(document):
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
    if not isinstance(document,bytes) or not 0<len(document)<=50_000_000 or not document.startswith((b'\xff\xd8\xff',b'\x89PNG\r\n\x1a\n')):
        raise ValueError('Expected PNG or JPEG')
    with Image.open(BytesIO(document)) as im:
        if im.width*im.height>25_000_000: raise ValueError('Pixel limit exceeded')
        gray=np.asarray(ImageOps.exif_transpose(im).convert('L'))
    h,w=gray.shape
    if min(h,w)<40: raise ValueError('Image too small')
    _,ink=cv2.threshold(gray,0,255,cv2.THRESH_BINARY_INV+cv2.THRESH_OTSU)
    horizontal=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((1,max(15,w//15)),np.uint8))
    vertical=cv2.morphologyEx(ink,cv2.MORPH_OPEN,np.ones((max(15,h//25),1),np.uint8))
    mask=cv2.bitwise_or(horizontal,vertical)
    n,_,stats,_=cv2.connectedComponentsWithStats(mask)
    def edges(projection, length, offset, total):
        hits=np.flatnonzero(projection>=length*.65)
        groups=np.split(hits,np.where(np.diff(hits)>1)[0]+1)
        return [(offset+float(g.mean())+.5)/total for g in groups if len(g)]
    grids=[]
    for x,y,bw,bh,area in stats[1:]:
        if bw<w*.15 or bh<h*.035: continue
        rows=edges(np.count_nonzero(horizontal[y:y+bh,x:x+bw],axis=1),bw,y,h)
        cols=edges(np.count_nonzero(vertical[y:y+bh,x:x+bw],axis=0),bh,x,w)
        if 3<=len(rows)<=201 and 3<=len(cols)<=201:
            grids.append({'rows':rows,'columns':cols,'needs_review':True})
    return {'grids':sorted(grids,key=lambda g:(g['rows'][0],g['columns'][0])),'needs_review':True}
