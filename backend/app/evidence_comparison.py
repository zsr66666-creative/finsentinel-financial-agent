"""Opt-in arithmetic on caller-verified structured evidence, not text entailment.

The caller must verify source values, units, periods and scope before calling.
No natural-language extraction, forecasting or production integration is provided.
"""
from datetime import date
from decimal import Decimal, InvalidOperation


def compare_evidence(current, previous, *, relation):
    rejected = dict(status='needs_review', claim_true=None, evidence_ids=[],
                    reason='unsupported_or_incompatible_evidence')
    relations = {'greater', 'less', 'equal', 'not_greater', 'not_less', 'not_equal'}
    if relation not in relations:
        return rejected
    try:
        for field in ('company', 'metric', 'unit', 'scope'):
            if not current[field] or current[field] != previous[field]:
                return rejected
        if current['scope'] not in ('parent', 'consolidated'):
            return rejected
        if date.fromisoformat(previous['period']) >= date.fromisoformat(current['period']):
            return rejected
        ids = []
        for item in (current, previous):
            source_ids = item['evidence_ids']
            if not isinstance(source_ids, list) or not source_ids or any(
                not isinstance(i, str) or not i.strip() for i in source_ids
            ):
                return rejected
            ids.extend(source_ids)
        a, b = Decimal(str(current['value'])), Decimal(str(previous['value']))
        if not a.is_finite() or not b.is_finite():
            return rejected
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return rejected
    truth = {'greater': a > b, 'less': a < b, 'equal': a == b,
             'not_greater': a <= b, 'not_less': a >= b, 'not_equal': a != b}
    return dict(status='supported', claim_true=truth[relation],
                difference=str(a-b), unit=current['unit'],
                evidence_ids=list(dict.fromkeys(ids)))
