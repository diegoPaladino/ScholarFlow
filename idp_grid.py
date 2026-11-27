"""Conservative assignment to explicitly supplied normalized grid boundaries."""
import math

def _edges(values):
    v=tuple(values)
    if len(v)<2 or len(v)>201 or any(type(x) not in (int,float) or not math.isfinite(x) or not 0<=x<=1 for x in v) or any(a>=b for a,b in zip(v,v[1:])):
        raise ValueError('Invalid grid boundaries')
    return v

def reconstruct(page, *, rows, columns):
    rows,columns=_edges(rows),_edges(columns)
    cells=[[[] for _ in columns[1:]] for _ in rows[1:]]
    unresolved=[]
    for word in page['words']:
        x0,y0,x1,y1=word['bbox']
        if not (0<=x0<x1<=1 and 0<=y0<y1<=1): raise ValueError('Invalid word bounds')
        rr=[i for i,(a,b) in enumerate(zip(rows,rows[1:])) if a<=y0 and y1<=b]
        cc=[i for i,(a,b) in enumerate(zip(columns,columns[1:])) if a<=x0 and x1<=b]
        if len(rr)==len(cc)==1: cells[rr[0]][cc[0]].append(word)
        else: unresolved.append(word)
    return {'page':page['page'],'cells':[[{'text':' '.join(w['text'] for w in sorted(cell,key=lambda w:(w['bbox'][1],w['bbox'][0]))) or None,'words':cell} for cell in row] for row in cells],'unresolved':unresolved,'needs_review':True}
