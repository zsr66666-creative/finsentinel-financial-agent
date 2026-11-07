export function riskCategory(row: Record<string, unknown> = {}) {
  const text = `${row.category ?? ''} ${row.title ?? ''} ${row.rule ?? ''}`;
  if (/现金|营运|存货|应收|回款|经营/.test(text)) return '营运与现金流质量';
  if (/盈利|业绩|毛利|利润|收入/.test(text)) return '业绩与盈利能力';
  if (/公告|事件|客户|诉讼|担保|回购|关联/.test(text)) return '重大公告事件';
  return '其他待跟踪事项';
}

export const workflowStages = [
  { id: 'Planner', label: '任务规划' },
  { id: 'DataQuality', label: '数据质量' },
  { id: 'Retriever', label: '混合检索' },
  { id: 'QuantAnalyst', label: '指标计算' },
  { id: 'EvidenceVerifier', label: '证据复核' },
  { id: 'ReportComposer', label: '报告生成' },
] as const;
