#!/usr/bin/env python3
"""Optional, small, rate-limited public evidence acquisition. Offline runs do not use this.

python acquire_evidence.py --fetch
Cached 2026-10-22 responses are distributed for reproducibility. Refreshing them
changes the source date and may change results. No credentials are needed.
"""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json
import time
import urllib.parse
import urllib.request
import numpy as np
import pandas as pd
from analysis import ROOT, R, sphere, read_xlsx, dump_csv

UA = 'NightMobilityResearch/1.0 (Seoul transit contest; small cached walking audit)'
FOOT = 'https://routing.openstreetmap.de/routed-foot/route/v1/foot/'
TOPIS = 'https://topis.seoul.go.kr/map/busMap/selectBusList.do'


def great_circle(a, b):
    chord = np.linalg.norm(sphere(np.atleast_2d(a)) - sphere(np.atleast_2d(b)), axis=1)
    return 2 * R * np.arcsin(np.clip(chord / 2, 0, 1))


def prepare_pairs():
    hubs = pd.read_csv(ROOT / 'results/scenario_three_hubs.csv', dtype={'NODE_ID':str, 'ARS':str})
    stops = pd.read_csv(ROOT / 'results/stops.csv', dtype={'NODE_ID':str, 'ARS':str}).set_index('NODE_ID')
    ns = pd.read_csv(ROOT / 'results/n_stops.csv', dtype={'NODE_ID':str, 'ARS':str})
    new = pd.read_csv(ROOT / 'results/scenario_newly_covered_stops.csv', dtype={'NODE_ID':str, 'ARS':str})
    priority = pd.read_csv(ROOT / 'results/priority_top100.csv', dtype={'NODE_ID':str, 'ARS':str}).head(6)
    pairs = {}
    def add(a, b, purpose):
        key = str(a.NODE_ID) + '_' + str(b.NODE_ID)
        if key not in pairs:
            pairs[key] = {'pair_id':key, 'from_id':str(a.NODE_ID), 'from_name':a.stop_name,
                'from_ARS':str(a.ARS), 'from_lat':float(a.lat), 'from_lon':float(a.lon),
                'to_id':str(b.NODE_ID), 'to_name':b.stop_name, 'to_ARS':str(b.ARS),
                'to_lat':float(b.lat), 'to_lon':float(b.lon),
                'straight_m':float(great_circle([a.lat,a.lon],[b.lat,b.lon])[0]), 'purposes':[]}
        if purpose not in pairs[key]['purposes']: pairs[key]['purposes'].append(purpose)
    # Audit every newly included stop for these fixed hubs. Do not claim a
    # citywide walking-network recalculation or an optimized walking solution.
    for a in hubs.itertuples():
        for b in new.itertuples():
            if great_circle([a.lat,a.lon],[b.lat,b.lon])[0] <= 500 + 1e-6:
                add(a,b,'fixed_hub_catchment')
    # Three closest N stops by spherical distance per selected location. The
    # best route among these is an audited connection, NOT a proven global
    # shortest footpath to any N stop.
    audits = pd.concat([hubs, priority], ignore_index=True).drop_duplicates('NODE_ID')
    for a in audits.itertuples():
        ds = great_circle([a.lat,a.lon],ns[['lat','lon']].to_numpy())
        for j in np.argsort(ds, kind='stable')[:3]: add(a,ns.iloc[j],'n_connection_sample')
    return pairs


def fetch_evidence(cache):
    cache.mkdir(parents=True, exist_ok=True)
    walkdir = cache / 'walking'; walkdir.mkdir(exist_ok=True)
    route_dir = cache / 'topis'; route_dir.mkdir(exist_ok=True)
    pairs = prepare_pairs()
    (cache / 'walking_pairs.json').write_text(json.dumps(list(pairs.values()),ensure_ascii=False,indent=2),encoding='utf-8')
    previous = 0.0
    def get(url, path, data=None):
        nonlocal previous
        meta_path = path.with_suffix('.meta.json')
        if path.exists() and meta_path.exists(): return
        pause = 1.15 - (time.monotonic() - previous)
        if pause > 0: time.sleep(pause)
        req = urllib.request.Request(url,data=data,headers={'User-Agent':UA,
            'Referer':'https://routing.openstreetmap.de/' if 'openstreetmap.de' in url else 'https://topis.seoul.go.kr/map/openBusMap.do'})
        previous=time.monotonic()
        with urllib.request.urlopen(req,timeout=25) as response:
            body=response.read();status=response.status
        json.loads(body)  # Do not cache a login or HTML error page as JSON.
        path.write_bytes(body)
        meta={'url':url,'method':'POST' if data else 'GET','post_data':data.decode() if data else None,
              'retrieved_utc':dt.datetime.now(dt.timezone.utc).isoformat(), 'http_status':status,
              'sha256':hashlib.sha256(body).hexdigest(),'user_agent':UA}
        meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    for i,p in enumerate(pairs.values(),1):
        coordinates=f"{p['from_lon']:.10f},{p['from_lat']:.10f};{p['to_lon']:.10f},{p['to_lat']:.10f}"
        url=FOOT+coordinates+'?overview=full&geometries=geojson&steps=false'
        get(url,walkdir/(p['pair_id']+'.json'))
        if i%10==0: print(f'walking {i}/{len(pairs)}',flush=True)
    routes=read_xlsx(ROOT/'data/raw/서울시버스노선별정류소정보(20260902).xlsx')
    hubs=pd.read_csv(ROOT/'results/scenario_three_hubs.csv',dtype={'NODE_ID':str})
    names=sorted(set(routes.loc[routes.NODE_ID.isin(hubs.NODE_ID),'노선명']))
    # The literal N query returns night routes in one ordinary search request.
    for name in ['N']+names:
        payload=urllib.parse.urlencode({'routName':name,'pageIndex':'1','pageSize':'100','recordPerPage':'100'}).encode()
        get(TOPIS,route_dir/(name+'.json'),payload)
    print(f'Cached {len(pairs)} walking pairs; TOPIS searches {len(names)+1}',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fetch',action='store_true',help='explicitly contact public services; 1.15s request spacing')
    a=p.parse_args()
    if not a.fetch: p.error('Use --fetch only when refreshing evidence is intended; normal analysis is offline.')
    fetch_evidence(ROOT/'data/evidence')
