"""Fixed synthetic plan-corruption cases: audit disabled versus audit+repair."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_engine import EngineTests
helper=EngineTests();engine=helper.engine(200)
helper.set_ratio(engine,'b',.4);helper.set_ratio(engine,'c',-.2)
campaign=engine.campaign('a|MID','b','sms')
cases=[('duplicate',[campaign,campaign],{'budget':100000}),
       ('resource_order',[dict(campaign,channel='call'),campaign],{'budget':1000}),
       ('invalid_filter',[dict(campaign,filter_arpu_segment='TYPO')],{'budget':100000})]
records=[]
for name,plan,constraints in cases:
    before=engine.audit(plan,constraints);repaired=engine.solve(constraints);after=engine.audit(repaired,constraints)
    records.append(dict(case=name,without_repair={'valid':before['valid'],'findings':before['findings'],'forecast_net':before['forecast']['net']},
                        with_repair={'valid':after['valid'],'findings':after['findings'],'forecast_net':after['forecast']['net']},
                        repaired_plan=repaired))
assert all(r['with_repair']['valid'] for r in records)
report=dict(source='Custom synthetic stress / forecast audit ablation',scope='Fixed authored corruptions, not official or hidden effects.',results=records)
(ROOT/'reports/levra/audit_repair_ablation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
print('Audit/repair: 3 fixed cases verified')
