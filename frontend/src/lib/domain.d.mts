export function normalizeCollection(payload: unknown, key?: string): any[];
export function normalizeAlert(row: any): any;
export function filterAlerts(rows: any[], filters: { query?: string; company?: string; severity?: string; status?: string }): any[];
export function formatMetric(value: unknown, unit?: string): string;
