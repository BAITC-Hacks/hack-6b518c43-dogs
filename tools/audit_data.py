"""Read-only audit of the supplied synthetic CSV files. Python standard library only."""
from __future__ import annotations
import csv, hashlib, json, math, statistics
from pathlib import Path
from collections import Counter, defaultdict
ROOT = Path(__file__).resolve().parents[1]

def read_csv(relative):
    with (ROOT / relative).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)

def main():
    paths = ['customer_profile.csv', 'data/change_tariff.csv', 'data/arpu_monthly.csv', 'data/traffic.csv', 'data/dict_tariff.csv', 'tariff_dictionary.csv', 'feature_dictionary.csv']
    frames, summaries = {}, {}
    for path in paths:
        headers, rows = read_csv(path); frames[path] = rows
        ids = {r['ID_NUMBER'] for r in rows} if 'ID_NUMBER' in headers else set()
        dates = sorted({r[c] for r in rows for c in ('TIME_KEY','time_key') if c in r})
        summaries[path] = dict(rows=len(rows), columns=len(headers), column_names=headers,
            unique_ids=len(ids) if ids else None,
            empty_by_column={h:sum(r[h] == '' for r in rows) for h in headers if any(r[h] == '' for r in rows)},
            dates=dates,
            sha256=hashlib.sha256((ROOT/path).read_bytes()).hexdigest())
    profile = frames['customer_profile.csv']; history = frames['data/change_tariff.csv']; traffic = frames['data/traffic.csv']
    ids_p={r['ID_NUMBER'] for r in profile}; ids_h={r['ID_NUMBER'] for r in history}
    ids_t={r['ID_NUMBER'] for r in traffic}; ids_a={r['ID_NUMBER'] for r in frames['data/arpu_monthly.csv']}
    cells=defaultdict(list)
    for r in profile: cells[(r['current_tariff'],r['arpu_segment'])].append(r)
    cells_report = sorted([dict(current_tariff=k[0], arpu_segment=k[1], n=len(v), predicted_arpu_sum=sum(float(r['predicted_arpu']) for r in v), predicted_arpu_mean=statistics.mean(float(r['predicted_arpu']) for r in v)) for k,v in cells.items()],key=lambda x:-x['predicted_arpu_sum'])
    high=[r for r in profile if r['arpu_segment']=='HIGH']
    all_arpu=sum(float(r['predicted_arpu']) for r in profile)
    hcells=Counter(); negative=0; n_prev_small=0; historic_ratios=[]
    for r in history:
        before=float(r['AVG_ARPU_PREV_3M']); after=float(r['AVG_ARPU_NEXT_3M'])
        negative += after<before
        if before<100: n_prev_small+=1;continue
        segment='LOW' if before<=1000 else 'MID' if before<=5000 else 'HIGH'
        hcells[(r['tariff_plan_code_from'],r['tariff_plan_code_to'],segment)]+=1
        historic_ratios.append(max(-1,min(3,(after-before)/before)))
    lte_inconsistent=sum(float(r['LTE_DATA_VOLUME'])>float(r['DATA_VOLUME']) for r in profile if r['LTE_DATA_VOLUME'] and r['DATA_VOLUME'])
    profile_segments={col:dict(Counter(r[col] for r in profile)) for col in ('arpu_segment','data_segment','call_segment','current_tariff','ARPU_trend')}
    tariffs=frames['data/dict_tariff.csv']
    features={r['feature']:r for r in frames['feature_dictionary.csv']}
    dups={path:len(rows)-len(set(tuple(r.items()) for r in rows)) for path,rows in frames.items()}
    result=dict(files=summaries, exact_duplicate_rows=dups, profile=dict(total=len(profile), duplicate_ids=len(profile)-len(ids_p), baseline_sum=all_arpu, segments=profile_segments, high_arpu_users=len(high), high_arpu_baseline_share=sum(float(r['predicted_arpu']) for r in high)/all_arpu, cells=len(cells), top_cells_by_baseline=cells_report[:15], nonfinite_predicted_arpu=sum(not math.isfinite(float(r['predicted_arpu'])) for r in profile), negative_predicted_arpu=sum(float(r['predicted_arpu'])<0 for r in profile), lte_exceeds_data_volume=lte_inconsistent), overlaps=dict(profile_history=len(ids_p & ids_h),profile_traffic=len(ids_p & ids_t),profile_arpu=len(ids_p & ids_a),history_traffic=len(ids_h & ids_t),history_arpu=len(ids_h & ids_a)),history=dict(rows=len(history), negative_before_after_changes=negative, prev_arpu_below_100=n_prev_small, observed_transition_cells=len(hcells), cells_below_10_observations=sum(v<10 for v in hcells.values()),cells_below_30_observations=sum(v<30 for v in hcells.values()), same_tariff_rows=sum(r['tariff_plan_code_from']==r['tariff_plan_code_to'] for r in history), clipped_ratio_mean=statistics.mean(historic_ratios)),tariffs=tariffs, features=list(features.values()))
    out=ROOT/'reports/data_audit.json';out.parent.mkdir(exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('features','tariffs')},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
