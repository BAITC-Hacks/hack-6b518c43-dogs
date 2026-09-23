"""Our own synthetic worlds. Truth lives solely in this harness, never the agent.

These scenarios are not the organizer mock or hidden-judging predictions.
"""
import json
import math
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


CHANNELS={'push':dict(cost_per_contact=0,conversion_multiplier=.5),
          'sms':dict(cost_per_contact=4,conversion_multiplier=.65),
          'digital_ads':dict(cost_per_contact=22,conversion_multiplier=.85),
          'call':dict(cost_per_contact=160,conversion_multiplier=1.2)}
SCENARIOS=['prior_overestimation','sign_flip','rare_transition','weak_returns','adverse_first_pilots','limited_resources','call_saturation']


def world(scenario,seed,heldout=False):
    rng=np.random.default_rng(seed)
    n=1200
    profile=pd.DataFrame(dict(ID_NUMBER=[f'customer_{i:05}' for i in range(n)],
        current_tariff=['a' if i<n//2 else 'b' for i in range(n)],
        arpu_segment=['MID' if i%2 else 'HIGH' for i in range(n)],
        data_segment=['HEAVY' if i%3 else 'LITE' for i in range(n)],call_segment=['MEDIUM']*n,
        predicted_arpu=np.where(np.arange(n)%2,2400.,6400.)))
    tariffs=pd.DataFrame(dict(tariff_plan_code=['a','b','c','d'],price_tariff=[2500,4000,5000,1800]))
    total_budget=1200 if scenario=='limited_resources' else 40000
    total_contacts=300 if scenario=='limited_resources' else 1800
    env=SimpleNamespace(customer_profile=profile,tariffs=tariffs,channels=CHANNELS,remaining_budget=total_budget,
                        remaining_contacts=total_contacts,pilots_left=20,pilot_history=[])
    pilot_records=[]
    def ratio(current,segment,target,channel):
        if target==current:return 0.
        delta={'a':-.1,'b':.15,'c':.65,'d':-.2}[target]
        conversion=.45 if heldout else .60
        delta={'a':-.1,'b':.15,'c':.50 if heldout else .65,'d':-.2}[target]
        if scenario=='shifted':delta=(1.05 if heldout else .80) if target=='d' else (-.08 if heldout else -.12)
        if scenario=='weakened':delta*=.08 if heldout else .20
        if scenario=='prior_overestimation':delta*=.12
        if scenario=='sign_flip':delta=-delta
        if scenario=='rare_transition':delta=1.2 if target=='d' else -.08
        if scenario=='weak_returns':delta=-.04
        if scenario=='stage2_magnitude':delta*=.2
        if scenario=='stage2_negative_shift':delta-=.5
        if scenario=='stage2_best_switch':delta=.7 if target=='d' else -.15
        if scenario=='call_saturation':conversion=.98;delta=.45 if target=='c' else -.1
        if segment=='HIGH':delta*=.65 if heldout else .80
        return delta*min(1.,conversion*CHANNELS[channel]['conversion_multiplier'])
    def audience(campaign):
        p=profile
        for f,c in [('filter_current_tariff','current_tariff'),('filter_arpu_segment','arpu_segment'),('filter_data_segment','data_segment'),('filter_call_segment','call_segment')]:
            if campaign.get(f) is not None:
                p=p[p[c].isin(campaign[f].split(';'))] if f=='filter_current_tariff' else p[p[c]==campaign[f]]
        return p.sort_values('ID_NUMBER')
    def run_pilot(target_tariff,channel,n_customers=100,**filters):
        campaign=dict(filters,target_tariff=target_tariff,channel=channel)
        eligible=audience(campaign)
        price=CHANNELS[channel]['cost_per_contact']
        n=min(len(eligible),n_customers,env.remaining_contacts)
        if price:n=min(n,int(env.remaining_budget//price))
        if n<=0 or env.pilots_left<=0:raise RuntimeError('No pilot resources')
        selected=eligible.iloc[rng.choice(len(eligible),n,replace=False)]
        truth=np.mean([ratio(row.current_tariff,row.arpu_segment,target_tariff,channel) for row in selected.itertuples()])
        observed=float(truth+rng.normal(0,.804/math.sqrt(n)))
        if scenario=='adverse' and len(pilot_records)<(3 if heldout else 2):observed-=.30 if heldout else .25
        env.remaining_budget-=n*price;env.remaining_contacts-=n;env.pilots_left-=1
        result=dict(n_customers=n,cost=n*price,observed_lift_ratio=observed)
        env.pilot_history.append(result);pilot_records.append((campaign,selected.index.to_numpy()))
        return result
    env.run_pilot=run_pilot
    def score(plan):
        best={};contacts=0;cost=0
        executions=list(pilot_records)
        for campaign in plan:
            eligible=audience(campaign)
            price=CHANNELS[campaign['channel']]['cost_per_contact']
            remaining=total_contacts-sum(len(ids) for _,ids in executions)
            money=total_budget-sum(len(ids)*CHANNELS[c['channel']]['cost_per_contact'] for c,ids in executions)
            n=min(len(eligible),5000,max(remaining,0))
            if price:n=min(n,max(0,int(money//price)))
            executions.append((campaign,eligible.index[:n].to_numpy()))
        for campaign,ids in executions:
            contacts+=len(ids);cost+=len(ids)*CHANNELS[campaign['channel']]['cost_per_contact']
            for row in profile.loc[ids].itertuples():
                effect=row.predicted_arpu*ratio(row.current_tariff,row.arpu_segment,campaign['target_tariff'],campaign['channel'])
                best[row.ID_NUMBER]=max(best.get(row.ID_NUMBER,-math.inf),effect)
        assert contacts<=total_contacts and cost<=total_budget
        return dict(net=sum(best.values())-cost,cost=cost,contacts=contacts,unique=len(best),n_pilots=len(pilot_records))
    return env,score

