export function setCsrfToken(value:string):void;
export function authFetch(path:string,init?:RequestInit):Promise<Response>;
export function accountRequest(path:string,body?:unknown):Promise<any>;
export function secureAccountOrigin(location:{protocol:string;hostname:string}):boolean;
