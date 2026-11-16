import type { FinancialComparison, FinancialMetric } from './verified-financials.mjs';
export type ReviewRecord={id:string;company_code:string;period:string;statement_scope:string;metric:string;fingerprint:string;decision:'confirmed'|'rejected'|'needs_evidence';reason:string;reviewer:string;created_at:string;identity_assurance:'self_declared_operator'|'authenticated_user';snapshot:FinancialMetric;previous_review_id:string|null};
export type ReviewItem={metric:string;fingerprint:string|null;snapshot:FinancialMetric|null;review_status:string;latest:ReviewRecord|null;history:ReviewRecord[]};
export type ReviewState={company_code:string;period:string;statement_scope:string;identity_assurance:string;items:ReviewItem[]};
export function parseReviewState(body:unknown,comparison:FinancialComparison):ReviewState;
export function reviewStatusText(status:string):string;
