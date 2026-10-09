"""Prefix-only chart rendering for the AI proxy; never reads sealed metadata."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
import xml.etree.ElementTree as ET
import sys

ROOT=Path('governance/post_dual_review_gate2_adjudication_pre_gate3_closure_v2/supplemental_blind_view')
OUT=Path('.akah_bot/gate2_visible_v3')

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=json.loads((ROOT/'visible_cases.json').read_text())['cases']
    for batch in range(0,len(cases),6):
        count=min(6,len(cases)-batch)
        fig,axes=plt.subplots(count,5,figsize=(25,3.5*count),squeeze=False)
        for row,case in enumerate(cases[batch:batch+6]):
            cid=case['case_id']
            for col,tf in enumerate(('1D','4H','1H')):
                frame=pd.read_csv(ROOT/'prefixes'/f'{cid}_{tf}.csv')
                ax=axes[row,col]
                ax.vlines(frame.rel_bar,frame.low,frame.high,color='gray',lw=.35)
                ax.plot(frame.rel_bar,frame.close,lw=.8)
                ax.set_title(cid+' '+case['school']+' '+tf+' '+case['allowed_ny_session'],fontsize=8)
                ax.grid(alpha=.2)
            rs=pd.read_csv(ROOT/'prefixes'/f'{cid}_RS.csv')
            axes[row,3].plot(rs.iloc[:,0],rs.iloc[:,1],lw=.8)
            axes[row,3].set_title('Visible relative-strength ratio',fontsize=8)
            frame=pd.read_csv(ROOT/'prefixes'/f'{cid}_1H.csv').tail(64)
            axes[row,4].vlines(frame.rel_bar,frame.low,frame.high,color='gray',lw=.7)
            axes[row,4].plot(frame.rel_bar,frame.close,lw=.9)
            axes[row,4].set_title('Final 64 visible 1H bars',fontsize=8)
            for ax in axes[row]: ax.tick_params(labelsize=6)
        fig.tight_layout()
        path=OUT/f'visible_batch_{batch//6+1}.png'
        fig.savefig(path,dpi=110)
        plt.close(fig)
        print('IMAGE='+str(path))

def market():
    """Render only already-visible SVG geometry; no hidden map or market source."""
    cases=json.loads((ROOT/'visible_cases.json').read_text())['cases']
    for batch in range(0,len(cases),6):
        count=min(6,len(cases)-batch)
        fig,axes=plt.subplots(count,3,figsize=(24,3.2*count),squeeze=False)
        for row,case in enumerate(cases[batch:batch+6]):
            cid=case['case_id']
            for col,tf in enumerate(('MARKET_1D','MARKET_4H','VOLUME')):
                ax=axes[row,col]
                root=ET.parse(ROOT/'images'/f'{cid}_{tf}.svg').getroot()
                for el in root.iter():
                    tag=el.tag.split('}')[-1]; a=el.attrib
                    if tag=='line':
                        ax.plot([float(a['x1']),float(a['x2'])],[float(a['y1']),float(a['y2'])],color=a.get('stroke','gray'),lw=.5)
                    elif tag=='polyline':
                        points=[tuple(map(float,p.split(','))) for p in a['points'].split()]
                        ax.plot(*zip(*points),color=a.get('stroke','blue'),lw=.8)
                ax.set_xlim(0,900); ax.set_ylim(420,0); ax.axis('off')
                ax.set_title(cid+' '+tf,fontsize=9)
        fig.tight_layout(); path=OUT/f'market_batch_{batch//6+1}.png'
        fig.savefig(path,dpi=110); plt.close(fig); print('IMAGE='+str(path))

if __name__=='__main__': market() if '--market' in sys.argv else main()
