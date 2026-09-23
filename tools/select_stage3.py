"""Apply the preregistered decision rule without tuning thresholds to outcomes."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'reports/stage3'
r=json.loads((OUT/'heldout.json').read_text());g=r['groups'];base=g['official/baseline'];decisions=[]
for candidate in ['repeat','revisit']:
    c=g['official/'+candidate];reasons=[];world_improvements=0
    for family in ['official','history_correct','shifted','weakened','adverse']:
        a=g[family+'/'+candidate];b=g[family+'/baseline']
        if a['violations'] or a['max_seconds']>=240:reasons.append(f'{family}: contract/runtime failure')
        if family!='official':
            scale=max(abs(b['median']),40000)
            if a['median']<b['median']-.1*scale:reasons.append(f'{family}: median regression exceeds 10%')
            if a['negative_fraction']>b['negative_fraction']+.20000001:reasons.append(f'{family}: negative fraction worsened >.20')
            world_improvements+=a['median']>=b['median']+.1*scale
    if c['median']<base['median']*.95:reasons.append('official: median below 95% baseline')
    if c['minimum']<base['minimum']-.1*abs(base['median']):reasons.append('official: minimum regression exceeds boundary')
    if c['negative_fraction']>base['negative_fraction']:reasons.append('official: negative fraction worsened')
    if not(c['median']>=base['median']*1.05 or world_improvements>=2):reasons.append('insufficient material improvement')
    if c['mean_absolute_error']>=base['mean_absolute_error']:reasons.append('official forecast MAE did not improve')
    decisions.append(dict(policy=candidate,eligible=not reasons,reasons=reasons,world_improvements=world_improvements))
eligible=[d['policy'] for d in decisions if d['eligible']]
selected='baseline'
if eligible:
    best=max(g['official/'+p]['median'] for p in eligible)
    tied=[p for p in eligible if g['official/'+p]['median']>=best*.98]
    selected=min(tied,key=lambda p:g['official/'+p]['mean_absolute_error'])
report=dict(selected=selected,decisions=decisions,protocol='docs/STAGE3_VALIDATION_PROTOCOL.md',
    caution='Official seeds change observation noise, not hidden truth. Authored families are reported separately. No future judging guarantee.')
(OUT/'selection.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,indent=2))
for k,v in g.items():print(k,{x:round(v[x],2) if isinstance(v[x],float) else v[x] for x in ['median','minimum','negative_fraction','mean_absolute_error','mean_pilot_contacts','violations']})
