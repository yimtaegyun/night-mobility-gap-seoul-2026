#!/usr/bin/env python3
"""Audit frozen public route/footpath responses without contacting the network."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from analysis import ROOT, CSV_NAME, read_xlsx, dump_csv


def main(out, evidence):
    pairs=json.loads((evidence/'walking_pairs.json').read_text(encoding='utf-8'))
    records=[]
    for p in pairs:
        path=evidence/'walking'/f"{p['pair_id']}.json"
        body=path.read_bytes();j=json.loads(body)
        meta=json.loads(path.with_suffix('.meta.json').read_text(encoding='utf-8'))
        assert hashlib.sha256(body).hexdigest()==meta['sha256']
        assert j['code']=='Ok' and len(j['waypoints'])==2
        r=j['routes'][0];a,b=[float(w['distance']) for w in j['waypoints']]
        own=p['from_id']==p['to_id']
        adjusted=0.0 if own else float(r['distance'])+a+b
        rec={k:v for k,v in p.items() if k!='purposes'}
        rec.update({'purposes':'|'.join(p['purposes']),'route_m':float(r['distance']),
            'start_snap_m':a,'end_snap_m':b,'route_plus_connectors_m':adjusted,
            'snap_within25m':bool(own or max(a,b)<=25),
            'within500_route_only':bool(own or float(r['distance'])<=500),
            'within500_connectors':bool(adjusted<=500), 'own_stop':own,
            'retrieved_utc':meta['retrieved_utc'],'osm_data_version':j.get('data_version','not returned'),
            'sha256':meta['sha256']})
        records.append(rec)
    allpairs=pd.DataFrame(records)
    dump_csv(allpairs,out/'walking_pairs_audit.csv')
    catch=allpairs.loc[allpairs.purposes.str.contains('fixed_hub_catchment')].copy()
    new=pd.read_csv(out/'scenario_newly_covered_stops.csv',dtype={'NODE_ID':str})
    catch=catch.merge(new[['NODE_ID','late','b23']],left_on='to_id',right_on='NODE_ID',validate='m:1')
    assert set(catch.to_id)==set(new.NODE_ID)
    catch['eligible_walk500']=catch.snap_within25m & catch.within500_connectors
    dump_csv(catch,out/'fixed_hub_walking_audit.csv')
    hub_rows=[]
    hubs=pd.read_csv(out/'scenario_three_hubs.csv',dtype={'NODE_ID':str,'ARS':str})
    for h in hubs.itertuples():
        c=catch.loc[catch.from_id.eq(h.NODE_ID)]
        hub_rows.append({'NODE_ID':h.NODE_ID,'ARS':h.ARS,'stop_name':h.stop_name,
            'geometric_stops':int(c.to_id.nunique()),'geometric_late':int(c.drop_duplicates('to_id').late.sum()),
            'walk500_stops':int(c.loc[c.eligible_walk500,'to_id'].nunique()),
            'walk500_late':int(c.loc[c.eligible_walk500].drop_duplicates('to_id').late.sum()),
            'snap_over25m_pairs':int((~c.snap_within25m).sum())})
    dump_csv(hub_rows,out/'hub_walking_summary.csv')
    sensitivity=[]
    for radius in [300,450,500,550,800]:
        for definition in ['route_m','route_plus_connectors_m']:
            keep=catch.snap_within25m & ((catch[definition]<=radius)|catch.own_stop)
            included_r=catch.loc[keep].drop_duplicates('to_id')
            sensitivity.append({'radius_m':radius,'distance_definition':definition,
                'included_stops':len(included_r),'included_late':int(included_r.late.sum()),
                'scope':'Only the original 48 newly geometric stops, hub-to-stop direction; not full catchments at alternative radii.'})
    dump_csv(sensitivity,out/'walking_threshold_sensitivity.csv')
    included=catch.loc[catch.eligible_walk500].drop_duplicates('to_id')
    review=catch.loc[~catch.snap_within25m].drop_duplicates('to_id')
    summary={'pairs_all':len(allpairs),'fixed_hub_pairs':len(catch),'fixed_hub_unique_stops':int(catch.to_id.nunique()),
        'geometric_late':int(new.late.sum()),'walking500_valid_stops':len(included),
        'walking500_valid_late':int(included.late.sum()),
        'walking500_retention_fraction':int(included.late.sum())/int(new.late.sum()),
        'snap_review_stops':len(review),'snap_review_late':int(review.late.sum()),
        'direction':'From each hub to stop. Reverse direction, field safety, nighttime access and wheelchair access are unverified.',
        'metric':'OSRM routed-foot returned route distance plus straight endpoint snap connectors. Own stop = 0m; snap<=25m per endpoint.',
        'ceiling':'Fixed-hub subset only. Baseline remains spherical; this is NOT a citywide walking coverage rate. No passenger forecast.',
        'osm_data_version':'Not returned by server; retrieval date is preserved, underlying graph date unverified.'}
    (out/'walking_validation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')

    # Save only exact supplied route IDs. Route-origin departure times are not
    # times at the hub or transfer stop; September counts are a separate source.
    routes=read_xlsx(ROOT/'data/raw/서울시버스노선별정류소정보(20260902).xlsx')
    relevant=set(routes.loc[routes.NODE_ID.isin(hubs.NODE_ID),'ROUTE_ID'])
    n_names=set(json.loads((out/'metrics.json').read_text(encoding='utf-8'))['n_routes'])
    relevant|=set(routes.loc[routes['노선명'].isin(n_names),'ROUTE_ID'])
    facts={}
    for p in sorted((evidence/'topis').glob('*.json')):
        if '.meta.' in p.name: continue
        body=p.read_bytes();meta=json.loads(p.with_suffix('.meta.json').read_text(encoding='utf-8'))
        assert hashlib.sha256(body).hexdigest()==meta['sha256']
        for row in json.loads(body).get('rows',[]):
            if str(row['routId']) not in relevant: continue
            record={k:row.get(k) for k in ['routId','routName','stnFirst','stnLast','turnPlaceStationId','timeFirst','timeLast','norTerms',
                'satTimeFirst','satTimeLast','satTerms','holTimeFirst','holTimeLast','holTerms','routeDistance','busRunStatusCd']}
            record.update({'retrieved_utc':meta['retrieved_utc'],'source_file':p.name,
                'time_interpretation':'Route-origin planned departures, not stop passage times; general route headway, not a guarantee.'})
            facts[record['routId']]=record
    dump_csv(list(facts.values()),out/'schedule_facts.csv')
    raw=pd.read_csv(ROOT/'data/raw'/CSV_NAME,encoding='cp949',low_memory=False,
        dtype={'노선번호':str,'표준버스정류장ID':str})
    hubroute=[]
    for h in hubs.itertuples():
        for row in routes.loc[routes.NODE_ID.eq(h.NODE_ID)].drop_duplicates('ROUTE_ID').to_dict('records'):
            record={'hub_id':h.NODE_ID,'hub_name':h.stop_name,'route_id':row['ROUTE_ID'],'route_name':row['노선명']}
            f=facts.get(row['ROUTE_ID'],{})
            for k in ['stnFirst','stnLast','timeFirst','timeLast','norTerms','retrieved_utc']:record[k]=f.get(k,'not retrieved')
            record['official_schedule_found']=bool(f)
            subset=raw.loc[raw['표준버스정류장ID'].eq(h.NODE_ID)&raw['노선번호'].eq(row['노선명'])]
            for hour in [23,0,1,2,3]:record[f'observed_h{hour:02}']=int(subset[f'{hour if hour else "00"}시승차총승객수'].sum())
            hubroute.append(record)
    dump_csv(hubroute,out/'hub_existing_route_audit.csv')
    nconnect=allpairs.loc[allpairs.purposes.str.contains('n_connection_sample')].copy()
    # Choose the lowest returned route+connector among the three sampled N stops
    # with acceptable snapping. No assertion of a globally closest pedestrian N stop.
    best=nconnect.loc[nconnect.snap_within25m].sort_values(['from_id','route_plus_connectors_m','to_id']).drop_duplicates('from_id')
    direction=[]
    for c in best.to_dict('records'):
        serving=routes.loc[routes.NODE_ID.eq(c['to_id']) & routes['노선명'].isin(n_names)]
        for sr in serving.to_dict('records'):
            rr=routes.loc[routes.ROUTE_ID.eq(sr['ROUTE_ID'])].copy()
            rr['seq_num']=pd.to_numeric(rr['순번']);rr=rr.sort_values('seq_num').reset_index(drop=True)
            positions=np.flatnonzero(rr.NODE_ID.eq(c['to_id']).to_numpy())
            pos=int(positions[0]);nxt=rr.iloc[pos+1]['정류소명'] if pos+1<len(rr) else 'end of route'
            fact=facts.get(sr['ROUTE_ID'],{})
            turn=np.flatnonzero(rr.NODE_ID.eq(str(fact.get('turnPlaceStationId',''))).to_numpy())
            direction_to=(fact.get('stnLast') if pos<int(turn[0]) else fact.get('stnFirst')) if len(turn) else 'not established'
            direction.append({'from_id':c['from_id'],'from_name':c['from_name'],'n_stop_id':c['to_id'],
                'n_stop_name':c['to_name'],'n_stop_ARS':c['to_ARS'],'route_m':c['route_plus_connectors_m'],
                'n_route':sr['노선명'],'next_stop_snapshot':nxt,
                'direction_terminal':direction_to,
                'origin_first':fact.get('timeFirst','not retrieved'),'origin_last':fact.get('timeLast','not retrieved'),
                'weekday_headway_min':fact.get('norTerms','not retrieved'),'route_destination':fact.get('stnLast','not retrieved')})
    dump_csv(best,out/'n_connection_sample_best.csv');dump_csv(direction,out/'n_connection_directions.csv')
    # Budget quantities are chosen planning assumptions, not quotes, forecasts,
    # current Seoul unit prices or a cost-benefit analysis.
    budget=[]
    for unit in [300000,500000,800000]:
        for riders in [50,100,200]:
            budget.append({'assumed_won_per_vehicle_night':unit,'assumed_vehicles':2,'assumed_nights':12,
                'assumed_boardings_per_night':riders,'scenario_total_cost_won':unit*2*12,
                'gross_cost_per_boarding_won':unit*2/riders,'is_observed':False,
                'exclusions':'No fare revenue, survey cost, stop works, standby vehicles or cost escalation. Contract estimate required.'})
    dump_csv(budget,out/'budget_sensitivity.csv')
    print(json.dumps({'walking':summary,'official_route_facts':len(facts),'hub_route_rows':len(hubroute),
        'missing_hub_route_facts':[r['route_name'] for r in hubroute if not r['official_schedule_found']]},ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=ROOT/'results')
    p.add_argument('--evidence-dir',type=Path,default=ROOT/'data/evidence');a=p.parse_args();main(a.output_dir,a.evidence_dir)
