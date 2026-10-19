import type {Capabilities,Run,Report,ApiPlan,ParsedContract,WebPlan} from './types';
const PREFIX='/api';
export class ApiError extends Error{constructor(message:string,public status:number){super(message);}}
export async function request<T>(path:string,options:RequestInit={},token=''):Promise<T>{
 const controller=new AbortController();const deadline=setTimeout(()=>controller.abort(),120000);
 try{
  const response=await fetch(PREFIX+path,{...options,signal:options.signal||controller.signal,headers:{...(options.body instanceof FormData?{}:options.body?{'Content-Type':'application/json'}:{}),...(token?{'X-TestGen-Workspace':token}:{}),...options.headers}});
  if(!response.ok){const body=await response.json().catch(()=>({}));const detail=body.detail;const message=typeof detail==='string'?detail:Array.isArray(detail)?detail.map((item:{msg?:string})=>item.msg||'Invalid input').join('; '):`Request failed (${response.status}). Please retry.`;throw new ApiError(message,response.status);}
  return response.json();
 }catch(e){if(e instanceof ApiError)throw e;throw new Error(e instanceof DOMException&&e.name==='AbortError'?'The request timed out. Check Run History before submitting again.':'Cannot reach the backend. Check that the API is running and retry.');}finally{clearTimeout(deadline);}
}
export const post=<T,>(path:string,body:unknown,token='')=>request<T>(path,{method:'POST',body:JSON.stringify(body)},token);
export const capabilities=()=>request<Capabilities>('/capabilities');
export const createWorkspace=()=>post<{workspace_token:string}>('/workspaces',{});
export const history=(token:string)=>request<{runs:Run[]}>('/runs',{},token);
export const getRun=(id:string,token:string)=>request<Run>('/runs/'+encodeURIComponent(id),{},token);
export const submitText=(requirement:string,key:string,token:string)=>post<Run>('/runs',{requirement,idempotency_key:key},token);
export function submitDocument(file:File,key:string,token:string){const body=new FormData();body.append('file',file);body.append('idempotency_key',key);return request<Run>('/runs/document',{method:'POST',body},token);}
export const generateDemo=(requirement:string)=>post<Report>('/generate',{requirement});
export function documentDemo(file:File){const body=new FormData();body.append('file',file);return request<Report>('/generate-document',{method:'POST',body});}
export const parseContract=(kind:'spec'|'html',body:unknown)=>post<ParsedContract>(`/api-testing/${kind}/parse`,body);
export const designApi=(kind:string,body:unknown)=>post<{plan:ApiPlan}>(`/api-testing/design/${kind}`,body);
export const generateWeb=(url:string,user_goal:string,inspection_mode:string)=>post<WebPlan>('/web-testing/generate',{url,user_goal,inspection_mode});
export function saveBlob(blob:Blob,filename:string){const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export async function download(path:string,filename:string,body?:unknown,token=''){
 const response=await fetch(PREFIX+path,{method:body===undefined?'GET':'POST',headers:{...(body===undefined?{}:{'Content-Type':'application/json'}),...(token?{'X-TestGen-Workspace':token}:{})},body:body===undefined?undefined:JSON.stringify(body)});
 if(!response.ok){const error=await response.json().catch(()=>({}));throw new ApiError(typeof error.detail==='string'?error.detail:'Download failed. Review the selected cases and try again.',response.status);}
 saveBlob(await response.blob(),filename);
}
export function downloadDemo(report:Report){if(!report.excel_base64)throw new Error('This response contains no workbook.');const bytes=Uint8Array.from(atob(report.excel_base64),char=>char.charCodeAt(0));saveBlob(new Blob([bytes],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}),'TestGen_Output.xlsx');}
