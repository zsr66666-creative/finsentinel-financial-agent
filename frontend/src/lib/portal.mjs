export function workbenchView(section) {
  return section === undefined ? 'overview' : ['alerts','companies','review','evals','data'].includes(section) ? section : null;
}
function distinctScopes(scopes) { return Array.from(new Map(scopes.map(s=>[JSON.stringify([s.company_code,s.period]),s])).values()); }
export function catalogReports(scopes) {
  const documents=new Map();
  for(const scope of distinctScopes(scopes)) for(const doc of scope.documents) {
    const key=JSON.stringify([scope.company_code,scope.period,doc.document_id,doc.document_sha256]);
    if(!documents.has(key))documents.set(key,{...doc,company_code:scope.company_code,company_name:scope.company_name,industry:scope.industry??'待标注',period:scope.period});
  }
  return Array.from(documents.values());
}
export function catalogCompanies(scopes) {
  const companies=new Map();
  for(const scope of distinctScopes(scopes)) {
    const company=companies.get(scope.company_code)??{company_code:scope.company_code,company_name:scope.company_name,industry:scope.industry??'待标注',periods:[],chunk_count:0,report_count:0};
    company.periods.push(scope.period);company.chunk_count+=scope.chunk_count;company.report_count+=scope.documents.length;
    companies.set(scope.company_code,company);
  }
  return Array.from(companies.values());
}
export function catalogSummary(scopes) {
  const items=distinctScopes(scopes);
  return {companies:catalogCompanies(items).length,reports:catalogReports(items).length,chunks:items.reduce((n,s)=>n+s.chunk_count,0)};
}
export function filterCompanies(companies, industry='all', query='') {
  const term=query.trim().toLocaleLowerCase();
  return companies.filter(c=>(industry==='all'||c.industry===industry)&&(!term||`${c.company_name} ${c.company_code} ${c.industry}`.toLocaleLowerCase().includes(term)));
}
export function chooseCompany(companies, query) {
  const term=query.trim();if(!term)return null;
  const exact=companies.find(c=>c.company_code===term||c.company_name===term);
  const matches=filterCompanies(companies,'all',term);
  return exact??(matches.length===1?matches[0]:null);
}
export function evidenceContext(scopes, company, period) {
  return scopes.some(s=>s.company_code===company&&s.period===period)?{companyCode:company,period}:null;
}
