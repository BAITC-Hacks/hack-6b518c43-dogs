"""Two preregistered experiments; never imported by the contest agent."""
import importlib.util
import math
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('stage3_baseline',ROOT/'reports/stage3/baseline/agent.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base);base.ROOT=ROOT

class RepeatEngine(base.Engine):
    def next_pilot(self,budget,contacts):
        # Research cannot consume the contacts reserved for final execution.
        remaining=min(contacts,int(self.total_contacts*.20)-self.spent_contacts)
        if remaining<=10:return None
        if len(self.log)>=4 and sum(p.get('repeat_validation',False) for p in self.log)<6:
            plan=self.solve(improve=False);details=self.forecast(plan)['details']
            total=sum(max(0,d['marginal_net']) for d in details)
            options=[]
            for detail in details:
                campaign=detail['campaign'];indices=self.audience(campaign)[:detail['contacts']]
                for cell in sorted(set(self.cell_keys[indices])-{''}):
                    key=self.state_key(cell,campaign['target_tariff'],campaign['channel']);state=self.states[key]
                    if state['pilots']!=1:continue
                    cell_ids=indices[self.cell_keys[indices]==cell]
                    share=len(cell_ids)/max(1,len(indices))
                    contribution=max(0,detail['marginal_net'])*share;cost=detail['cost']*share
                    if contribution<.10*total and cost<.10*self.total_budget:continue
                    mu,sd=self.estimate(cell,campaign['target_tariff'],campaign['channel'])
                    arpu=max(1,self.cells[cell]['arpu_sum']/self.cells[cell]['n'])
                    score=mu-self.channels[campaign['channel']]['cost_per_contact']/arpu
                    alternatives=[]
                    for target in self.tariffs:
                        if target==self.cells[cell]['current']:continue
                        for channel,settings in self.channels.items():
                            if self.state_key(cell,target,channel)==key:continue
                            am,asd=self.estimate(cell,target,channel)
                            alternatives.append((am-settings['cost_per_contact']/arpu,asd))
                    alternative=max(alternatives,default=(0.,0.))
                    if score-alternative[0]>2*math.sqrt(sd*sd+alternative[1]**2):continue
                    channel=campaign['channel']
                    if self.channels[channel]['conversion_multiplier']<=1:
                        channel=min((ch for ch in self.channels if self.channels[ch]['conversion_multiplier']<=1),
                                    key=lambda ch:(abs(self.channels[ch]['conversion_multiplier']-.65),ch))
                    price=self.channels[channel]['cost_per_contact']
                    n=min(180 if self.channels[channel]['conversion_multiplier']<=1 else 100,
                          self.cells[cell]['n'],remaining-10)
                    if price:n=min(n,int(max(0,self.total_budget*.20-self.spent_budget)//price),int(budget//price))
                    if n<min(40,self.cells[cell]['n']):continue
                    options.append((contribution*sd/max(abs(mu),sd,1e-12)+cost,key,
                        dict(cell=cell,target=campaign['target_tariff'],channel=channel,key=key,
                             requested_n=n,value=None,repeat_validation=True)))
            if options:return sorted(options,key=lambda x:(-x[0],x[1]))[0][2]
        choice=super().next_pilot(budget,remaining)
        if choice:
            price=self.channels[choice['channel']]['cost_per_contact']
            n=min(choice['requested_n'],remaining-10,self.cells[choice['cell']]['n'])
            if price:n=min(n,int(max(0,self.total_budget*.20-self.spent_budget)//price),int(budget//price))
            if n<=0:return None
            choice['requested_n']=n
        return choice

    def observe(self,choice,result,before,after):
        super().observe(choice,result,before,after)
        self.log[-1]['repeat_validation']=bool(choice.get('repeat_validation'))
        if choice.get('repeat_validation'):
            self.log[-1]['reason']='Повторная проверка крупного решения: преимущество перед альтернативой недостаточно определено.'

class RevisitEngine(RepeatEngine):
    def observe(self,choice,result,before,after):
        super().observe(choice,result,before,after)
        innovations={}
        for p in self.log:
            key=self.state_key(p['cell'],p['campaign']['target_tariff'],p['campaign']['channel'])
            if key not in innovations:
                mult=self.channels[p['campaign']['channel']]['conversion_multiplier'];scale=mult if mult<=1 else 1.
                innovations[key]=p['observed_ratio']/scale-p['prior']['prior']['mean']
        if len(innovations)>=3:
            disagreement=max(0.,-float(np.median(list(innovations.values()))))
            for state in self.states.values():
                if state['samples']==0:
                    prior=state['prior'];state['mean']=prior['mean']-min(max(0,prior['mean']),disagreement)
                    state['variance']=prior['variance']+disagreement**2
            self.log[-1]['history_revisit']=dict(directions=len(innovations),median_negative_innovation=disagreement)

    def next_pilot(self,budget,contacts):
        choice=super().next_pilot(budget,contacts)
        if choice and choice.get('repeat_validation'):return choice
        remaining=min(contacts,int(self.total_contacts*.20)-self.spent_contacts)
        if len(self.log)%4!=3 or remaining<=10:return choice
        exposures={k:0 for k in self.cells}
        for d in self.forecast(self.solve(improve=False))['details']:
            ids=self.audience(d['campaign'])[:d['contacts']]
            for key in sorted(set(self.cell_keys[ids])-{''}):exposures[key]+=int((self.cell_keys[ids]==key).sum())
        options=[]
        channel=min((ch for ch in self.channels if self.channels[ch]['conversion_multiplier']<=1),key=lambda ch:(abs(self.channels[ch]['conversion_multiplier']-.65),ch))
        price=self.channels[channel]['cost_per_contact']
        for cell,data in self.cells.items():
            for target in self.tariffs:
                if target==data['current']:continue
                key=self.state_key(cell,target,channel);state=self.states[key]
                if state['samples']:continue
                n=min(100,data['n'],remaining-10)
                if price:n=min(n,int(max(0,self.total_budget*.20-self.spent_budget)//price),int(budget//price))
                if n<min(40,data['n']):continue
                mu,sd=self.estimate(cell,target,channel)
                value=(mu+sd)*data['arpu_sum']*max(.1,exposures[cell]/data['n'])-n*price
                options.append((value,key,dict(cell=cell,target=target,channel=channel,key=key,requested_n=n,value=value,exploration=True)))
        return sorted(options,key=lambda x:(-x[0],x[1]))[0][2] if options else choice

class ExperimentalAgent(base.Agent):
    engine_class=RepeatEngine
    def act(self,env):
        # Baseline Agent creates a fresh Engine; swap only this private module's class.
        original=base.Engine
        try:
            base.Engine=self.engine_class
            return super().act(env)
        finally:base.Engine=original

class RevisitAgent(ExperimentalAgent):engine_class=RevisitEngine
POLICIES={'baseline':base.Agent,'fixed':lambda **kw:base.Agent(policy='fixed_pilots',**kw),
          'repeat':ExperimentalAgent,'revisit':RevisitAgent}
