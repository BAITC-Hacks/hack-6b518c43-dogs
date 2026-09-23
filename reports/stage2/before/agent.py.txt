"""LEVRA: deterministic offline campaign decisions using only the public interface.

History is an association, not causal uplift or measured offer conversion.
No organizer module is imported by this file. UI and test harnesses reuse Engine.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

FILTERS = {
    'filter_arpu_segment': ('arpu_segment', ('LOW', 'MID', 'HIGH')),
    'filter_data_segment': ('data_segment', ('NON_USER', 'LITE', 'HEAVY')),
    'filter_call_segment': ('call_segment', ('LOW', 'MEDIUM', 'HIGH')),
}
NOISE = 0.804
MAX_CAMPAIGNS = 10
CAMPAIGN_CAP = 5000
ROOT = Path(__file__).resolve().parent


def normal_update(mean, variance, observed, actual_n, multiplier=1.0):
    """Precision-weighted update; actual, not requested, sample size."""
    if actual_n <= 0 or not math.isfinite(observed):
        return mean, variance
    noise_var = NOISE ** 2 / actual_n / multiplier ** 2
    v = 1.0 / (1.0 / variance + 1.0 / noise_var)
    return float(v * (mean / variance + observed / multiplier / noise_var)), float(v)


def fingerprint(profile):
    columns = ['ID_NUMBER', 'current_tariff', 'arpu_segment', 'data_segment',
               'call_segment', 'predicted_arpu']
    return hashlib.sha256(pd.util.hash_pandas_object(profile[columns], index=False).values.tobytes()).hexdigest()


def expected_best(events, final=None):
    """E[max contacted effects], with zero ONLY on the no-contact event.

    Events are independent random pilot inclusion (probability, ratio). Negative
    contacted effects remain negative. Final effects, if present, are certain.
    This is a plug-in forecast, not integration over posterior uncertainty.
    """
    higher_absent, value = 1.0, 0.0
    for probability, ratio in sorted(events, key=lambda x: -x[1]):
        if final is not None and ratio <= final:
            break
        value += higher_absent * probability * ratio
        higher_absent *= 1.0 - probability
    if final is not None:
        value += higher_absent * final
    return value


def _summary(values):
    a = np.asarray(values, dtype=float)
    return (float(np.mean(a)), len(a)) if len(a) else (0.0, 0)


class History:
    def __init__(self, path, tariffs):
        self.exact, self.direction, self.segment_target, self.source = {}, {}, {}, {}
        self.diagnostics = {'source': str(path.name), 'association_only': True}
        self.tariffs = tariffs.set_index('tariff_plan_code').to_dict('index')
        if not path.exists():
            self.diagnostics['warning'] = 'History unavailable; broad context priors only.'
            return
        h = pd.read_csv(path).drop_duplicates().copy()
        before, after = h['AVG_ARPU_PREV_3M'], h['AVG_ARPU_NEXT_3M']
        valid = np.isfinite(before) & np.isfinite(after) & (before >= 100)
        self.diagnostics.update(rows_read=len(h), rows_used=int(valid.sum()),
                                denominator_floor=100, ratio_clip=[-1, 2], deduplication='exact rows only')
        h = h.loc[valid].copy()
        h['ratio'] = ((after[valid] - before[valid]) / before[valid]).clip(-1, 2)
        h['segment'] = np.where(before[valid] < 1000, 'LOW', np.where(before[valid] <= 5000, 'MID', 'HIGH'))
        for key, g in h.groupby(['tariff_plan_code_from', 'segment', 'tariff_plan_code_to'], sort=True):
            self.exact[key] = _summary(g.ratio)
        for key, g in h.groupby(['tariff_plan_code_from', 'tariff_plan_code_to'], sort=True):
            self.direction[key] = _summary(g.ratio)
        for key, g in h.groupby(['segment', 'tariff_plan_code_to'], sort=True):
            self.segment_target[key] = _summary(g.ratio)
        self.source = h.groupby(['tariff_plan_code_from', 'segment']).size().to_dict()

    def prior(self, current, segment, target, floor):
        src, dst = self.tariffs[current], self.tariffs[target]
        price_from, price_to = float(src.get('price_tariff', 0)), float(dst.get('price_tariff', 0))
        price_context = np.clip((price_to - price_from) / max(price_from, 1000), -1, 1)
        package_columns = ['Data_in_PKG', 'Min_another_operator_in_PKG', 'Min_another_operator_and_city_in_PKG']
        package_context = float(np.mean([np.clip((float(dst.get(c, 0)) - float(src.get(c, 0))) /
                                                     max(abs(float(src.get(c, 0))), 100), -1, 1) for c in package_columns]))
        context = .12 * price_context + .03 * package_context
        broad, broad_n = self.segment_target.get((segment, target), (context, 0))
        direction, dir_n = self.direction.get((current, target), (broad, 0))
        pooled = (direction * dir_n + (broad * .7 + context * .3) * 30) / (dir_n + 30)
        mean, n = self.exact.get((current, segment, target), (pooled, 0))
        delta = (mean * n + pooled * 20) / (n + 20)
        share = (n + 1) / (self.source.get((current, segment), 0) + max(2, len(self.tariffs)))
        adoption = .12 + .48 * math.sqrt(share)  # heuristic ONLY; no offer denominator in history
        ratio = float(delta * adoption)
        variance = floor ** 2 + .12 ** 2 / (1 + n / 15)
        return {'mean': ratio, 'variance': variance, 'n_history': int(n),
                'pooled_n': int(dir_n), 'broad_n': int(broad_n), 'historical_change': float(delta),
                'adoption_heuristic': adoption, 'price_context': float(price_context),
                'package_context': package_context, 'source': 'historical association + pooling + context'}


class Engine:
    """Reusable knowledge model, ordered forecast ledger, solver and audit."""
    def __init__(self, profile, tariffs, channels, budget, contacts, history_path=None, prior_floor=.24):
        self.profile = profile.copy().sort_values('ID_NUMBER').reset_index(drop=True)
        self.tariffs = sorted(tariffs.tariff_plan_code.astype(str).tolist())
        self.channels = {k: dict(v) for k, v in sorted(channels.items())}
        self.total_budget, self.total_contacts = float(budget), int(contacts)
        self.spent_budget, self.spent_contacts = 0., 0
        self.prior_floor = prior_floor
        self.log, self.states, self.cells = [], {}, {}
        self.arpu = self.profile.predicted_arpu.to_numpy(dtype=float)
        valid = (self.profile.current_tariff.isin(self.tariffs) &
                 self.profile.arpu_segment.isin(FILTERS['filter_arpu_segment'][1]) &
                 np.isfinite(self.arpu) & (self.arpu >= 0))
        self.diagnostics = {'excluded_missing_or_invalid': int((~valid).sum()), 'profile_rows': len(profile)}
        self.cell_keys = np.full(len(profile), '', dtype=object)
        for (current, segment), g in self.profile[valid].groupby(['current_tariff', 'arpu_segment'], sort=True):
            key = current + '|' + segment
            indices = g.index.to_numpy()
            self.cells[key] = {'current': current, 'segment': segment, 'indices': indices,
                               'n': len(indices), 'arpu_sum': float(self.arpu[indices].sum())}
            self.cell_keys[indices] = key
        history = History(Path(history_path) if history_path else ROOT / 'data/change_tariff.csv', tariffs)
        self.diagnostics['history'] = history.diagnostics
        for cellkey, cell in self.cells.items():
            for target in self.tariffs:
                if target == cell['current']:
                    continue
                prior = history.prior(cell['current'], cell['segment'], target, prior_floor)
                self.states[self.key(cellkey, target, 'linear')] = dict(prior=prior, mean=prior['mean'], variance=prior['variance'], samples=0, pilots=0)
                for channel, settings in self.channels.items():
                    mult = settings['conversion_multiplier']
                    if mult > 1:
                        # Independent saturated-channel prior, never transferred pilot precision.
                        cp = dict(prior, mean=prior['mean'] * min(mult, 1.0), variance=prior['variance'] * mult ** 2)
                        self.states[self.key(cellkey, target, channel)] = dict(prior=cp, mean=cp['mean'], variance=cp['variance'], samples=0, pilots=0)
        self._audiences = {}
        self.stop_reason = 'not started'

    @staticmethod
    def key(cell, target, group):
        return cell + '|' + target + '|' + group

    def state_key(self, cell, target, channel):
        return self.key(cell, target, 'linear' if self.channels[channel]['conversion_multiplier'] <= 1 else channel)

    def estimate(self, cell, target, channel, risk=0.):
        if not cell or target == self.cells[cell]['current']:
            return 0., 0.
        state = self.states[self.state_key(cell, target, channel)]
        mult = self.channels[channel]['conversion_multiplier']
        scale = mult if mult <= 1 else 1.
        sd = math.sqrt(state['variance']) * scale
        return state['mean'] * scale - risk * sd, sd

    def campaign(self, cellkey, target, channel, extra=None):
        cell = self.cells[cellkey]
        c = {'filter_current_tariff': cell['current'], 'filter_arpu_segment': cell['segment'],
             'target_tariff': target, 'channel': channel}
        c.update(extra or {})
        return c

    def validate(self, campaign):
        errors = []
        if not isinstance(campaign, dict):
            return ['campaign must be an object']
        allowed = {'campaign_name', 'target_tariff', 'channel', 'filter_current_tariff', *FILTERS}
        if set(campaign) - allowed:
            errors.append('Недопустимые поля: ' + ', '.join(sorted(set(campaign) - allowed)))
        if campaign.get('target_tariff') not in self.tariffs:
            errors.append('Неизвестный целевой тариф')
        if campaign.get('channel') not in self.channels:
            errors.append('Неизвестный канал')
        for key, (_, values) in FILTERS.items():
            if campaign.get(key) is not None and campaign[key] not in values:
                errors.append('Недопустимый ' + key)
        currents = str(campaign.get('filter_current_tariff', '')).split(';')
        if campaign.get('filter_current_tariff') is not None and any(t.strip() not in self.tariffs for t in currents):
            errors.append('Неизвестный текущий тариф')
        if not errors:
            idx = self.audience(campaign)
            if np.any(self.profile.current_tariff.iloc[idx].to_numpy() == campaign['target_tariff']):
                errors.append('Предложение текущего тарифа недопустимо')
        return errors

    def audience(self, c):
        signature = tuple((k, c.get(k)) for k in [*FILTERS, 'filter_current_tariff'])
        if signature not in self._audiences:
            mask = np.ones(len(self.profile), dtype=bool)
            for key, (column, _) in FILTERS.items():
                if c.get(key) is not None:
                    mask &= (self.profile[column] == c[key]).to_numpy()
            if c.get('filter_current_tariff') is not None:
                mask &= self.profile.current_tariff.isin([t.strip() for t in c['filter_current_tariff'].split(';')]).to_numpy()
            self._audiences[signature] = np.flatnonzero(mask)
        return self._audiences[signature]

    def pilot_events(self, risk=0.):
        events = {k: [] for k in self.cells}
        for pilot in self.log:
            cell = pilot['cell']
            ratio, _ = self.estimate(cell, pilot['campaign']['target_tariff'], pilot['campaign']['channel'], risk)
            events[cell].append((pilot['actual_n'] / self.cells[cell]['n'], ratio))
        return events

    def constraints(self, constraints=None):
        c = dict(budget=self.total_budget, contacts=self.total_contacts, max_campaigns=10,
                 channels=list(self.channels), risk=.7)
        c.update(constraints or {})
        for key in ('budget', 'contacts', 'max_campaigns', 'risk'):
            if not isinstance(c[key], (int, float)) or not math.isfinite(c[key]):
                raise ValueError('Некорректное ограничение: ' + key)
        if c['budget'] < self.spent_budget or c['contacts'] < self.spent_contacts:
            raise ValueError('Новый лимит ниже уже потраченных ресурсов пилотов')
        if not 1 <= c['max_campaigns'] <= 10 or c['max_campaigns'] != int(c['max_campaigns']):
            raise ValueError('Допустимо от 1 до 10 финальных кампаний')
        if c['contacts'] != int(c['contacts']) or c['risk'] < 0 or c['risk'] > 3:
            raise ValueError('Некорректные контакты или коэффициент осторожности')
        if not c['channels'] or set(c['channels']) - set(self.channels):
            raise ValueError('Выберите хотя бы один допустимый канал')
        c['channels'] = sorted(set(c['channels']))
        return c

    def _empty_ledger(self, risk=0.):
        events = self.pilot_events(risk)
        ratios = np.zeros(len(self.profile))
        for cell, ids in ((k, v['indices']) for k, v in self.cells.items()):
            ratios[ids] = expected_best(events[cell])
        return {'best': np.full(len(self.profile), np.nan), 'expected': ratios,
                'events': events, 'cost': self.spent_budget, 'contacts': self.spent_contacts,
                'seen': np.zeros(len(self.profile), dtype=bool)}

    def _evaluate_step(self, campaign, ledger, constraints, risk=0., apply=False):
        audience = self.audience(campaign)
        cost = self.channels[campaign['channel']]['cost_per_contact']
        n = min(len(audience), CAMPAIGN_CAP, max(0, int(constraints['contacts'] - ledger['contacts'])))
        if cost:
            n = min(n, max(0, int((constraints['budget'] - ledger['cost']) // cost)))
        ids = audience[:n]
        after = ledger['best'][ids].copy()
        sd_sum = 0.
        for cell in sorted(set(self.cell_keys[ids])):
            loc = np.flatnonzero(self.cell_keys[ids] == cell)
            ratio, sd = self.estimate(cell, campaign['target_tariff'], campaign['channel'], risk)
            after[loc] = np.fmax(after[loc], ratio)  # fmax(NaN, negative) retains negative
            sd_sum += self.arpu[ids[loc]].sum() * sd
        expected = after.copy()
        for cell in sorted(set(self.cell_keys[ids])):
            loc = np.flatnonzero(self.cell_keys[ids] == cell)
            for value in np.unique(after[loc]):
                sub = loc[after[loc] == value]
                expected[sub] = expected_best(ledger['events'].get(cell, []), float(value))
        gain = float(((expected - ledger['expected'][ids]) * self.arpu[ids]).sum())
        record = dict(campaign=campaign, audience=len(audience), contacts=n, cost=float(n * cost),
                      marginal_net=gain - n * cost, gross_increment=gain, uncertainty_scale=float(sd_sum),
                      final_overlap=int(ledger['seen'][ids].sum()), truncated=n < min(len(audience), CAMPAIGN_CAP),
                      campaign_capped=len(audience) > CAMPAIGN_CAP)
        if apply:
            ledger['best'][ids], ledger['expected'][ids], ledger['seen'][ids] = after, expected, True
            ledger['contacts'] += n
            ledger['cost'] += n * cost
        return record

    def forecast(self, campaigns, constraints=None, risk=0.):
        c = self.constraints(constraints)
        ledger = self._empty_ledger(risk)
        details = []
        for campaign in campaigns:
            errors = self.validate(campaign)
            if errors:
                raise ValueError('; '.join(errors))
            details.append(self._evaluate_step(campaign, ledger, c, risk, True))
        gross = float((ledger['expected'] * self.arpu).sum())
        unique = float(ledger['seen'].sum())
        for cell, events in ledger['events'].items():
            p_none = math.prod(1 - p for p, _ in events)
            ids = self.cells[cell]['indices']
            unique += int((~ledger['seen'][ids]).sum()) * (1 - p_none)
        return dict(source='Forecast', net=gross - ledger['cost'], gross=gross, cost=ledger['cost'],
                    contacts=ledger['contacts'], final_unique=int(ledger['seen'].sum()), estimated_unique=unique,
                    pilot_overlap='probabilistic: independent uniform samples; IDs unknown',
                    details=details, constraints=c)

    def candidates(self, constraints):
        candidates = []
        pooled = {}
        for cellkey, cell in self.cells.items():
            ranked = []
            for channel in constraints['channels']:
                for target in self.tariffs:
                    if target == cell['current']:
                        continue
                    ratio, _ = self.estimate(cellkey, target, channel, constraints['risk'])
                    score = cell['arpu_sum'] / cell['n'] * ratio - self.channels[channel]['cost_per_contact']
                    ranked.append((score, target, channel))
            # Keep alternatives per channel so local resource shifts can change channels.
            keep = []
            for channel in constraints['channels']:
                keep += sorted([r for r in ranked if r[2] == channel], key=lambda x: (-x[0], x[1]))[:2]
            for score, target, channel in keep:
                base = self.campaign(cellkey, target, channel)
                candidates.append(base)
                if score > 0:
                    pooled.setdefault((cell['segment'], target, channel), []).append(cell['current'])
                if cell['n'] > CAMPAIGN_CAP:
                    for key, (column, values) in FILTERS.items():
                        if key == 'filter_arpu_segment':
                            continue
                        for value in values:
                            if (self.profile.loc[cell['indices'], column] == value).any():
                                candidates.append(dict(base, **{key: value}))
        for (segment, target, channel), currents in sorted(pooled.items()):
            if len(currents) > 1:
                candidates.append(dict(filter_arpu_segment=segment, filter_current_tariff=';'.join(sorted(currents)), target_tariff=target, channel=channel))
        return candidates

    def solve(self, constraints=None, improve=True):
        c = self.constraints(constraints)
        options = self.candidates(c)
        ledger = self._empty_ledger(c['risk'])
        plan = []
        for _ in range(int(c['max_campaigns'])):
            ranked = [(self._evaluate_step(x, ledger, c, c['risk']), x) for x in options]
            ranked.sort(key=lambda pair: (-pair[0]['marginal_net'], json.dumps(pair[1], sort_keys=True)))
            if not ranked or ranked[0][0]['marginal_net'] <= 0:
                break
            record, candidate = ranked[0]
            if record['contacts'] <= 0:
                break
            plan.append(candidate)
            self._evaluate_step(candidate, ledger, c, c['risk'], True)
            options.remove(candidate)
        if not plan and options:
            # Contract requires >=1 campaign even in all-negative worlds. Minimise
            # expected loss, don't turn negative values into zero or force spending.
            ranked = sorted(options, key=lambda x: (-self._evaluate_step(x, ledger, c, c['risk'])['marginal_net'], json.dumps(x, sort_keys=True)))
            plan = [ranked[0]]
        if improve and len(plan) > 1:
            best = self.forecast(plan, c, c['risk'])['net']
            # Bounded order search. Every evaluation includes exact truncation.
            for i in range(len(plan)):
                for j in range(i + 1, len(plan)):
                    trial = list(plan)
                    trial[i], trial[j] = trial[j], trial[i]
                    value = self.forecast(trial, c, c['risk'])['net']
                    if value > best + 1e-6:
                        plan, best = trial, value
            # Remove/replace weak slots by an alternative on the same audience.
            for i in range(len(plan)):
                alternatives = [x for x in options if all(x.get(k) == plan[i].get(k) for k in [*FILTERS, 'filter_current_tariff'])]
                for option in alternatives:
                    trial = plan[:i] + [option] + plan[i + 1:]
                    value = self.forecast(trial, c, c['risk'])['net']
                    if value > best + 1e-6:
                        plan, best = trial, value
        return [dict(x, campaign_name=f'LEVRA_{i + 1:02d}') for i, x in enumerate(plan)]

    def next_pilot(self, budget, contacts):
        """One-step knowledge-gradient heuristic, not exact global VOI."""
        if contacts <= 10 or not self.cells:
            return None
        best = None
        provisional = self.solve(improve=False)
        provisional_forecast = self.forecast(provisional)
        marginal_values = [max(0., d['marginal_net']) / max(1, d['contacts']) for d in provisional_forecast['details'] if d['contacts']]
        reach_shadow = min(marginal_values, default=0.)
        exposure = {key: 0 for key in self.cells}
        commitments = {}
        for detail in provisional_forecast['details']:
            indices = self.audience(detail['campaign'])[:detail['contacts']]
            for key in set(self.cell_keys[indices]):
                if key:
                    exposure[key] += int((self.cell_keys[indices] == key).sum())
                    campaign = detail['campaign']
                    statekey = self.state_key(key, campaign['target_tariff'], campaign['channel'])
                    mu, _ = self.estimate(key, campaign['target_tariff'], campaign['channel'])
                    money = float(self.arpu[indices[self.cell_keys[indices] == key]].sum()) * max(0., mu)
                    commitments[statekey] = commitments.get(statekey, 0.) + money
        # Most experiments resolve decisions in the current portfolio. Every
        # fourth step reopens the full population to discover overlooked cells.
        discovery_step = len(self.log) % 4 == 3
        # Before committing a material share of the plan to an untested prior,
        # validate it even if the Gaussian VOI is overconfident about that prior.
        material = {key for key, value in commitments.items() if value > .10 * sum(commitments.values()) and self.states[key]['samples'] == 0}
        validation_probe = None
        for cellkey, cell in self.cells.items():
            frontier = max(self.estimate(cellkey, t, ch)[0] - self.channels[ch]['cost_per_contact'] / max(cell['arpu_sum'] / cell['n'], 1)
                           for t in self.tariffs if t != cell['current'] for ch in self.channels)
            for target in self.tariffs:
                if target == cell['current']:
                    continue
                for channel, settings in self.channels.items():
                    key = self.state_key(cellkey, target, channel)
                    state = self.states[key]
                    mult = settings['conversion_multiplier']
                    transfer = mult if mult <= 1 else 1.
                    mu, sd = self.estimate(cellkey, target, channel)
                    price = settings['cost_per_contact']
                    if state['pilots'] >= 3:
                        continue
                    for requested in (40, 100, 180):
                        n = min(requested, cell['n'], contacts - 10)
                        if price:
                            n = min(n, int(budget // price))
                        if n <= 0 or n * price > max(0, self.total_budget * .20 - self.spent_budget):
                            continue
                        _, newvar = normal_update(state['mean'], state['variance'], mu, n, transfer)
                        posterior_move = math.sqrt(max(0, state['variance'] - newvar))
                        future_channels = [ch for ch in self.channels if
                                           (self.channels[ch]['conversion_multiplier'] <= 1 if mult <= 1 else ch == channel)]
                        information_gain = 0.
                        for future_channel in future_channels:
                            future = self.channels[future_channel]
                            future_scale = future['conversion_multiplier'] if mult <= 1 else 1.
                            move_sd = posterior_move * future_scale
                            future_mu = state['mean'] * future_scale
                            gap = abs(future_mu - future['cost_per_contact'] / max(cell['arpu_sum'] / cell['n'], 1) - frontier)
                            z = gap / max(move_sd, 1e-12)
                            improvement = move_sd * math.exp(-z*z / 2) / math.sqrt(2*math.pi) - gap * .5 * math.erfc(z/math.sqrt(2))
                            reachable = min(cell['n'], CAMPAIGN_CAP, contacts - n)
                            if future['cost_per_contact']:
                                reachable = min(reachable, max(0, int((budget - n*price) // future['cost_per_contact'])))
                            decision_reach = reachable if discovery_step else min(reachable, max(exposure[cellkey], .10 * reachable))
                            information_gain = max(information_gain, decision_reach * cell['arpu_sum'] / cell['n'] * improvement)
                        # An experiment competes for the same reachable audience and money.
                        contact_value = max(reach_shadow, max(0, frontier) * cell['arpu_sum'] / cell['n'])
                        value = information_gain - n * contact_value - n * price
                        identity = (cellkey, target, channel, requested)
                        if key in material and requested == 100 and n >= min(100, cell['n'], contacts - 10):
                            priority = commitments[key] + value
                            if validation_probe is None or priority > validation_probe['priority']:
                                validation_probe = dict(value=float(value), priority=priority, cell=cellkey, target=target, channel=channel, requested_n=requested, key=key, identity=identity, validation=True)
                        if best is None or value > best['value'] + 1e-8:
                            best = dict(value=float(value), cell=cellkey, target=target, channel=channel,
                                        requested_n=requested, key=key, identity=identity)
        if validation_probe is not None:
            return validation_probe
        if best and (best['value'] > 0 or not self.log):
            return best
        return None

    def observe(self, choice, result, before, after):
        key = choice['key']
        state = self.states[key]
        prior = dict(state)
        actual = int(result['n_customers'])
        mult = self.channels[choice['channel']]['conversion_multiplier']
        transfer = mult if mult <= 1 else 1.
        observed = float(result['observed_lift_ratio'])
        innovation = observed / transfer - state['mean']
        noise_var = NOISE ** 2 / max(actual, 1) / transfer ** 2
        conflict = state['samples'] == 0 and abs(innovation) > 3 * math.sqrt(state['variance'] + noise_var)
        if conflict:
            # A first observation sharply contradicting history tempers the prior.
            # This only uses that public observation; thresholds are our heuristic.
            state['variance'] = max(state['variance'], innovation ** 2)
        state['mean'], state['variance'] = normal_update(state['mean'], state['variance'], observed, actual, transfer)
        state['samples'] += actual
        state['pilots'] += 1
        self.spent_budget = self.total_budget - after['budget']
        self.spent_contacts = self.total_contacts - after['contacts']
        self.log.append(dict(index=len(self.log) + 1, cell=choice['cell'],
                             campaign=self.campaign(choice['cell'], choice['target'], choice['channel']),
                             requested_n=choice['requested_n'], actual_n=actual, cost=float(result['cost']),
                             observed_ratio=observed, prior=prior, posterior=dict(state), prior_conflict=conflict,
                             resources_before=before, resources_after=after,
                             information_value=choice.get('value'),
                             reason=('Проверка неподтверждённой гипотезы, на которую приходится существенная часть плана.' if choice.get('validation') else 'Уменьшение неопределённости может изменить выбор тарифа/канала на этой аудитории.')))

    def audit(self, plan, constraints=None):
        c = self.constraints(constraints)
        findings, valid = [], []
        if not 1 <= len(plan) <= c['max_campaigns']:
            findings.append(dict(code='campaign_count', severity='error', message='Число кампаний выходит за допустимый предел'))
        for i, campaign in enumerate(plan):
            errors = self.validate(campaign)
            for error in errors:
                findings.append(dict(code='invalid_campaign', severity='error', index=i, message=error))
            if not errors:
                valid.append(campaign)
                if campaign['channel'] not in c['channels']:
                    findings.append(dict(code='disabled_channel', severity='error', index=i, message='Канал отключён в сценарии'))
        forecast = self.forecast(valid, c)
        desired_contacts = sum(min(CAMPAIGN_CAP, len(self.audience(x))) for x in valid)
        desired_cost = sum(min(CAMPAIGN_CAP, len(self.audience(x))) * self.channels[x['channel']]['cost_per_contact'] for x in valid)
        if desired_cost + self.spent_budget > c['budget'] or desired_contacts + self.spent_contacts > c['contacts']:
            findings.append(dict(code='requested_resources', severity='warning', message='Полная аудитория не помещается в лимиты; порядок меняет фактический охват'))
        for i, d in enumerate(forecast['details']):
            if d['final_overlap']:
                findings.append(dict(code='overlap', severity='warning', index=i, message=f"Повторных финальных контактов: {d['final_overlap']}"))
            if d['truncated']:
                findings.append(dict(code='truncation', severity='warning', index=i, message='Кампания усечена остатком бюджета или контактов'))
            if d['contacts'] == 0:
                findings.append(dict(code='empty', severity='error', index=i, message='Фактическая аудитория пуста'))
            weak = []
            for cell in set(self.cell_keys[self.audience(d['campaign'])]):
                if cell and self.states[self.state_key(cell, d['campaign']['target_tariff'], d['campaign']['channel'])]['samples'] == 0:
                    weak.append(cell)
            if weak:
                findings.append(dict(code='unpiloted', severity='warning', index=i, message='Есть исторические гипотезы без пилотного подтверждения', cells=sorted(weak)))
            uncertain_contacts = 0
            actual_ids = self.audience(d['campaign'])[:d['contacts']]
            for cell in set(self.cell_keys[actual_ids]):
                if cell:
                    mu, sd = self.estimate(cell, d['campaign']['target_tariff'], d['campaign']['channel'])
                    if mu - 1.96 * sd <= 0:
                        uncertain_contacts += int((self.cell_keys[actual_ids] == cell).sum())
            if uncertain_contacts > .25 * max(1, d['contacts']):
                findings.append(dict(code='uncertain_sign', severity='warning', index=i, message='Более четверти контактов зависят от оценки, интервал которой включает ноль'))
        return dict(valid=not any(f['severity'] == 'error' for f in findings), findings=findings, forecast=forecast)

    def passports(self, plan, constraints=None):
        forecasts = self.forecast(plan, constraints)['details']
        result = []
        for i, campaign in enumerate(plan):
            cells = sorted(set(self.cell_keys[self.audience(campaign)]) - {''})
            evidence = []
            alternatives = []
            for cell in cells:
                state = self.states[self.state_key(cell, campaign['target_tariff'], campaign['channel'])]
                mu, sd = self.estimate(cell, campaign['target_tariff'], campaign['channel'])
                evidence.append(dict(state, cell=cell, channel_mean=mu, sd=sd, interval=[mu - 1.96*sd, mu + 1.96*sd]))
            for target in self.tariffs:
                if target == campaign['target_tariff'] or any(self.cells[x]['current'] == target for x in cells):
                    continue
                alt = dict(campaign, target_tariff=target)
                alternative_plan = plan[:i] + [alt] + plan[i+1:]
                alternatives.append(dict(target=target, channel=alt['channel'], plan_net=self.forecast(alternative_plan, constraints)['net']))
            alternatives.sort(key=lambda x: (-x['plan_net'], x['target']))
            best_alt = alternatives[0] if alternatives else None
            result.append(dict(index=i, campaign=campaign, forecast=forecasts[i], evidence=evidence,
                               pilots=[p['index'] for p in self.log if p['cell'] in cells and p['campaign']['target_tariff'] == campaign['target_tariff'] and self.state_key(p['cell'], campaign['target_tariff'], p['campaign']['channel']) == self.state_key(p['cell'], campaign['target_tariff'], campaign['channel'])],
                               status='Проверено пилотом' if evidence and all(e['samples'] > 0 for e in evidence) else 'Историческая гипотеза',
                               best_rejected_alternative=best_alt,
                               rejection_reason='Сравнение замены в той же позиции с учётом всего плана; solver использует штраф за неопределённость.',
                               could_change='Новые наблюдения, сдвиг эффекта или другие ограничения ресурсов могут изменить выбор.',
                               uncertainty_label='Normal posterior interval; calibration under audience shift not guaranteed'))
        return result

    def snapshot(self):
        record = dict(version=1, profile_hash=fingerprint(self.profile), tariffs=self.tariffs, channels=self.channels,
                      total_budget=self.total_budget, total_contacts=self.total_contacts, spent_budget=self.spent_budget,
                      spent_contacts=self.spent_contacts, prior_floor=self.prior_floor, states=self.states, pilots=self.log,
                      diagnostics=self.diagnostics, stop_reason=self.stop_reason,
                      assumptions=['History is a weak non-causal prior; adoption is a heuristic. A first pilot with >3 predictive-sigma conflict inflates prior variance.',
                                   'For multiplier <= 1, transfer assumes base conversion in [0,1]. Calls are independent.',
                                   'Pilot inclusion is independent uniform sampling; no sampled IDs are available.',
                                   'Greedy + bounded local search is not a global optimum; risk penalty is a hyperparameter.'])
        record['snapshot_id'] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
        return record

    @classmethod
    def from_snapshot(cls, profile, tariffs, snapshot):
        engine = cls(profile, tariffs, snapshot['channels'], snapshot['total_budget'], snapshot['total_contacts'], prior_floor=snapshot['prior_floor'])
        if fingerprint(engine.profile) != snapshot['profile_hash']:
            raise ValueError('Снимок относится к другой версии аудитории')
        engine.states = json.loads(json.dumps(snapshot['states']))
        engine.log = json.loads(json.dumps(snapshot['pilots']))
        engine.spent_budget, engine.spent_contacts = snapshot['spent_budget'], snapshot['spent_contacts']
        engine.stop_reason = snapshot['stop_reason']
        return engine


class Agent:
    def __init__(self, policy='adaptive', report_path=None, prior_floor=.24, history_path=None):
        if policy not in ('adaptive', 'history_only', 'fixed_pilots'):
            raise ValueError('Unknown policy')
        self.policy, self.report_path, self.prior_floor = policy, report_path, prior_floor
        self.history_path = history_path

    def act(self, env):
        # Every call creates entirely fresh knowledge, independent of previous runs.
        self.engine = Engine(env.customer_profile, env.tariffs, env.channels,
                             env.remaining_budget, env.remaining_contacts, history_path=self.history_path, prior_floor=self.prior_floor)
        engine = self.engine
        if self.policy != 'history_only':
            fixed = None
            if self.policy == 'fixed_pilots':
                fixed = []
                for cellkey, cell in engine.cells.items():
                    for target in engine.tariffs:
                        if target == cell['current']:
                            continue
                        channel = min(engine.channels, key=lambda ch: abs(engine.channels[ch]['conversion_multiplier'] - .65))
                        mu, _ = engine.estimate(cellkey, target, channel)
                        fixed.append(dict(cell=cellkey, target=target, channel=channel, requested_n=100,
                                          key=engine.state_key(cellkey, target, channel), value=cell['arpu_sum'] * mu))
                fixed.sort(key=lambda x: (-x['value'], x['key']))
            for step in range(min(20, env.pilots_left)):
                choice = fixed[step] if fixed and step < min(12, len(fixed)) else (None if fixed is not None else engine.next_pilot(env.remaining_budget, env.remaining_contacts))
                if choice is None:
                    engine.stop_reason = 'Ожидаемая ценность информации не покрывает расход ресурсов'
                    break
                before = dict(budget=float(env.remaining_budget), contacts=int(env.remaining_contacts))
                try:
                    result = env.run_pilot(**engine.campaign(choice['cell'], choice['target'], choice['channel']), n_customers=choice['requested_n'])
                except (RuntimeError, ValueError) as error:
                    engine.stop_reason = 'Публичный интерфейс отклонил пилот: ' + str(error)
                    break
                after = dict(budget=float(env.remaining_budget), contacts=int(env.remaining_contacts))
                engine.observe(choice, result, before, after)
            else:
                engine.stop_reason = 'Достигнут лимит пилотов'
        else:
            engine.stop_reason = 'History-only ablation: no pilots'
        self.plan = engine.solve()
        self.snapshot = engine.snapshot()
        self.manifest = dict(snapshot_id=self.snapshot['snapshot_id'], plan=self.plan,
                             forecast=engine.forecast(self.plan), audit=engine.audit(self.plan))
        # Reporting must never determine or prevent the returned official plan.
        destination = Path(self.report_path) if self.report_path else ROOT / 'reports/levra/latest_snapshot.json'
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(dict(knowledge=self.snapshot, manifest=self.manifest), ensure_ascii=False, indent=2))
        except OSError:
            pass
        return self.plan
