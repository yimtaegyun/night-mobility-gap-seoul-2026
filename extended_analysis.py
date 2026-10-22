#!/usr/bin/env python3
"""Reproduce time-window, candidate-selection and source-consistency checks offline."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
from scipy.optimize import milp, Bounds, LinearConstraint
from scipy.sparse import csr_matrix, hstack, vstack, eye
from analysis import ROOT, R, CSV_NAME, sphere, read_xlsx, dump_csv


def distance_matrix(a,b):
    # Independent all-pairs haversine implementation; not KDTree.
    lat1,lon1=np.deg2rad(np.asarray(a,float)).T
    lat2,lon2=np.deg2rad(np.asarray(b,float)).T
    q=np.sin((lat1[:,None]-lat2[None,:])/2)**2+np.cos(lat1[:,None])*np.cos(lat2[None,:])*np.sin((lon1[:,None]-lon2[None,:])/2)**2
    return 2*R*np.arcsin(np.sqrt(np.clip(q,0,1)))


def make_model(stops, radius=500, threshold=2000, weight='late'):
    outside=stops.nearest_n_m.to_numpy()>radius
    pool=stops.loc[outside & (stops.late>=threshold)].sort_values('NODE_ID')
    targets=stops.loc[outside]
    coverage=distance_matrix(pool[['lat','lon']],targets[['lat','lon']])<=radius+1e-8
    weights=targets[weight].to_numpy(np.int64)
    return pool,targets,coverage,weights


def greedy(coverage,weights,k=3):
    chosen=[];covered=np.zeros(len(weights),bool);increments=[]
    for _ in range(k):
        scores=coverage @ np.where(covered,0,weights)
        if chosen: scores[chosen]=-1
        j=int(np.argmax(scores))
        if scores[j]<=0: break
        increments.append(int(scores[j]));chosen.append(j);covered|=coverage[j]
    return chosen,covered,increments


def main(data, out, solve=True):
    raw=pd.read_csv(data/CSV_NAME,encoding='cp949',low_memory=False,
        dtype={'표준버스정류장ID':str,'버스정류장ARS번호':str,'노선번호':str})
    bc=[f'{h if h else "00"}시승차총승객수' for h in range(24)]
    road=raw.loc[raw['교통수단타입명'].ne('기타')].copy()
    non=road.loc[road['교통수단타입명'].ne('서울심야버스') & road['표준버스정류장ID'].str.fullmatch(r'\d{9}').fillna(False)]
    hourly=non.groupby('표준버스정류장ID',sort=True)[bc].sum()
    hourly.columns=[f'h{h:02}' for h in range(24)]
    stops=pd.read_csv(out/'stops.csv',dtype={'NODE_ID':str,'ARS':str,'nearest_n_id':str})
    stops=stops.merge(hourly,left_on='NODE_ID',right_index=True,how='left',validate='1:1')
    windows={'late':[21,22,23],'b23':[23],'night00_03':[0,1,2,3],
             'night01_03':[1,2,3],'night02_03':[2,3],**{f'b{h:02}':[h] for h in range(5)}}
    for name,hs in windows.items():
        counts=stops[[f'h{h:02}' for h in hs]].sum(axis=1)
        if name in stops: assert np.array_equal(stops[name],counts)
        stops[name]=counts
    dump_csv(stops,out/'stops_hourly.csv')
    m=stops.loc[stops.coordinate_matched].copy().reset_index(drop=True)
    rows=[]
    for name in windows:
        for radius in [300,500,800]:
            inside=m.nearest_n_m<=radius;tot=int(m[name].sum());outside=int(m.loc[~inside,name].sum())
            rows.append({'window':name,'radius_m':radius,'matched_boardings':tot,'outside_boardings':outside,
                'outside_share':outside/tot if tot else None,'unmatched_boardings':int(stops.loc[~stops.coordinate_matched,name].sum()),
                'outside_stops_with_any_boarding':int(((m[name]>0)&~inside).sum())})
    dump_csv(rows,out/'time_window_sensitivity.csv')
    ns=pd.read_csv(out/'n_stops.csv',dtype={'NODE_ID':str})
    independently=distance_matrix(m[['lat','lon']],ns[['lat','lon']]).min(axis=1)
    max_error=float(np.abs(independently-m.nearest_n_m).max())
    assert max_error<1e-5
    for radius in [300,500,800,1000]:
        assert np.array_equal(independently<=radius,m.nearest_n_m.to_numpy()<=radius)

    trials=[]
    settings=[(r,2000,'late') for r in [300,500,800]]
    settings += [(500,t,'late') for t in [0,1000,3000,5000]]
    settings += [(500,2000,w) for w in ['b23','night00_03','night01_03']]
    baseids=set(pd.read_csv(out/'scenario_three_hubs.csv',dtype={'NODE_ID':str}).NODE_ID)
    for radius,threshold,weight in settings:
        pool,target,cover,w=make_model(m,radius,threshold,weight)
        selected,covered,gains=greedy(cover,w)
        ids=pool.iloc[selected].NODE_ID.tolist();names=pool.iloc[selected].stop_name.tolist()
        # Always additionally report the original 21-23 weight to permit
        # comparisons between different objectives on a common denominator.
        trials.append({'radius_m':radius,'minimum_late':threshold,'weight_window':weight,'candidate_count':len(pool),
            'selected_ids':'|'.join(ids),'selected_names':' / '.join(names),'retained_base_hubs':len(baseids & set(ids)),
            'additional_weight':int(w[covered].sum()),'additional_late':int(target.loc[covered,'late'].sum()),
            'new_stops':int(covered.sum())})
    dump_csv(trials,out/'candidate_robustness.csv')

    pool,target,cover,weights=make_model(m)
    gs,gc,gi=greedy(cover,weights)
    assert pool.iloc[gs].NODE_ID.tolist()==pd.read_csv(out/'scenario_three_hubs.csv',dtype={'NODE_ID':str}).NODE_ID.tolist()
    assert int(weights[gc].sum())==225811 and int(gc.sum())==48
    comparisons=[]
    def compare(name,indices):
        union=cover[indices].any(axis=0)
        comparisons.append({'method':name,'selected_names':' / '.join(pool.iloc[indices].stop_name),
            'selected_ids':'|'.join(pool.iloc[indices].NODE_ID),'additional_late':int(weights[union].sum()),'new_stops':int(union.sum())})
    compare('greedy_area',gs)
    compare('top_own_late',np.argsort(-pool.late.to_numpy(),kind='stable')[:3])
    compare('top_own_23',np.argsort(-pool.b23.to_numpy(),kind='stable')[:3])
    rng=np.random.default_rng(20261022)
    random_gains=np.array([weights[cover[rng.choice(len(pool),3,replace=False)].any(axis=0)].sum() for _ in range(1000)])
    random_result={'seed':20261022,'samples':1000,'median_additional_late':float(np.median(random_gains)),
        'p05':float(np.quantile(random_gains,.05)),'p95':float(np.quantile(random_gains,.95)),
        'interpretation':'Random candidate triples, not an uncertainty interval or causal significance test.'}
    optimum={'performed':False}
    if solve:
        keep=cover.any(axis=0)&(weights>0);mat=cover[:,keep];ww=weights[keep]
        nc,nj=mat.shape
        constraints=vstack([hstack([-csr_matrix(mat.T.astype(float)),eye(nj,format='csr')]),
                             csr_matrix(np.r_[np.ones(nc),np.zeros(nj)][None,:])],format='csc')
        objective=np.r_[np.zeros(nc),-ww/1000.0]
        result=milp(objective,integrality=np.r_[np.ones(nc),np.zeros(nj)],bounds=Bounds(0,1),
            constraints=LinearConstraint(constraints,-np.inf,np.r_[np.zeros(nj),3]),
            options={'time_limit':60,'mip_rel_gap':1e-9})
        optimum={'performed':True,'status':int(result.status),'message':str(result.message),
            'solver':'SciPy milp / HiGHS','relative_gap':float(result.mip_gap) if result.x is not None else None,
            'upper_bound_boardings':float(-result.mip_dual_bound*1000) if result.x is not None else None,
            'scope':'Only 334 eligible candidates, fixed 500m spherical radius, 21-23 monthly boardings, <=3 hubs. No operating constraints.'}
        if result.x is not None:
            ids=np.flatnonzero(result.x[:nc]>.5);u=cover[ids].any(axis=0)
            optimum.update({'selected_ids':pool.iloc[ids].NODE_ID.tolist(), 'selected_names':pool.iloc[ids].stop_name.tolist(),
                'additional_late':int(weights[u].sum()),'greedy_fraction':int(weights[gc].sum())/int(weights[u].sum())})
            compare('milp_best_found',ids)
    dump_csv(comparisons,out/'method_comparison.csv')
    (out/'selection_validation.json').write_text(json.dumps({'optimization':optimum,'random_benchmark':random_result},ensure_ascii=False,indent=2),encoding='utf-8')

    routes=read_xlsx(data/'서울시버스노선별정류소정보(20260902).xlsx')
    loc=read_xlsx(data/'서울시버스정류소위치정보(20260902).xlsx')
    routecoords=routes[['NODE_ID','X좌표','Y좌표']].drop_duplicates().copy()
    coord=loc[['NODE_ID','X좌표','Y좌표']].merge(routecoords,on='NODE_ID',suffixes=('_location','_route'))
    for column in coord.columns[1:]:coord[column]=pd.to_numeric(coord[column],errors='coerce')
    coord=coord.dropna()
    a=coord[['Y좌표_location','X좌표_location']].to_numpy();b=coord[['Y좌표_route','X좌표_route']].to_numpy()
    lat1,lon1=np.deg2rad(a).T;lat2,lon2=np.deg2rad(b).T
    q=np.sin((lat1-lat2)/2)**2+np.cos(lat1)*np.cos(lat2)*np.sin((lon1-lon2)/2)**2
    coord['difference_m']=2*R*np.arcsin(np.sqrt(np.clip(q,0,1)))
    discrepancies=coord.groupby('NODE_ID',as_index=False).difference_m.max().sort_values('difference_m',ascending=False)
    dump_csv(discrepancies,out/'coordinate_consistency.csv')
    # A source disagreement is not silently "corrected". Assess how using the
    # alternate route coordinates or dropping large disagreements affects C(500).
    alt=routes[['NODE_ID','Y좌표','X좌표']].drop_duplicates('NODE_ID').set_index('NODE_ID')
    alt=alt.apply(pd.to_numeric,errors='coerce').rename(columns={'Y좌표':'lat','X좌표':'lon'})
    alternate_m=m[['NODE_ID','lat','lon','late']].set_index('NODE_ID').copy()
    alternate_n=ns[['NODE_ID','lat','lon']].set_index('NODE_ID').copy()
    alternate_m.update(alt);alternate_n.update(alt)
    ad=distance_matrix(alternate_m[['lat','lon']],alternate_n[['lat','lon']]).min(axis=1)
    discrepant=set(discrepancies.loc[discrepancies.difference_m>100,'NODE_ID'])
    reduced=m.loc[~m.NODE_ID.isin(discrepant)]
    reduced_n=ns.loc[~ns.NODE_ID.isin(discrepant)]
    rd=distance_matrix(reduced[['lat','lon']],reduced_n[['lat','lon']]).min(axis=1)
    coord_sensitivity=[
        {'coordinate_rule':'location_priority_baseline','matched_late':int(m.late.sum()),'outside_late':int(m.loc[m.nearest_n_m>500,'late'].sum())},
        {'coordinate_rule':'route_priority_alternative','matched_late':int(alternate_m.late.sum()),'outside_late':int(alternate_m.loc[ad>500,'late'].sum())},
        {'coordinate_rule':'exclude_nodes_with_disagreement_gt100m','matched_late':int(reduced.late.sum()),'outside_late':int(reduced.loc[rd>500,'late'].sum())}]
    for s in coord_sensitivity:s['outside_share']=s['outside_late']/s['matched_late']
    dump_csv(coord_sensitivity,out/'coordinate_source_sensitivity.csv')
    boundary=m.loc[m.nearest_n_m.between(450,550)]
    unmapped_n=road.loc[road['교통수단타입명'].eq('서울심야버스') & ~road['표준버스정류장ID'].isin(ns.NODE_ID)].copy()
    unmapped_n['night00_03']=unmapped_n[[bc[h] for h in range(4)]].sum(axis=1)
    unmapped_n['late']=unmapped_n[[bc[h] for h in [21,22,23]]].sum(axis=1)
    dump_csv(unmapped_n.groupby(['표준버스정류장ID','역명'],dropna=False)[['night00_03','late']].sum().reset_index(),out/'n_ids_outside_snapshot.csv')
    rh=road.groupby(['노선번호','교통수단타입명'])[bc].sum().reset_index()
    rh.columns=['route','mode']+[f'h{h:02}' for h in range(24)]
    dump_csv(rh,out/'route_hourly.csv')
    hubs=pd.read_csv(out/'scenario_three_hubs.csv',dtype={'NODE_ID':str,'ARS':str})
    audits=[]
    for h in hubs.itertuples():
        distance=distance_matrix([[h.lat,h.lon]],m[['lat','lon']])[0]
        new=(distance<=500)&(m.nearest_n_m>500)
        own=m.loc[m.NODE_ID.eq(h.NODE_ID)].iloc[0]
        record={'NODE_ID':h.NODE_ID,'ARS':h.ARS,'stop_name':h.stop_name,
            'snapshot_routes':' / '.join(sorted(routes.loc[routes.NODE_ID.eq(h.NODE_ID),'노선명'].unique())),
            'new_geometric_stops':int(new.sum()),'new_late':int(m.loc[new,'late'].sum())}
        for col in ['b23','night00_03','night01_03','night02_03','b00','b01','b02','b03']:
            record['own_'+col]=int(own[col]);record['new_area_'+col]=int(m.loc[new,col].sum())
        audits.append(record)
    dump_csv(audits,out/'hub_temporal_audit.csv')
    checks={'independent_haversine_max_error_m':max_error,'distance_threshold_masks_identical':True,
        'radius_boundary_450_550_stops':len(boundary),'radius_boundary_450_550_late':int(boundary.late.sum()),
        'common_coordinate_nodes':len(discrepancies),'coordinate_difference_over_25m_nodes':int((discrepancies.difference_m>25).sum()),
        'coordinate_difference_over_100m_nodes':int((discrepancies.difference_m>100).sum()),
        'max_coordinate_difference_m':float(discrepancies.difference_m.max()),
        'matched_non_seoul_id_prefix_stops':int((~m.NODE_ID.str.startswith('1')).sum()),
        'matched_non_seoul_id_prefix_late':int(m.loc[~m.NODE_ID.str.startswith('1'),'late'].sum()),
        'n_ids_not_in_snapshot':int(unmapped_n['표준버스정류장ID'].nunique()),
        'n_outside_snapshot_00_03':int(unmapped_n.night00_03.sum()),
        'observed_vs_unmet':'Zero boardings do not prove zero need or no service. Positive counts do not give departure times/headway.',
        'scope':'Seoul-operated bus data; spatial matched sample, not an administrative-boundary polygon census.'}
    (out/'extended_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':checks,'optimization':optimum,'robustness':trials},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data-dir',type=Path,default=ROOT/'data/raw')
    p.add_argument('--output-dir',type=Path,default=ROOT/'results');p.add_argument('--skip-milp',action='store_true')
    a=p.parse_args();main(a.data_dir,a.output_dir,not a.skip_milp)
