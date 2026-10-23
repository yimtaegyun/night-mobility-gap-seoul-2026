"""Publication figures from saved result tables only; no further data aggregation."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parent
NAVY, GREEN, ORANGE, GRAY = '#183247', '#258877', '#D6753F', '#AAB8C3'


def make_figures(results: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    for name in ['NanumGothic.ttf', 'NanumGothicBold.ttf']:
        font_manager.fontManager.addfont(str(ROOT / 'assets' / name))
    plt.rcParams.update({'font.family': 'NanumGothic', 'font.size': 10.5,
                         'axes.unicode_minus': False, 'axes.spines.top': False,
                         'axes.spines.right': False, 'axes.edgecolor': '#D6DFE5',
                         'axes.labelcolor': NAVY, 'text.color': NAVY, 'xtick.color': NAVY,
                         'ytick.color': NAVY, 'savefig.facecolor': 'white', 'figure.facecolor': 'white'})
    def save(fig, stem):
        fig.savefig(output / (stem + '.png'), dpi=240, bbox_inches='tight', pad_inches=.12)
        fig.savefig(output / (stem + '.pdf'), bbox_inches='tight', pad_inches=.12)
        plt.close(fig)

    hourly = pd.read_csv(results / 'hourly.csv').set_index('hour')
    metrics = json.loads((results / 'metrics.json').read_text(encoding='utf-8'))
    order = [18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4]
    a = hourly.loc[order]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.0), gridspec_kw={'width_ratios': [2.4, 1]})
    ax = axes[0]; x = np.arange(len(order))
    ax.axvspan(2.6, 5.4, color='#FFF0E5', zorder=0)
    ax.bar(x, a.non_n_boardings / 10000, color='#B6C7D1', label='비N 도로버스')
    ax.bar(x, a.n_boardings / 10000, bottom=a.non_n_boardings / 10000, color=GREEN, label='도시형 N노선')
    ax.set_xticks(x, [f'{h:02d}' for h in order]); ax.set_xlabel('시간대(시)')
    ax.set_ylabel('월간 승차(만 건)'); ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=9, loc='upper right')
    ax.set_title('18시부터 익일 04시까지 관측 승차', fontsize=11, loc='left', pad=12)
    ax = axes[1]; hs = [23, 0, 1, 2, 3, 4]; shares = hourly.loc[hs].n_share.to_numpy() * 100
    ax.bar(np.arange(6), shares, color=GREEN, width=.62)
    for i, v in enumerate(shares):ax.text(i, v + 2, f'{v:.1f}', ha='center', fontsize=8.5)
    ax.set_xticks(range(6), [f'{h:02d}' for h in hs]); ax.set_ylim(0, 113)
    ax.set_ylabel('N노선 승차 비중(%)'); ax.set_xlabel('시간대(시)')
    ax.set_title('도로버스 승차 중 N노선 비중', fontsize=10.5, loc='left', pad=12)
    ax.grid(axis='y', alpha=.2);ax.set_axisbelow(True)
    fig.tight_layout(w_pad=2)
    save(fig, '01_hourly_observed')

    sensitivity = pd.read_csv(results / 'distance_sensitivity.csv').head(4)
    fig, ax = plt.subplots(figsize=(9.5, 3.3))
    y = np.arange(4); height = .30
    ax.barh(y - height / 2, sensitivity.stop_share * 100, height, color='#B6C7D1', label='정류장 수 기준')
    ax.barh(y + height / 2, sensitivity.boarding_share * 100, height, color=GREEN, label='21~23시 비N 승차 가중')
    for i, r in sensitivity.iterrows():
        ax.text(r.stop_share * 100 + 1, i - height / 2, f'{r.stop_share * 100:.2f}%', va='center', fontsize=10)
        ax.text(r.boarding_share * 100 + 1, i + height / 2, f'{r.boarding_share * 100:.2f}%', va='center', fontsize=10, fontweight='bold')
    ax.set_yticks(y, ['같은 ID 직접정차', '300m 직선거리', '500m 직선거리', '800m 직선거리'])
    ax.invert_yaxis();ax.set_xlim(0, 105);ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel('포괄률(%)');ax.grid(axis='x', alpha=.2);ax.set_axisbelow(True)
    ax.legend(loc='upper center', bbox_to_anchor=(.5, 1.20), ncol=2, frameon=False, fontsize=10)
    fig.tight_layout(rect=[0, 0, 1, .94])
    save(fig, '02_distance_coverage_observed')

    priorities = pd.read_csv(results / 'priority_top100.csv', dtype={'ARS': str}).head(8)
    fig, ax = plt.subplots(figsize=(9.7, 3.6))
    y = np.arange(len(priorities)); ax.barh(y, priorities.b23, color=ORANGE, height=.62)
    ax.set_yticks(y, [f'{r.stop_name} [{r.ARS}]' for r in priorities.itertuples()])
    for i, r in enumerate(priorities.itertuples()):
        ax.text(r.b23 + 50, i, f'{r.b23:,}건 / {r.nearest_n_m:,.0f}m', va='center', fontsize=9.5)
    ax.invert_yaxis();ax.set_xlim(0, 6800);ax.set_xlabel('23시 월간 비N 승차(건) / 최근접 N정류장 직선거리(m)')
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _:f'{int(v):,}'))
    ax.grid(axis='x', alpha=.2);ax.set_axisbelow(True);fig.tight_layout()
    save(fig, '03_priority_observed')

    hubs = pd.read_csv(results / 'scenario_three_hubs.csv', dtype={'ARS': str})
    base = metrics['baseline_500m']['boarding_share'] * 100
    values = [base] + list(hubs.total_boarding_coverage * 100)
    fig, ax = plt.subplots(figsize=(9.6, 2.3))
    ys = np.arange(4)
    ax.barh(ys, values, color=[GRAY, GREEN, GREEN, GREEN], height=.54)
    ax.set_yticks(ys, ['기존 N정류장'] + [f'{i}개 거점 가정' for i in [1, 2, 3]])
    for i, val in enumerate(values):ax.text(val + .65, i, f'{val:.2f}%', va='center', fontsize=11, fontweight='bold')
    ax.invert_yaxis();ax.set_xlim(0, 100);ax.set_xlabel('21~23시 비N 승차기록의 기하학적 500m 포괄률(%)')
    ax.grid(axis='x', alpha=.2);ax.set_axisbelow(True);fig.tight_layout()
    save(fig, '04_three_hubs_simulated')

    stops = pd.read_csv(results / 'stops.csv')
    ns = pd.read_csv(results / 'n_stops.csv')
    newly = pd.read_csv(results / 'scenario_newly_covered_stops.csv')
    fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2))
    for i, row in enumerate(hubs.itertuples()):
        ax = axes[i]
        sx = (stops.lon - row.lon) * np.cos(np.deg2rad(row.lat)) * 111195
        sy = (stops.lat - row.lat) * 111195
        nx = (ns.lon - row.lon) * np.cos(np.deg2rad(row.lat)) * 111195
        ny = (ns.lat - row.lat) * 111195
        ux = (newly.lon - row.lon) * np.cos(np.deg2rad(row.lat)) * 111195
        uy = (newly.lat - row.lat) * 111195
        ax.scatter(sx, sy, c='#CBD3D9', s=11, label='비N 정류장')
        ax.scatter(nx, ny, c=GREEN, marker='s', s=20, label='기존 N정류장')
        ax.scatter(ux, uy, c=ORANGE, s=23, label='추가 포괄 정류장')
        ax.add_patch(Circle((0, 0), 500, fill=False, edgecolor=ORANGE, lw=1.3, linestyle='--'))
        ax.scatter([0], [0], marker='*', s=150, color=NAVY, zorder=5, label='가상 거점')
        ax.set_title(f'{i+1}. {row.stop_name}\nARS {row.ARS}', fontsize=10.5, pad=8)
        ax.set_xlim(-1600, 1600);ax.set_ylim(-1600, 1600);ax.set_aspect('equal')
        ax.set_xticks([-1000, 0, 1000]);ax.set_yticks([-1000, 0, 1000]);ax.tick_params(labelsize=8)
        ax.grid(alpha=.15);ax.set_xlabel('거점 기준 동서 거리(m)', fontsize=8.5)
        if i == 0:ax.set_ylabel('거점 기준 남북 거리(m)', fontsize=8.5)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc='lower center', ncol=4, frameon=False, fontsize=9, bbox_to_anchor=(.5, -.025))
    fig.subplots_adjust(bottom=.24, wspace=.23, left=.065, right=.99, top=.8)
    save(fig, '05_hub_locations_simulated')

    valid = stops.loc[stops.coordinate_matched]
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(valid.lon, valid.lat, s=4, c='#D0D8DE', label='비N 정류장', rasterized=True)
    far = valid.loc[valid.nearest_n_m > 500]
    ax.scatter(far.lon, far.lat, s=5 + np.minimum(far.late / 1500, 20), c=ORANGE, alpha=.55, label='N정류장 500m 밖')
    ax.scatter(ns.lon, ns.lat, s=5, c=GREEN, label='도시형 N정류장')
    for i, row in enumerate(hubs.itertuples()):
        ax.scatter(row.lon, row.lat, marker='*', s=160, color=NAVY, zorder=5)
        ax.annotate(f'{i+1}. {row.stop_name}', (row.lon, row.lat), xytext=(8, (i-1)*18), textcoords='offset points', fontsize=10,
                    bbox={'facecolor':'white','edgecolor':'none','alpha':.85})
    ax.set_xlabel('경도');ax.set_ylabel('위도');ax.set_aspect(1 / np.cos(np.deg2rad(37.55)))
    ax.legend(frameon=False, fontsize=9, loc='upper left');ax.grid(alpha=.15)
    ax.set_title('정류장 좌표 분포와 가상 3거점\n공간 분석 / 경위도 점도 / 행정경계·도로·보행경로 미표시', fontsize=12)
    fig.tight_layout();save(fig, '06_station_distribution')


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser();p.add_argument('--results', type=Path, default=ROOT / 'results');p.add_argument('--output', type=Path, default=ROOT / 'figures')
    a = p.parse_args();make_figures(a.results, a.output)
