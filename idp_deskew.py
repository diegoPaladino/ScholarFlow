"""Conservative global deskew; geometry and OCR must use the same output image."""
from io import BytesIO
import math

def deskew(document):
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
    edges=cv2.Canny(gray,50,150)
    lines=cv2.HoughLinesP(edges,1,np.pi/1800, max(30,w//12),minLineLength=max(30,w//5),maxLineGap=max(5,w//100))
    angles=[]
    if lines is not None:
        for x1,y1,x2,y2 in lines[:,0]:
            a=math.degrees(math.atan2(int(y2)-int(y1),int(x2)-int(x1)))
            a=(a+90)%180-90
            if abs(a)<=12: angles.append(a)
    angle=float(np.median(angles)) if len(angles)>=3 else 0.0
    if len(angles)<3 or float(np.median(np.abs(np.asarray(angles)-angle)))>1.5 or abs(angle)<.1: angle=0.0
    matrix=cv2.getRotationMatrix2D((w/2,h/2),angle,1)
    if angle:
        corners=np.array([[0,0],[w,0],[0,h],[w,h]],dtype=float)
        transformed=corners@matrix[:,:2].T+matrix[:,2]
        lo=np.floor(transformed.min(axis=0)); hi=np.ceil(transformed.max(axis=0))
        nw,nh=map(int,hi-lo)
        if nw*nh>25_000_000: raise ValueError('Output pixel limit exceeded')
        matrix[:,2]-=lo
        gray=cv2.warpAffine(gray,matrix,(nw,nh),borderValue=255)
    ok,png=cv2.imencode('.png',gray)
    if not ok: raise RuntimeError('PNG encoding failed')
    return {'image':png.tobytes(),'angle':angle,'matrix':matrix.tolist(),'line_count':len(angles),'needs_review':True}
