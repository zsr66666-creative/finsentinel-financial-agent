export type Favorite={id:string;kind:'company'|'evidence';company_code:string;period?:string|null;chunk_id?:string|null;note:string;snapshot:Record<string,unknown>;created_at:number;updated_at:number};
export type HistoryEntry={id:string;kind:'search'|'compare';query:string;company_code?:string|null;period?:string|null;created_at:number};
export function queryPrefill(value:unknown):string;
export function historyPayload(value:Record<string,unknown>):Record<string,string>;
export function reopenHref(value:Record<string,unknown>):string|null;
export function parseResearchPage(value:unknown,collection:'favorites'): {items:Favorite[];total:number};
export function parseResearchPage(value:unknown,collection:'history'): {items:HistoryEntry[];total:number};
export function researchRequest(path:string,init?:RequestInit):Promise<any>;
export function researchWrite(path:string,body?:unknown,method?:string,signal?:AbortSignal):Promise<any>;
