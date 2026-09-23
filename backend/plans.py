"""Immutable plan versions shared by manual UI and the assistant's tools."""
import csv
from copy import deepcopy
import io
import json
import uuid
from backend.identity import compatible, verified_measurement
from backend.presentation import evidence_summary
from datetime import datetime, timezone

CHANNEL_LABELS={'push':'Push','sms':'SMS','digital_ads':'Реклама','call':'Звонки'}
METRIC_LABELS={'net':'Ожидаемый чистый прирост','cost':'Расход с учётом проверок',
    'contacts':'Контакты с учётом проверок','estimated_unique':'Оценка уникального охвата'}

class PlanService:
    def __init__(self,root,load_run,restore,bundle,save,tariff_lookup=None):
        self.root=root;self.load_run=load_run;self.restore=restore;self.bundle=bundle;self.save=save
        self.tariff_lookup=tariff_lookup
        self.directory=root/'plans';self.directory.mkdir(parents=True,exist_ok=True)

    def get(self,run_id,plan_id=None):
        record=deepcopy(self.load_run(run_id))
        for passport in record['passports']:
            passport['summary']=evidence_summary(passport,record['knowledge']['pilots'])
        plan_id=plan_id or run_id
        if plan_id==run_id:
            return dict({k:record[k] for k in ['plan','forecast','audit','passports','cautious_net']},
                plan_id=run_id,run_id=run_id,base_plan_id=None,data_version=record['knowledge']['snapshot_id'],
                new_pilots=0,measurement=verified_measurement(record,run_id,record['plan']),
                identity=record.get('identity'),archived=not compatible(record),created_at=record.get('created_at'),
                measurement_binding=record.get('measurement_binding'),source='Проверка на данных кейса')
        if not isinstance(plan_id,str) or len(plan_id)!=36 or any(c not in '0123456789abcdef-' for c in plan_id):
            raise ValueError('Некорректная версия плана')
        file=self.directory/(plan_id+'.json')
        if not file.exists():raise ValueError('Версия плана не найдена')
        plan=json.loads(file.read_text())
        if plan['run_id']!=run_id or plan['data_version']!=record['knowledge']['snapshot_id'] or plan.get('identity')!=record.get('identity'):
            raise ValueError('Версия относится к другому набору наблюдений')
        for i,campaign in enumerate(plan['plan']):campaign['campaign_name']=f'BeeAgent_{i+1:02d}'
        for i,detail in enumerate(plan['forecast']['details']):detail['campaign']['campaign_name']=f'BeeAgent_{i+1:02d}'
        plan['archived']=not compatible(record)
        plan['measurement']=None
        for passport in plan['passports']:
            passport['summary']=evidence_summary(passport,record['knowledge']['pilots'])
        return plan

    def active_id(self,run_id):
        file=self.directory/(run_id+'.active')
        return file.read_text().strip() if file.exists() else run_id

    def propose(self,run_id,base_plan_id,constraints,repair_plan=None):
        base=self.get(run_id,base_plan_id);record=self.load_run(run_id)
        if not compatible(record):raise ValueError('Архивный запуск: версия движка или данных изменилась. Рассчитайте новый план.')
        engine=self.restore(record)
        if not isinstance(constraints,dict) or set(constraints)-{'budget','contacts','channels','max_campaigns','risk'}:
            raise ValueError('Неизвестное ограничение')
        combined={**base['forecast']['constraints'],**constraints}
        before=engine.snapshot()
        plan=engine.solve(combined)
        result=self.bundle(engine,plan,combined)
        for passport in result['passports']:
            passport['summary']=evidence_summary(passport,record['knowledge']['pilots'])
        result.update(plan_id=str(uuid.uuid4()),run_id=run_id,base_plan_id=base['plan_id'],
            data_version=base['data_version'],snapshot_id=base['data_version'],new_pilots=0,
            measurement=None,identity=record['identity'],archived=False,source='Прогноз изменённого плана',prior_forecast=base['forecast'],
            delta={k:result['forecast'][k]-base['forecast'][k] for k in METRIC_LABELS},
            created_at=datetime.now(timezone.utc).isoformat())
        if repair_plan is not None:result['before_audit']=engine.audit(repair_plan,combined)
        if engine.snapshot()!=before:raise RuntimeError('Пересчёт изменил наблюдения')
        self.save(self.directory/(result['plan_id']+'.json'),result)
        return result

    def apply(self,run_id,plan_id,expected_active):
        result=self.get(run_id,plan_id)
        if result.get('archived'):raise ValueError('Архивная версия доступна для чтения и экспорта. Рассчитайте новый план.')
        if self.active_id(run_id)!=expected_active:
            raise ValueError('Активный план изменился. Откройте запуск заново и сравните версии.')
        self.directory.joinpath(run_id+'.active').write_text(result['plan_id'])
        return result

    def export(self,run_id,plan_id):
        plan=self.get(run_id,plan_id)
        output=io.StringIO(newline='')
        columns=['campaign_name','filter_arpu_segment','filter_data_segment','filter_call_segment','filter_current_tariff','target_tariff','channel']
        writer=csv.DictWriter(output,fieldnames=columns);writer.writeheader();writer.writerows(plan['plan'])
        return output.getvalue().encode('utf-8')

    def compare(self,run_id,base_id,proposed_id):
        base=self.get(run_id,base_id);proposed=self.get(run_id,proposed_id)
        return dict(run_id=run_id,data_version=base['data_version'],base=base,proposed=proposed,
            delta={k:proposed['forecast'][k]-base['forecast'][k] for k in METRIC_LABELS})

    def context(self,run_id,plan_id):
        bundle=self.get(run_id,plan_id)
        if bundle.get('archived'):raise ValueError('Архивный запуск: новый расчёт нужен для работы ассистента.')
        metrics=[dict(metric_id=f'{plan_id}:{key}',label=label,value=bundle['forecast'][key],
                    unit='у.е.' if key in ['net','cost'] else 'контактов' if key=='contacts' else 'клиентов',
                    source='Расчёт движка',plan_id=plan_id) for key,label in METRIC_LABELS.items()]
        evidence=[dict(evidence_id=f'{plan_id}:method',text='Прогноз использует оценки после проверок и исторические гипотезы. Интервалы модели не откалиброваны. Прогноз может быть завышен из-за отбора шумных положительных оценок.'),
            dict(evidence_id=f'{plan_id}:resources',text='Расход включает уже проведённые проверки. Отключение канала действует на будущие кампании. Пересчёт использует сохранённые наблюдения и не запускает проверки повторно.')]
        campaigns=[]
        for i,(detail,passport) in enumerate(zip(bundle['forecast']['details'],bundle['passports'])):
            uncertainty=sum(x['samples']==0 for x in passport['evidence'])
            metrics.append(dict(metric_id=f'{plan_id}:campaign:{i}:net',label=f'Вклад кампании {i+1}',
                value=detail['marginal_net'],unit='у.е.',source='Расчёт движка',plan_id=plan_id))
            metric=dict(metric_id=f'{plan_id}:campaign:{i}:uncertainty',label=f'Чувствительность кампании {i+1}',
                value=detail['uncertainty_scale'],unit='у.е.',source='Масштаб одной стандартной ошибки, не граница риска',plan_id=plan_id)
            metrics.append(metric)
            ev=dict(evidence_id=f'{plan_id}:campaign:{i}',text=f'Кампания {i+1}: '+
                ('в оценке есть направления без пилотных контактов. ' if uncertainty else 'оценки направлений опираются на пилотные контакты. ')+
                ('Модель допускает смену знака эффекта. ' if any(e['interval'][0]<=0<=e['interval'][1] for e in passport['evidence']) else 'Внутри интервала модели знак эффекта не меняется. ')+
                'Это не доказательство причинного эффекта. Размер аудитории и её ожидаемая выручка усиливают чувствительность денежного прогноза.')
            evidence.append(ev)
            campaigns.append(dict(index=i,campaign=detail['campaign'],contacts=detail['contacts'],
                cost=detail['cost'],marginal_net=detail['marginal_net'],unpiloted_cells=uncertainty,
                evidence_summary=passport['summary'],
                uncertainty_scale=detail['uncertainty_scale'],evidence_id=ev['evidence_id']))
        return dict(run_id=run_id,plan_id=plan_id,data_version=bundle['data_version'],identity=bundle.get('identity'),
            constraints=bundle['forecast']['constraints'],metrics=metrics,evidence=evidence,campaigns=campaigns,
            measurement={k:bundle['measurement'][k] for k in ['net_arpu_gain','total_cost','total_contacts','unique_customers_targeted']} if bundle['measurement'] else None)

    def campaign_evidence(self,run_id,plan_id,index):
        bundle=self.get(run_id,plan_id)
        if type(index)!=int or not 0<=index<len(bundle['plan']):raise ValueError('Кампания не найдена')
        record=self.load_run(run_id)
        if not compatible(record):raise ValueError('Архивный запуск: новый расчёт нужен для сравнения каналов.')
        engine=self.restore(record);context=self.context(run_id,plan_id)
        context['campaigns']=[context['campaigns'][index]]
        context['passport']=bundle['passports'][index]
        chosen=bundle['plan'][index]
        codes=[chosen['target_tariff'],*chosen.get('filter_current_tariff','').split(';')]
        context['tariffs']=self.tariff_lookup(codes) if self.tariff_lookup else []
        context['pilot_observations']=[dict(index=p['index'],actual_n=p['actual_n'],cost=p['cost'],
            observed_ratio=p['observed_ratio'],channel=p['campaign']['channel'],
            estimate_before=p['prior']['mean'],estimate_after=p['posterior']['mean'])
            for p in engine.log if p['index'] in context['passport']['pilots']]
        for pilot in context['pilot_observations']:
            context['metrics'].append(dict(metric_id=f'{plan_id}:pilot:{pilot["index"]}:observed',
                label=f'Наблюдаемый эффект проверки {pilot["index"]}',value=pilot['observed_ratio']*100,unit='%',
                source=f'Проверка на {pilot["actual_n"]} контактах; шумное наблюдение',plan_id=plan_id))
        context['channel_alternatives']=[]
        for channel in engine.channels:
            plan=[dict(c) for c in bundle['plan']];plan[index]['channel']=channel
            constraints={**bundle['forecast']['constraints'],'channels':list(engine.channels)}
            alternative=engine.forecast(plan,constraints)
            metric_id=f'{plan_id}:campaign:{index}:channel:{channel}'
            context['metrics'].append(dict(metric_id=metric_id,label=f'Весь план при канале «{CHANNEL_LABELS[channel]}»',
                value=alternative['net'],unit='у.е.',source='Условная замена канала без новой оптимизации',plan_id=plan_id))
            context['channel_alternatives'].append(dict(channel=channel,cost_per_contact=engine.channels[channel]['cost_per_contact'],
                enabled=channel in bundle['forecast']['constraints']['channels'],net=alternative['net'],metric_id=metric_id))
        context['evidence'].append(dict(evidence_id=f'{plan_id}:campaign:{index}:channels',
            text='Сравнение каналов заменяет канал выбранной кампании в том же порядке. Более дорогой контакт сокращает доступный охват. Звонки имеют отдельную оценку эффекта; сравнение не подтверждает их эффект наблюдением. Если замена выгоднее, это ограничение эвристического поиска, а не доказательство оптимальности текущего выбора.'))
        # Only selected evidence and aggregates; never customer rows or full history.
        context['evidence']=[e for e in context['evidence'] if e['evidence_id'].endswith((':method',':resources',f':campaign:{index}',f':campaign:{index}:channels'))]
        return context
