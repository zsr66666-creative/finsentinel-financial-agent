"""Source-fresh research exports. Monetary strings are never converted through float."""
from datetime import datetime, timezone
import html
import json
import re
from app.financial_reviews import review_state
from app.verified_financials import load_contracts


def safe_text(value):
    value = html.escape(str(value), quote=True)
    value = re.sub(r'[\r\n\t]+', ' ', value)
    return re.sub(r'([\\`*_{}\[\]()#+!|>~])', r'\\\1', value)


def export_research(engine, comparison, format='json'):
    if format not in ('json', 'markdown'): raise ValueError('unsupported export format')
    states = {r['metric']: r for r in review_state(engine, comparison)['items']}
    # Export only the current matching decision; historical snapshots remain in history API.
    items = []
    for metric in comparison['items']:
        state = states[metric['metric']]
        review = {k:state[k] for k in ('fingerprint','review_status','latest')}
        if review['latest']:
            review['latest'] = {k:v for k,v in review['latest'].items() if k != 'snapshot'}
        items.append(dict(metric, review=review))
    company_name = next((r['company_name'] for r in load_contracts() if r['company_code']==comparison['company_code']), comparison['company_code'])
    report = dict(company_name=company_name, schema_version='finsentinel-research-v1', exported_at=datetime.now(timezone.utc).isoformat(),
        **{k:comparison[k] for k in ('company_code','period','statement_scope','status','data_mode')},
        items=items, limitations=['来源校验不等于人工复核；账号署名仅表示系统登录身份，历史自报署名不追认为真实账号。',
        '增加或减少不构成风险或投资结论。', '仅覆盖六个固定指标契约；历史决策不会继承到变更后的来源。',
        'rejected 表示人工驳回，所列金额仅保留为被审阅的来源值，不代表认可。'])
    if comparison.get('reason'): report['reason'] = comparison['reason']
    if format == 'json': return json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    lines = ['# FinSentinel 财务证据研究报告', '',
        f"公司：{safe_text(report['company_name'])} / 代码：{safe_text(report['company_code'])} / 报告期：{safe_text(report['period'])} / 口径：{safe_text(report['statement_scope'])}",
        f"导出时间：{safe_text(report['exported_at'])}", '', '## 适用边界', *['- '+safe_text(v) for v in report['limitations']], '']
    if report.get('reason'): lines += ['待复核原因：'+safe_text(report['reason']), '']
    for item in items:
        state = item['review']; latest = state['latest']
        lines += ['## '+safe_text(item['label']), '来源状态：'+safe_text(item['status']),
                  '人工复核：'+safe_text(state['review_status'])]
        if latest:
            if latest.get('identity_assurance') == 'authenticated_user':
                lines += ['账号署名：'+safe_text(latest['reviewer'])+' / '+safe_text(latest['username']),
                          '用户 ID：'+safe_text(latest['user_id'])]
            else:
                lines += ['历史自报署名：'+safe_text(latest['reviewer'])]
            lines += ['意见：'+safe_text(latest['reason']),
                      '复核时间：'+safe_text(latest['created_at']), '记录 ID：'+safe_text(latest['id'])]
        if item['status'] != 'supported':
            lines += ['证据不足，不展示数值。原因：'+safe_text(item.get('reason','unknown')), ''];continue
        for label,key in [('本期原始期间','current_period'),('比较期原始期间','previous_period'),('本期原列名','current_column'),('比较期原列名','previous_column'),('单位','unit'),('本期金额','current_value'),('比较期金额','previous_value'),('差额','difference'),('变化率 %','change_percent'),('来源 URL','source_url'),('PDF SHA-256','source_sha256')]:
            lines.append(label+'：'+safe_text(item.get(key) if item.get(key) is not None else '不适用（比较基数为零）'))
        lines += ['计算方式：(本期 − 比较期) ÷ |比较期| × 100%，两位小数。', '快照指纹：'+safe_text(state['fingerprint']), '', '### 原文定位']
        for proof in item['evidence']:
            lines += [f"- 物理页 {proof['page']} / {safe_text(proof['role'])} / {safe_text(proof['evidence_id'])}",
                '  原文：'+safe_text(proof['text']), '  文本 SHA-256：'+safe_text(proof['text_sha256']),
                '  页面文本 SHA-256：'+safe_text(proof['page_text_sha256'])]
        lines.append('')
    return '\n'.join(lines)+'\n'
