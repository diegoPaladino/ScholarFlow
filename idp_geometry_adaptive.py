"""Experimental grid proposals; partial lines are not proof of complete cells."""
from io import BytesIO

def detect_adaptive(document):
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
    block=min(51,(min(h,w)-1)//2*2+1)
    ink=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,block,12)
    def lines(horizontal):
        length=w if horizontal else h
        def kernel(n): return np.ones((1,n) if horizontal else (n,1),np.uint8)
        closed=cv2.morphologyEx(ink,cv2.MORPH_CLOSE,kernel(max(3,length//100)))
        return cv2.morphologyEx(closed,cv2.MORPH_OPEN,kernel(max(15,length//18)))
    hor,ver=lines(True),lines(False)
    mask=cv2.bitwise_or(hor,ver)
    _,_,stats,_=cv2.connectedComponentsWithStats(mask)
    def edges(p,length,offset,total):
        hits=np.flatnonzero(p>=length*.45)
        groups=np.split(hits,np.where(np.diff(hits)>1)[0]+1)
        return [(offset+float(g.mean())+.5)/total for g in groups if len(g)]
    grids=[]
    for x,y,bw,bh,_ in stats[1:]:
        if bw<w*.15 or bh<h*.035: continue
        rows=edges(np.count_nonzero(hor[y:y+bh,x:x+bw],axis=1),bw,y,h)
        cols=edges(np.count_nonzero(ver[y:y+bh,x:x+bw],axis=0),bh,x,w)
        if 3<=len(rows)<=201 and 3<=len(cols)<=201:
            grids.append({'rows':rows,'columns':cols,'needs_review':True})
    return {'grids':sorted(grids,key=lambda g:(g['rows'][0],g['columns'][0])),'needs_review':True}
