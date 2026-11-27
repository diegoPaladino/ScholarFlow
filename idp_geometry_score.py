"""Heuristic grid screening; scores are not probabilities or approval."""
from statistics import median
from idp_grid import _edges

def assess_grid(grid, *, min_relative_gap=0.20, max_cells=1000):
    if not 0 < min_relative_gap <= 1 or type(max_cells) is not int or max_cells < 1:
        raise ValueError('Invalid screening parameters')
    rows, cols = _edges(grid['rows']), _edges(grid['columns'])
    flags=[]
    ratios=[]
    for name, edges in [('rows',rows),('columns',cols)]:
        gaps=[b-a for a,b in zip(edges,edges[1:])]
        ratio=min(gaps)/median(gaps)
        ratios.append(ratio)
        if len(edges)<3: flags.append(name+'_insufficient')
        if ratio<min_relative_gap: flags.append(name+'_close_boundaries')
    cells=(len(rows)-1)*(len(cols)-1)
    if cells>max_cells: flags.append('cell_limit')
    return {'rows':list(rows),'columns':list(cols),'cell_count':cells,
            'relative_gaps':ratios,'flags':flags,'needs_review':True,
            'screening_pass':not flags}

def rank_grids(grids):
    """Rank only proposals sharing a coordinate frame; never merge or approve."""
    assessed=[dict(assess_grid(g),candidate_index=i) for i,g in enumerate(grids)]
    return sorted(assessed,key=lambda g:(not g['screening_pass'],len(g['flags']),-min(g['relative_gaps']),g['candidate_index']))
