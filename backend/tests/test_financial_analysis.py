from decimal import Decimal

import pytest

from app.financial_analysis import analyze_pair, calc_cash_profit_ratio, calc_yoy, classify_divergence


def verified(metric, value, period, evidence_id, page):
    return {
        'id': f'{period}-{metric}', 'company_id': '000100', 'metric': metric,
        'value': str(value), 'period': period, 'unit': 'CNY',
        'statement_scope': 'consolidated', 'document_sha256': 'a' * 64,
        'page': page, 'excerpt': f'verified {metric}', 'extraction_status': 'human_verified',
        'evidence_id': evidence_id,
    }


def test_yoy_uses_decimal_and_absolute_prior_value():
    assert calc_yoy(Decimal('120'), Decimal('-100')) == Decimal('220')


def test_zero_prior_denominator_is_not_defined():
    with pytest.raises(ValueError, match='zero'):
        calc_yoy(Decimal('10'), Decimal('0'))


def test_cash_profit_ratio_rejects_zero_profit():
    with pytest.raises(ValueError, match='zero'):
        calc_cash_profit_ratio(Decimal('10'), Decimal('0'))


@pytest.mark.parametrize(('profit', 'cash', 'expected'), [
    ('0', '0', '同步改善'), ('-1', '-1', '同步恶化'),
    ('1', '-1', '利润增长但现金流恶化'), ('-1', '1', '利润恶化但现金流改善'),
])
def test_classifies_profit_cashflow_divergence(profit, cash, expected):
    assert classify_divergence(Decimal(profit), Decimal(cash)) == expected


def test_analysis_binds_inputs_to_evidence_pages():
    result = analyze_pair(
        verified('net_profit', 120, '2024FY', 'p24', 80),
        verified('net_profit', 150, '2025FY', 'p25', 82),
        verified('operating_cash_flow', 100, '2024FY', 'c24', 91),
        verified('operating_cash_flow', 80, '2025FY', 'c25', 93),
    )
    assert result['status'] == 'completed'
    assert result['classification'] == '利润增长但现金流恶化'
    assert Decimal(result['metrics']['net_profit_yoy']['value']) == Decimal('25')
    assert Decimal(result['metrics']['operating_cash_flow_yoy']['value']) == Decimal('-20')
    assert {item['page'] for item in result['evidence']} == {80, 82, 91, 93}
    assert result['metrics']['net_profit_yoy']['input_ids'] == ['2024FY-net_profit', '2025FY-net_profit']


def test_unverified_input_degrades_to_needs_review():
    inputs = [verified('net_profit', 120, '2024FY', 'p24', 80),
              verified('net_profit', 150, '2025FY', 'p25', 82),
              verified('operating_cash_flow', 100, '2024FY', 'c24', 91),
              verified('operating_cash_flow', 80, '2025FY', 'c25', 93)]
    inputs[-1]['extraction_status'] = 'machine_extracted'
    result = analyze_pair(*inputs)
    assert result['status'] == 'needs_review'
    assert result['classification'] == '无法判断'


def test_mixed_units_degrade_to_needs_review():
    inputs = [verified('net_profit', 120, '2024FY', 'p24', 80),
              verified('net_profit', 150, '2025FY', 'p25', 82),
              verified('operating_cash_flow', 100, '2024FY', 'c24', 91),
              verified('operating_cash_flow', 80, '2025FY', 'c25', 93)]
    inputs[-1]['unit'] = 'CNY_thousand'
    assert analyze_pair(*inputs)['status'] == 'needs_review'
