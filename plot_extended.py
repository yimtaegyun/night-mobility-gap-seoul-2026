"""Publication figures for the extended audit, generated from frozen tables/cache."""
from pathlib import Path
import argparse
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle
from matplotlib.ticker import FuncFormatter
from analysis import ROOT

NAVY,GREEN,ORANGE,GRAY='#183247','#258877','#D6753F','#B6C7D1'


def make_figures(results,output):
    output.mkdir(parents=True,exist_ok=True)
    for name in ['NanumGothic.ttf','NanumGothicBold.ttf']:font_manager.fontManager.addfont(str(ROOT/'assets'/name))
    plt.rcParams.update({'font.family':'NanumGothic','font.size':10.5,'axes.unicode_minus':False,
        'axes.spines.top':False,'axes.spines.right':False,'text.color':NAVY,'axes.labelcolor':NAVY,
        'xtick.color':NAVY,'ytick.color':NAVY,'axes.edgecolor':'#D6DFE5','savefig.facecolor':'white'})
    def save(fig,stem):
        fig.savefig(output/(stem+'.png'),dpi=240,bbox_inches='tight',pad_inches=.13)
        fig.savefig(output/(stem+'.pdf'),bbox_inches='tight',pad_inches=.13);plt.close(fig)
    comp=pd.read_csv(results/'method_comparison.csv').iloc[:3]
    fig,ax=plt.subplots(figsize=(9.6,2.5));ys=np.arange(3)
    ax.barh(ys,comp.additional_late/10000,color=[GREEN,GRAY,GRAY],height=.55)
    ax.set_yticks(ys,['주변 승차 포괄량 최대화','정류장 자체 21~23시 상위 3곳','정류장 자체 23시 상위 3곳'])
    for i,r in enumerate(comp.itertuples()):ax.text(r.additional_late/10000+.3,i,f'{r.additional_late:,}건',va='center',fontsize=10)
    ax.invert_yaxis();ax.set_xlim(0,28);ax.set_xlabel('기존 21~23시 월간 승차의 추가 기하학적 포괄량(만 건)')
    ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True);fig.tight_layout();save(fig,'07_method_comparison_simulated')

    hubs=pd.read_csv(results/'scenario_three_hubs.csv',dtype={'NODE_ID':str,'ARS':str})
    walks=pd.read_csv(results/'hub_walking_summary.csv',dtype={'NODE_ID':str})
    best=pd.read_csv(results/'n_connection_sample_best.csv',dtype={'from_id':str,'to_id':str,'to_ARS':str})
    ns=pd.read_csv(results/'n_stops.csv');stops=pd.read_csv(results/'stops.csv')
    fig,axes=plt.subplots(1,3,figsize=(10.6,3.7))
    for i,h in enumerate(hubs.itertuples()):
        ax=axes[i];b=best.loc[best.from_id.eq(h.NODE_ID)].iloc[0]
        def xy(lon,lat):return ((np.asarray(lon)-h.lon)*np.cos(np.deg2rad(h.lat))*111195,(np.asarray(lat)-h.lat)*111195)
        sx,sy=xy(stops.lon,stops.lat);nx,ny=xy(ns.lon,ns.lat)
        ax.scatter(sx,sy,c='#CCD6DC',s=10,zorder=1)
        ax.scatter(nx,ny,c=GREEN,marker='s',s=16,zorder=2)
        path=ROOT/'data/evidence/walking'/f'{h.NODE_ID}_{b.to_id}.json'
        coords=np.array(json.loads(path.read_text())['routes'][0]['geometry']['coordinates']);rx,ry=xy(coords[:,0],coords[:,1])
        ax.plot(rx,ry,color=ORANGE,lw=2.1,zorder=3)
        ex,ey=xy(b.to_lon,b.to_lat);ax.scatter([ex],[ey],color=GREEN,marker='s',s=45,zorder=4)
        ax.scatter([0],[0],marker='*',s=130,c=NAVY,zorder=5)
        ax.add_patch(Circle((0,0),500,fill=False,ls='--',color='#94A6AF',lw=1))
        ax.set_title(f'{h.stop_name} [{h.ARS}]\n→ {b.to_name} [{b.to_ARS}]\n모형 보행 경로 {b.route_plus_connectors_m:,.0f}m',fontsize=9.5,pad=10)
        ax.set_xlim(-1850,1850);ax.set_ylim(-1850,1850);ax.set_aspect('equal')
        ax.set_xticks([-1000,0,1000]);ax.set_yticks([-1000,0,1000]);ax.tick_params(labelsize=8)
        ax.grid(alpha=.15);ax.set_xlabel('동서 상대거리(m)',fontsize=8.5)
        if i==0:ax.set_ylabel('남북 상대거리(m)',fontsize=8.5)
    fig.text(.5,.08,'★ 가상 거점    ■ 기존 N정류장    주황선: 조회된 보행 경로    점선: 500m 직선거리',ha='center',fontsize=8.5)
    fig.text(.5,.015,'© OpenStreetMap contributors (ODbL) · routing: FOSSGIS/OSRM foot · https://www.openstreetmap.org/copyright',ha='center',fontsize=7.2)
    fig.subplots_adjust(left=.055,right=.99,bottom=.22,top=.77,wspace=.25);save(fig,'08_hub_n_walking_routes')

    fig,ax=plt.subplots(figsize=(9.6,2.7));ys=np.arange(3);height=.3
    ax.barh(ys-height/2,walks.geometric_late/10000,height,color=GRAY,label='500m 직선거리권')
    ax.barh(ys+height/2,walks.walk500_late/10000,height,color=GREEN,label='500m 보행망 경로 모형권')
    for i,r in enumerate(walks.itertuples()):
        ax.text(r.geometric_late/10000+.15,i-height/2,f'{r.geometric_late:,}건 · {r.geometric_stops}곳',va='center',fontsize=9)
        ax.text(r.walk500_late/10000+.15,i+height/2,f'{r.walk500_late:,}건 · {r.walk500_stops}곳',va='center',fontsize=9)
    ax.set_yticks(ys,walks.stop_name);ax.invert_yaxis();ax.set_xlim(0,12.7)
    ax.set_xlabel('고정된 3거점 주변의 기존 21~23시 월간 승차기록(만 건)')
    ax.legend(loc='upper center',bbox_to_anchor=(.5,1.24),ncol=2,frameon=False,fontsize=9.5)
    ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True);fig.tight_layout(rect=[0,0,1,.94]);save(fig,'09_fixed_hub_walking_audit')

    hourly=pd.read_csv(results/'hourly.csv').set_index('hour');hours=[23,0,1,2,3]
    fig,axes=plt.subplots(1,2,figsize=(10,3.0),gridspec_kw={'width_ratios':[1,1.15]})
    ax=axes[0];x=np.arange(5);ax.bar(x,hourly.loc[hours].n_share*100,color=GREEN)
    for i,v in enumerate(hourly.loc[hours].n_share*100):ax.text(i,v+2,f'{v:.2f}%',ha='center',fontsize=8.5)
    ax.set_xticks(x,[f'{h:02d}시' for h in hours]);ax.set_ylim(0,117);ax.set_ylabel('도로버스 승차 중 N노선 비중(%)')
    ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);ax.set_title('관측 시간대별 이용 구조',fontsize=10.5,loc='left',pad=10)
    t=pd.read_csv(results/'hub_temporal_audit.csv');a=t[['new_area_b23','new_area_b00','new_area_b01','new_area_b02','new_area_b03']].sum()
    ax=axes[1];ax.bar(x,a.to_numpy(),color=ORANGE)
    for i,v in enumerate(a):ax.text(i,v+600,f'{v:,}',ha='center',fontsize=9)
    ax.set_xticks(x,[f'{h:02d}시' for h in hours]);ax.set_ylim(0,47000);ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_:f'{int(v):,}'))
    ax.set_ylabel('월간 비N 승차(건)');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    ax.set_title('가상 3거점의 기하학적 추가권 48곳',fontsize=10.5,loc='left',pad=10)
    fig.tight_layout(w_pad=3);save(fig,'10_observed_transition_hours')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--results',type=Path,default=ROOT/'results');p.add_argument('--output',type=Path,default=ROOT/'figures')
    a=p.parse_args();make_figures(a.results,a.output)
