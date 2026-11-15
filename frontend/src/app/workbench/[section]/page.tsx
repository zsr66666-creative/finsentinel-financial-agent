import { notFound } from 'next/navigation';
import { LegacyWorkbench } from '@/components/legacy-workbench';
import { workbenchView } from '@/lib/portal.mjs';
export default async function WorkbenchSection({params}:{params:Promise<{section:string}>}){
 const {section}=await params;const view=workbenchView(section);if(!view)notFound();
 return <LegacyWorkbench key={view} initialView={view}/>;
}
