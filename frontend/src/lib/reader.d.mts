export type ReaderLocator = {chunk_id?:unknown;document_sha256?:unknown;company_code?:unknown;period?:unknown;page?:unknown};
export type ReaderMetadata = {document_sha256:string;document_id:string;company_code:string;period:string;page:number;page_count:number;text:string;source_status:string;source_url:string|null;pdf_url:string};
export function readerLocator(value:ReaderLocator):URLSearchParams|null;
export function readerHref(value:ReaderLocator):string|null;
export function parseReaderQuery(params:URLSearchParams):URLSearchParams|null;
export function parseReaderMetadata(body:unknown,locator:URLSearchParams):ReaderMetadata;
