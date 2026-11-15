import type { CSSProperties } from 'react';
const paths:Record<string,string>={
 home:'m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',
 companies:'M3 21h18M5 21V6h9v15M14 10h5v11M8 9h3M8 13h3M8 17h3M16 13h1M16 17h1',
 reports:'M14 2H5a1 1 0 0 0-1 1v18a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1V8ZM14 2v6h6M8 12h8M8 16h8',
 search:'m21 21-5-5M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0',
 compare:'M4 7h16m-4-4 4 4-4 4M20 17H4m4-4-4 4 4 4',
 dashboard:'M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3ZM14 14h7v7h-7Z',
 alerts:'M12 3 2 21h20ZM12 9v5M12 17v1',
 review:'M9 12l2 2 4-4M9 3H5v18h14V3h-4M9 2h6v4H9Z',
 evals:'M4 20h17M7 16v-5M12 16V4M17 16V8',
 data:'M20 6c0 2-16 2-16 0s16-2 16 0v12c0 2-16 2-16 0V6M4 12c0 2 16 2 16 0',
 settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2',
 menu:'M3 6h18M3 12h18M3 18h18',close:'m6 6 12 12M18 6 6 18',arrow:'M4 12h16m-6-6 6 6-6 6',
 shield:'m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6ZM8 12l3 3 5-6',
};
export function PortalIcon({name,size=20,style}:{name:string;size?:number;style?:CSSProperties}){return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false" style={style}><path d={paths[name]??paths.reports}/></svg>;}
