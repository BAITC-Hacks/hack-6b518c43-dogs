"""Read-only product evidence derived from stored public observations.

These summaries never participate in campaign selection or scoring.
"""


def evidence_summary(passport, pilots):
    evidence = passport['evidence']
    observed = [p for p in pilots if p['index'] in passport['pilots']]
    untested = sum(e['samples'] == 0 for e in evidence)
    uncertain = sum(e['interval'][0] <= 0 <= e['interval'][1] for e in evidence)
    repeated = any(e['pilots'] >= 2 for e in evidence)
    if not evidence or untested or uncertain:
        level = 'limited'
        reason = ('Есть направления без пилотных наблюдений.' if untested else
                  'Интервал модели допускает нулевой или отрицательный эффект.' if uncertain else
                  'Для этой аудитории нет оценки.')
    elif all(e['pilots'] >= 2 and e['samples'] >= 200 for e in evidence):
        level = 'strong'
        reason = 'Каждое направление проверено повторно; интервалы модели не включают ноль.'
    else:
        level = 'moderate'
        reason = 'Все направления имеют наблюдения, но не все подтверждены повторно на 200 контактах.'
    return dict(level=level,reason=reason,pilot_count=len(observed),
                sample_size=sum(p['actual_n'] for p in observed),
                direct_history_rows=sum(e['prior']['n_history'] for e in evidence),
                untested_cells=untested,uncertain_cells=uncertain,repeated=repeated,
                scope='Все модельные группы аудитории до усечения. Уровень не является вероятностью успеха.')


def activity(snapshot):
    states=snapshot['states'];pilots=snapshot['pilots']
    directions={tuple(key.split('|')[:3]) for key in states}
    direct={tuple(key.split('|')[:3]) for key,s in states.items() if s['prior']['n_history']>0}
    stop=snapshot['stop_reason']
    # The snapshot has the original reason; report observable exhausted research
    # resources as well because early exit shares a generic VOI string in v3.
    if len(pilots)>=20:stop='Достигнут лимит: 20 пилотов.'
    elif snapshot['total_contacts']*.20-snapshot['spent_contacts']<=10:
        stop='Исчерпан контактный резерв исследования: остаток не больше 10 контактов.'
    elif stop.startswith('History-only'):stop='В этом исследовании пилоты не проводились.'
    return dict(hypotheses=len(directions),direct_history_hypotheses=len(direct),
                pilots=len(pilots),material_repeats=sum(bool(p.get('repeat_validation')) for p in pilots),
                changed_decisions=sum(bool(p.get('decision_change',{}).get('selection_changed')) for p in pilots),
                traced_pilots=sum('decision_change' in p for p in pilots),stop_reason=stop,
                total_budget=snapshot['total_budget'],total_contacts=snapshot['total_contacts'],
                pilot_limit=20,research_budget=snapshot['total_budget']*.20,
                research_contacts=int(snapshot['total_contacts']*.20))
