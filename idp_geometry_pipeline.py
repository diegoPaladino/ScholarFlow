"""Image-only review proposals in one explicit coordinate frame; no auto approval."""
from idp_deskew import deskew
from idp_geometry import detect_grids
from idp_geometry_adaptive import detect_adaptive
from idp_geometry_score import rank_grids
from idp_spatial import extract_spatial
from idp_grid import reconstruct
import hashlib

def propose(document, *, ocr=None):
    corrected=deskew(document)
    image=corrected['image']
    frame=hashlib.sha256(image).hexdigest()
    page=extract_spatial(image,ocr=ocr)['pages'][0]
    grids=[]
    sources=[]
    for name, detector in [('original',detect_grids),('adaptive',detect_adaptive)]:
        for grid in detector(image)['grids']:
            grids.append({'rows':[float(x) for x in grid['rows']], 'columns':[float(x) for x in grid['columns']]})
            sources.append(name)
    candidates=[dict(g,source=sources[g['candidate_index']],frame_id=frame) for g in rank_grids(grids)]
    return {'frame_id':frame,'image':image,'angle':corrected['angle'],'matrix':corrected['matrix'],'page':page,'candidates':candidates,'needs_review':True}

def review_grid(result, *, frame_id, rows, columns):
    if frame_id != result['frame_id'] or hashlib.sha256(result['image']).hexdigest()!=frame_id:
        raise ValueError('Coordinate frame mismatch')
    return dict(reconstruct(result['page'],rows=rows,columns=columns),frame_id=frame_id)
