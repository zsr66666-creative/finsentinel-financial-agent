"""Auditable, deterministic calculations for cash flow and profit divergence."""

from decimal import Decimal, InvalidOperation
import re


def _decimal(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('financial value is not a decimal') from exc
    if not number.is_finite():
        raise ValueError('financial value must be finite')
    return number


def calc_yoy(current, previous):
    current, previous = _decimal(current), _decimal(previous)
    if previous == 0:
        raise ValueError('previous value is zero; yoy is undefined')
    return (current - previous) / abs(previous) * Decimal('100')


def calc_cash_profit_ratio(cash_flow, net_profit):
    cash_flow, net_profit = _decimal(cash_flow), _decimal(net_profit)
    if net_profit == 0:
        raise ValueError('net profit is zero; cash-profit ratio is undefined')
    return cash_flow / net_profit


def classify_divergence(net_profit_yoy, cash_flow_yoy):
    profit_up, cash_up = _decimal(net_profit_yoy) >= 0, _decimal(cash_flow_yoy) >= 0
    if profit_up and cash_up:
        return '同步改善'
    if not profit_up and not cash_up:
        return '同步恶化'
    if profit_up:
        return '利润增长但现金流恶化'
    return '利润恶化但现金流改善'


def _period_year(period):
    if not isinstance(period, str) or not period.endswith('FY'):
        raise ValueError('period must use YYYYFY format')
    try:
        return int(period[:-2])
    except ValueError as exc:
        raise ValueError('period must use YYYYFY format') from exc


def _validate_input(record, metric):
    required = ('id', 'company_id', 'period', 'value', 'unit', 'statement_scope',
                'document_sha256', 'page', 'excerpt', 'extraction_status', 'evidence_id')
    missing = [key for key in required if record.get(key) in (None, '')]
    if missing:
        raise ValueError(f'{metric} input missing: {", ".join(missing)}')
    if record['metric'] != metric:
        raise ValueError(f'expected {metric}, got {record["metric"]}')
    if record['extraction_status'] != 'human_verified':
        raise ValueError(f'{metric} input is not human_verified')
    if not isinstance(record['page'], int) or record['page'] < 1:
        raise ValueError(f'{metric} input has invalid physical page')
    if not re.fullmatch(r'[0-9a-fA-F]{64}', str(record['document_sha256'])):
        raise ValueError(f'{metric} input has invalid document SHA256')
    _decimal(record['value'])
    _period_year(record['period'])


def _review(reason, inputs):
    return {
        'status': 'needs_review', 'classification': '无法判断', 'reason': reason,
        'metrics': {}, 'charts': [], 'evidence': _evidence(inputs),
        'formula_version': 'cashflow-profit-v1',
    }


def _evidence(inputs):
    return [{key: item[key] for key in ('evidence_id', 'company_id', 'period', 'metric',
                'document_sha256', 'page', 'excerpt', 'unit', 'statement_scope', 'source_url') if key in item}
            for item in inputs]


def _derived(value, formula, inputs, unit):
    return {'value': str(value), 'unit': unit, 'formula': formula,
            'input_ids': [item['id'] for item in inputs],
            'evidence_ids': [item['evidence_id'] for item in inputs],
            'pages': [item['page'] for item in inputs]}


def calc_verified_cash_profit_ratio(net_profit, cash_flow):
    _validate_input(net_profit, 'net_profit')
    _validate_input(cash_flow, 'operating_cash_flow')
    if net_profit['company_id'] != cash_flow['company_id'] or net_profit['period'] != cash_flow['period']:
        raise ValueError('company or period mismatch in cash-profit ratio inputs')
    if net_profit['statement_scope'] != cash_flow['statement_scope'] or net_profit['unit'] != cash_flow['unit']:
        raise ValueError('unit or statement scope mismatch in cash-profit ratio inputs')
    return calc_cash_profit_ratio(cash_flow['value'], net_profit['value'])


def analyze_pair(net_previous, net_current, cash_previous, cash_current):
    inputs = [net_previous, net_current, cash_previous, cash_current]
    try:
        _validate_input(net_previous, 'net_profit')
        _validate_input(net_current, 'net_profit')
        _validate_input(cash_previous, 'operating_cash_flow')
        _validate_input(cash_current, 'operating_cash_flow')
        records_by_company = {item['company_id'] for item in inputs}
        if len(records_by_company) != 1:
            raise ValueError('company mismatch across financial inputs')
        previous_year, current_year = _period_year(net_previous['period']), _period_year(net_current['period'])
        if current_year != previous_year + 1:
            raise ValueError('periods must be adjacent financial years')
        if cash_previous['period'] != net_previous['period'] or cash_current['period'] != net_current['period']:
            raise ValueError('period mismatch across financial inputs')
        if len({item['statement_scope'] for item in inputs}) != 1:
            raise ValueError('statement scope mismatch')
        if len({item['unit'] for item in inputs}) != 1:
            raise ValueError('unit mismatch across financial inputs')
        net_yoy = calc_yoy(net_current['value'], net_previous['value'])
        cash_yoy = calc_yoy(cash_current['value'], cash_previous['value'])
        ratio = calc_cash_profit_ratio(cash_current['value'], net_current['value'])
    except (KeyError, ValueError) as exc:
        return _review(str(exc), inputs)

    classification = classify_divergence(net_yoy, cash_yoy)
    return {
        'status': 'completed', 'classification': classification, 'reason': None,
        'metrics': {
            'net_profit_yoy': _derived(net_yoy,
                '(current_net_profit - previous_net_profit) / abs(previous_net_profit) * 100',
                [net_previous, net_current], '%'),
            'operating_cash_flow_yoy': _derived(cash_yoy,
                '(current_operating_cash_flow - previous_operating_cash_flow) / abs(previous_operating_cash_flow) * 100',
                [cash_previous, cash_current], '%'),
            'cash_profit_ratio': _derived(ratio,
                'current_operating_cash_flow / current_net_profit', [cash_current, net_current], 'ratio'),
        },
        'charts': [
            {'id': 'yoy-comparison', 'title': '净利润与经营现金流同比变化', 'unit': '%',
             'series': [{'name': '净利润同比', 'value': str(net_yoy), 'evidence_ids': [net_previous['evidence_id'], net_current['evidence_id']]},
                        {'name': '经营现金流同比', 'value': str(cash_yoy), 'evidence_ids': [cash_previous['evidence_id'], cash_current['evidence_id']]}]},
            {'id': 'cash-profit-ratio', 'title': '现金流利润比', 'unit': '倍',
             'series': [{'name': net_current['period'], 'value': str(ratio),
                         'evidence_ids': [cash_current['evidence_id'], net_current['evidence_id']]}]},
        ],
        'evidence': _evidence(inputs), 'formula_version': 'cashflow-profit-v1',
    }
