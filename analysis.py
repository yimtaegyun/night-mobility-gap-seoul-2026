#!/usr/bin/env python3
"""밤의 이동 공백. 공개 CSV/XLSX에서 결과와 시각화를 재현한다.

python analysis.py
python analysis.py --data-dir data/raw --output-dir results --figures-dir figures
월별 승차 건수와 구면 직선거리만 분석한다. 개인별 이동, 보행거리, 미충족 수요,
신규 승객, 탄소감축 또는 실제 노선 운영 효과는 추정하지 않는다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pandas as pd
import scipy
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parent
R = 6371008.8
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
CSV_NAME = '2026년_버스노선별_정류장별_시간대별_승하차_인원_정보(09월).csv'
SNAPSHOTS = ['20260506', '20260602', '20260701', '20260804', '20260902']


def read_xlsx(path: Path) -> pd.DataFrame:
    """Read the supplied first OOXML worksheet without an Excel application."""
    with zipfile.ZipFile(path) as z:
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            shared = [''.join(t.text or '' for t in si.iter(NS + 't'))
                      for si in ET.fromstring(z.read('xl/sharedStrings.xml'))]
        rows = []
        for row in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).find(NS + 'sheetData'):
            values = {}
            for c in row:
                match = re.match(r'([A-Z]+)', c.attrib.get('r', ''))
                if not match:
                    continue
                col = 0
                for letter in match.group(1):
                    col = col * 26 + ord(letter) - 64
                v = c.find(NS + 'v')
                value = v.text if v is not None else ''
                if c.attrib.get('t') == 's' and value:
                    value = shared[int(value)]
                elif c.attrib.get('t') == 'inlineStr':
                    value = ''.join(t.text or '' for t in c.iter(NS + 't'))
                values[col - 1] = value
            rows.append([values.get(i, '') for i in range(max(values, default=-1) + 1)])
    return pd.DataFrame(rows[1:], columns=rows[0]).fillna('')


def sphere(latlon: np.ndarray) -> np.ndarray:
    lat, lon = np.deg2rad(np.asarray(latlon, dtype=float)).T
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


def nearest_meters(points: np.ndarray, targets: np.ndarray):
    """Unit-sphere KDTree gives the exact nearest great-circle target."""
    chord, idx = cKDTree(sphere(targets)).query(sphere(points), k=1)
    return 2 * R * np.arcsin(np.clip(chord / 2, 0, 1)), idx


def valid_coord(row):
    try:
        lon, lat = float(row['X좌표']), float(row['Y좌표'])
        if 126.5 < lon < 127.4 and 37.1 < lat < 38:
            return lat, lon
    except (ValueError, TypeError, KeyError):
        pass
    return None


def dump_csv(frame, path):
    pd.DataFrame(frame).to_csv(path, index=False, encoding='utf-8-sig', float_format='%.10f')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'data/raw')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'results')
    parser.add_argument('--figures-dir', type=Path, default=ROOT / 'figures')
    parser.add_argument('--no-figures', action='store_true')
    args = parser.parse_args()
    data, out = args.data_dir.resolve(), args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(data / CSV_NAME, encoding='cp949', low_memory=False,
                      dtype={'노선번호': str, '표준버스정류장ID': str, '버스정류장ARS번호': str})
    bcols = [('00' if h == 0 else str(h)) + '시승차총승객수' for h in range(24)]
    acols = [('00' if h == 0 else str(h)) + '시하차총승객수' for h in range(24)]
    assert set(raw['사용년월'].unique()) == {202609}, '2026-09 입력만 사용'
    assert raw.shape == (42155, 57), f'Unexpected source shape {raw.shape}'
    counts = raw[bcols + acols]
    assert not counts.isna().any().any(), '승하차 결측치'
    assert (counts >= 0).all().all(), '음수 승하차량'
    duplicates = int(raw.duplicated().sum())
    assert duplicates == 0, '원본 전체행 중복을 확인해야 함'
    other = raw['교통수단타입명'].eq('기타')
    assert other.sum() == 8
    assert raw.loc[other, '노선번호'].str.startswith('한강버스').all()
    road = raw.loc[~other].copy()
    road['is_n'] = road['교통수단타입명'].eq('서울심야버스')
    assert (road['is_n'] == road['노선번호'].str.fullmatch(r'N\d+').fillna(False)).all()
    n_routes = sorted(road.loc[road.is_n, '노선번호'].unique())
    assert len(n_routes) == 14
    hourly = pd.DataFrame({'hour': range(24), 'road_boardings': road[bcols].sum().to_numpy(),
                           'n_boardings': road.loc[road.is_n, bcols].sum().to_numpy(),
                           'road_alightings': road[acols].sum().to_numpy()})
    hourly['non_n_boardings'] = hourly.road_boardings - hourly.n_boardings
    hourly['n_share'] = hourly.n_boardings / hourly.road_boardings
    dump_csv(hourly, out / 'hourly.csv')

    for key, hs in [('evening', [18, 19, 20]), ('late', [21, 22, 23]), ('b23', [23]), ('b00_04', [0, 1, 2, 3, 4])]:
        road[key] = road[[bcols[h] for h in hs]].sum(axis=1)
    valid_ids = road['표준버스정류장ID'].str.fullmatch(r'\d{9}').fillna(False)
    non = road.loc[~road.is_n & valid_ids].copy()
    non['stop_name'] = non['역명'].astype(str).str.replace(r'\(\d{5}\)$', '', regex=True)
    mode = lambda s: s.value_counts(sort=True).index[0]
    stops = non.groupby('표준버스정류장ID', sort=False).agg(
        ARS=('버스정류장ARS번호', mode), stop_name=('stop_name', mode),
        evening=('evening', 'sum'), late=('late', 'sum'), b23=('b23', 'sum'),
        b00_04=('b00_04', 'sum'), route_count=('노선번호', 'nunique')).reset_index()
    stops = stops.rename(columns={'표준버스정류장ID': 'NODE_ID'})
    locations_frame = read_xlsx(data / '서울시버스정류소위치정보(20260902).xlsx')
    routes = read_xlsx(data / '서울시버스노선별정류소정보(20260902).xlsx')
    locations = {}
    for row in locations_frame.to_dict('records'):
        c = valid_coord(row)
        if c and row['NODE_ID'] not in locations:
            locations[row['NODE_ID']] = (c[0], c[1], row['ARS_ID'], row['정류소명'], 'location_snapshot')
    initial_locations = len(locations)
    all_n_routes = sorted(set(routes.loc[routes['노선명'].str.fullmatch(r'N\d+'), '노선명']))
    # Match the supplied analysis: supplement missing N-type locations from route file coordinates.
    for row in routes.loc[routes['노선명'].isin(all_n_routes)].to_dict('records'):
        c = valid_coord(row)
        if c and row['NODE_ID'] not in locations:
            locations[row['NODE_ID']] = (c[0], c[1], row['ARS_ID'], row['정류소명'], 'route_snapshot_supplement')
    city = routes.loc[routes['노선명'].isin(n_routes)]
    n_ids = sorted(set(city.NODE_ID) & locations.keys())
    assert len(n_ids) == 1490
    n_points = np.array([locations[i][:2] for i in n_ids])
    n_stops = pd.DataFrame([{'NODE_ID': i, 'lat': locations[i][0], 'lon': locations[i][1],
                              'ARS': locations[i][2], 'stop_name': locations[i][3]} for i in n_ids])
    dump_csv(n_stops, out / 'n_stops.csv')
    for key, ix in [('lat', 0), ('lon', 1), ('location_ARS', 2), ('location_name', 3), ('coordinate_source', 4)]:
        stops[key] = stops.NODE_ID.map(lambda i: locations.get(i, (np.nan, np.nan, '', '', 'missing'))[ix])
    stops['coordinate_matched'] = stops.lat.notna()
    stops['same_id_n'] = stops.NODE_ID.isin(n_ids)
    matched = stops.loc[stops.coordinate_matched].copy().reset_index(drop=True)
    points = matched[['lat', 'lon']].to_numpy()
    distances, nearest = nearest_meters(points, n_points)
    matched['nearest_n_m'] = distances
    matched['nearest_n_id'] = np.array(n_ids)[nearest]
    weights = matched.late.to_numpy(dtype=np.int64)
    total = int(weights.sum())
    sensitivity = []
    for radius in [0, 300, 500, 800, 1000]:
        cover = matched.same_id_n.to_numpy() if radius == 0 else distances <= radius
        sensitivity.append({'radius_m': radius, 'covered_stops': int(cover.sum()), 'stop_share': float(cover.mean()),
                            'covered_boardings': int(weights[cover].sum()),
                            'boarding_share': float(weights[cover].sum() / total),
                            'outside_boardings': int(weights[~cover].sum()),
                            'outside_b23': int(matched.loc[~cover, 'b23'].sum())})
    dump_csv(sensitivity, out / 'distance_sensitivity.csv')
    stops = stops.merge(matched[['NODE_ID', 'nearest_n_m', 'nearest_n_id']], on='NODE_ID', how='left', validate='1:1')
    dump_csv(stops, out / 'stops.csv')
    priorities = matched.loc[(distances > 500) & (matched.evening >= 1000) & (matched.late >= 1000)]
    priorities = priorities.sort_values(['b23', 'late', 'NODE_ID'], ascending=[False, False, True])
    dump_csv(priorities.head(100), out / 'priority_top100.csv')

    outside = distances > 500
    pool = matched.loc[outside & (matched.late >= 2000)].sort_values('NODE_ID')
    outside_idx = np.flatnonzero(outside)
    point_sphere = sphere(points)
    outside_tree = cKDTree(point_sphere[outside])
    chord_radius = 2 * np.sin(500 / (2 * R))
    neighborhoods = {}
    for i, row in pool.iterrows():
        local = outside_tree.query_ball_point(point_sphere[i], chord_radius)
        neighborhoods[i] = outside_idx[np.asarray(local, dtype=int)]
    newly_covered = np.zeros(len(matched), dtype=bool)
    selected = []
    scenario = []
    for step in range(1, 4):
        scored = [(int(weights[idx[~newly_covered[idx]]].sum()), i) for i, idx in neighborhoods.items() if i not in selected]
        gain, winner = max(scored, key=lambda x: x[0])
        if gain <= 0:
            break
        indices = neighborhoods[winner]
        new_stops = int((~newly_covered[indices]).sum())
        newly_covered[indices] = True
        selected.append(winner)
        row = matched.loc[winner]
        cumulative = int(weights[newly_covered].sum())
        scenario.append({'step': step, 'NODE_ID': row.NODE_ID, 'ARS': row.ARS, 'stop_name': row.stop_name,
                         'lat': float(row.lat), 'lon': float(row.lon), 'nearest_n_m': float(row.nearest_n_m),
                         'own_late_boardings': int(row.late), 'increment_boardings': gain,
                         'increment_stops': new_stops, 'cumulative_boardings': cumulative,
                         'total_boarding_coverage': (int(weights[~outside].sum()) + cumulative) / total})
    dump_csv(scenario, out / 'scenario_three_hubs.csv')
    matched['scenario_new_500m'] = newly_covered
    dump_csv(matched.loc[newly_covered], out / 'scenario_newly_covered_stops.csv')
    union = np.zeros(len(matched), bool)
    for winner in selected:
        union[neighborhoods[winner]] = True
    assert not np.any(union & ~outside)
    assert int(weights[union].sum()) == sum(s['increment_boardings'] for s in scenario)
    assert int(union.sum()) == sum(s['increment_stops'] for s in scenario)

    snapshots = []
    previous = None
    for date in SNAPSHOTS:
        r = routes if date == '20260902' else read_xlsx(data / f'서울시버스노선별정류소정보({date}).xlsx')
        r = r.loc[r['노선명'].isin(n_routes)]
        ids = set(r.NODE_ID)
        snapshots.append({'date': date, 'n_routes': int(r['노선명'].nunique()), 'n_stops': len(ids),
                          'added_stops': None if previous is None else len(ids - previous),
                          'removed_stops': None if previous is None else len(previous - ids)})
        previous = ids
    dump_csv(snapshots, out / 'snapshots.csv')
    missing_weight = int(stops.loc[~stops.coordinate_matched, 'late'].sum())
    baseline = next(s for s in sensitivity if s['radius_m'] == 500)
    metrics = {
        'period': '2026-09', 'snapshot_date': '2026-09-02', 'raw_rows': len(raw), 'raw_columns': len(raw.columns),
        'exact_duplicate_rows': duplicates, 'excluded_other_rows': int(other.sum()), 'road_rows': len(road),
        'road_boardings': int(hourly.road_boardings.sum()),
        'evening_18_20': int(road.evening.sum()), 'late_21_23': int(road.late.sum()),
        'late_to_evening_ratio': float(road.late.sum() / road.evening.sum()),
        'invalid_stop_id_rows': int((~valid_ids).sum()), 'non_n_valid_stops': len(stops),
        'non_n_valid_late': int(stops.late.sum()), 'matched_stops': len(matched),
        'matched_late': total, 'matched_stop_share': len(matched) / len(stops),
        'matched_boarding_share': total / int(stops.late.sum()), 'unmatched_stops': int((~stops.coordinate_matched).sum()),
        'unmatched_late': missing_weight, 'location_rows': len(locations_frame), 'route_rows': len(routes),
        'location_snapshot_usable': initial_locations, 'supplemented_location_nodes': len(locations) - initial_locations,
        'matched_supplemented_stops': int(matched.coordinate_source.eq('route_snapshot_supplement').sum()),
        'n_routes': n_routes, 'excluded_airport_n': sorted(set(all_n_routes) - set(n_routes)), 'n_stops': len(n_ids),
        'baseline_500m': baseline, 'hub_candidate_count': len(pool), 'priority_candidate_count': len(priorities),
        'scenario_added_boardings': int(weights[newly_covered].sum()), 'scenario_added_stops': int(newly_covered.sum()),
        'scenario_final_coverage': scenario[-1]['total_boarding_coverage'],
        'scenario_gain_percentage_points': scenario[-1]['total_boarding_coverage'] * 100 - baseline['boarding_share'] * 100,
        'outside_share_bounds_among_valid_ids': [baseline['outside_boardings'] / int(stops.late.sum()),
                                               (baseline['outside_boardings'] + missing_weight) / int(stops.late.sum())],
        'method': '3D unit-sphere KDTree; spherical great-circle distance; R=6371008.8 m; greedy maximum additional weighted coverage',
        'interpretation': 'Observed monthly card-boardings; geometric catchment scenario only. Not a latent-demand or ridership forecast.'
    }
    (out / 'metrics.json').write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    environment = {'python': sys.version.split()[0], 'platform': platform.platform(), 'numpy': np.__version__,
                   'pandas': pd.__version__, 'scipy': scipy.__version__}
    (out / 'environment.json').write_text(json.dumps(environment, indent=2), encoding='utf-8')
    input_names = [CSV_NAME, '서울시버스정류소위치정보(20260902).xlsx'] + [
        f'서울시버스노선별정류소정보({date}).xlsx' for date in SNAPSHOTS]
    manifest = {name: hashlib.sha256((data / name).read_bytes()).hexdigest() for name in sorted(input_names)}
    (out / 'input_sha256.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    if not args.no_figures:
        from plot_figures import make_figures
        make_figures(out, args.figures_dir.resolve())
    print(json.dumps({'matched_stops': len(matched), 'matched_boardings': total,
                      'outside_500m_boardings': baseline['outside_boardings'],
                      'scenario_added_boardings': metrics['scenario_added_boardings'],
                      'scenario_final_coverage': metrics['scenario_final_coverage']}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
