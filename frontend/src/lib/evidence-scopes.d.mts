export type EvidenceScope = {
  company_code: string; company_name: string; industry?: string; market?: string; period: string; chunk_count: number;
  documents: { document_id: string; document_sha256: string; pages: number[]; chunk_count: number;
    total_pages: number | null; coverage_kind: 'selected_pages' | 'indexed_fragments' | 'all_text_pages'; source_statuses: string[] }[];
};
export function parseScopes(body: unknown): EvidenceScope[];
export function selectScope(items: EvidenceScope[], company: string, period: string): EvidenceScope | null;
export function coverageText(scope: EvidenceScope): string;
type Request = { controller: AbortController };
export function createRequestGate(): { begin(): Request; isCurrent(request: Request): boolean; cancel(): void };
export function scopesForCompany(items: EvidenceScope[], companyCode?: string): EvidenceScope[];
export function groupScopedCompanies(items: EvidenceScope[]): { company_code: string; company_name: string; industry: string; chunk_count: number; periods: string[] }[];
