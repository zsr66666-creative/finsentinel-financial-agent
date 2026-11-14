import { CompanyResearch } from '@/components/company-research';
export default async function CompanyPage({ params }: { params: Promise<{ companyId: string }> }) {
  const { companyId } = await params;
  return <CompanyResearch companyId={companyId} />;
}
