#!/usr/bin/env python3
"""Independent source totals and fixed-hub union checks, using Python stdlib only."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def rows(path,encoding='utf-8-sig'):
    with path.open(encoding=encoding,newline='') as stream:return list(csv.DictReader(stream))


def distance(a,b):
    lat1,lon1=map(math.radians,a);lat2,lon2=map(math.radians,b)
    q=math.sin((lat1-lat2)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin((lon1-lon2)/2)**2
    return 2*6371008.8*math.asin(min(1,math.sqrt(q)))


def main(out):
    expected=json.loads((ROOT/'assets/expected_input_sha256.json').read_text(encoding='utf-8'))
    for name,sha in expected.items():assert hashlib.sha256((ROOT/'data/raw'/name).read_bytes()).hexdigest()==sha,name
    raw=rows(next((ROOT/'data/raw').glob('*.csv')),'cp949')
    assert len(raw)==42155
    road=[r for r in raw if r['교통수단타입명']!='기타']
    observed=rows(out/'hourly.csv')
    for hour in range(24):
        column=f'{hour if hour else "00"}시승차총승객수'
        all_total=sum(int(r[column]) for r in road)
        n_total=sum(int(r[column]) for r in road if r['교통수단타입명']=='서울심야버스')
        assert all_total==int(observed[hour]['road_boardings'])
        assert n_total==int(observed[hour]['n_boardings'])
    s=rows(out/'stops.csv');m=json.loads((out/'metrics.json').read_text(encoding='utf-8'))
    matched=[r for r in s if r['coordinate_matched']=='True']
    assert len(matched)==m['matched_stops']
    weights=sum(int(r['late']) for r in matched)
    outside=[r for r in matched if float(r['nearest_n_m'])>500]
    assert weights==m['matched_late']
    assert sum(int(r['late']) for r in outside)==m['baseline_500m']['outside_boardings']
    hubs=rows(out/'scenario_three_hubs.csv');covered=set();increment=[]
    for h in hubs:
        new=[r for r in outside if distance((float(h['lat']),float(h['lon'])),(float(r['lat']),float(r['lon'])))<=500 and r['NODE_ID'] not in covered]
        gain=sum(int(r['late']) for r in new);assert gain==int(h['increment_boardings'])
        covered.update(r['NODE_ID'] for r in new);increment.append(gain)
    assert sum(increment)==225811 and len(covered)==48
    actual_ids={r['NODE_ID'] for r in rows(out/'scenario_newly_covered_stops.csv')}
    assert actual_ids==covered
    # Recompute the fixed-hub walking scenario directly from cached API bytes,
    # independently of audit_evidence.py's DataFrame operations.
    pairs=json.loads((ROOT/'data/evidence/walking_pairs.json').read_text(encoding='utf-8'))
    eligible=set();snap_review=set()
    for p in pairs:
        path=ROOT/'data/evidence/walking'/f"{p['pair_id']}.json"
        body=path.read_bytes();j=json.loads(body);meta=json.loads(path.with_suffix('.meta.json').read_text(encoding='utf-8'))
        assert hashlib.sha256(body).hexdigest()==meta['sha256']
        if 'fixed_hub_catchment' not in p['purposes']:continue
        own=p['from_id']==p['to_id'];offsets=[x['distance'] for x in j['waypoints']]
        acceptable=own or max(offsets)<=25
        walk=0 if own else j['routes'][0]['distance']+sum(offsets)
        if acceptable and walk<=500:eligible.add(p['to_id'])
        if not acceptable:snap_review.add(p['to_id'])
    w=json.loads((out/'walking_validation.json').read_text(encoding='utf-8'))
    assert len(eligible)==w['walking500_valid_stops']
    assert sum(int(r['late']) for r in outside if r['NODE_ID'] in eligible)==w['walking500_valid_late']
    report={'source_sha256_checked':len(expected),'source_rows_checked':len(raw),
        'all_hourly_boarding_totals_match':True,'n_hourly_totals_match':True,
        'fixed_hub_union_stops':len(covered),'fixed_hub_union_late':sum(increment),
        'walking_from_raw_json_match':True,'walking500_stops':len(eligible),
        'walking500_late':w['walking500_valid_late'],'snap_review_stops':len(snap_review),
        'all_checks_passed':True}
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output-dir',type=Path,default=ROOT/'results')
    main(p.parse_args().output_dir)
