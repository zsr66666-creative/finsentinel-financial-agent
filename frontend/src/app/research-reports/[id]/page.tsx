import {SavedReportDetail} from '@/components/saved-reports';
export default async function Page({params}:{params:Promise<{id:string}>}){const {id}=await params;return <SavedReportDetail key={id} id={id}/>;}
