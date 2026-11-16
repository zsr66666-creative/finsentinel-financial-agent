export type OperationStatus = 'ok'|'warning'|'critical'|'unknown';
export type OperationCheck = {id:string;label:string;status:OperationStatus;reason:string;checked_at:string;duration_ms:number;last_success_at?:string;expires_at?:string;free_bytes?:number;total_bytes?:number};
export type OperationHistory = {at:string;check_id:string;status:OperationStatus;reason:string};
export type Operations = {schema_version:1;checked_at:string;status:OperationStatus;checks:OperationCheck[];history:OperationHistory[];stale:boolean};
export function parseOperations(value:unknown, now?:number):Operations;
export function groupStatus(checks:{status:OperationStatus}[]):OperationStatus;
