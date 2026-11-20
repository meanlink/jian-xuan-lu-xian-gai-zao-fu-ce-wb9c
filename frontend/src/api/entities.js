import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
export const scheduling={
 roadways:()=>api('/scheduling/roadways'),
 registerRoadway:data=>api('/scheduling/roadways',{method:'POST',body:JSON.stringify(data)}),
 quotas:()=>api('/scheduling/quotas'),
 upsertQuota:data=>api('/scheduling/quotas',{method:'POST',body:JSON.stringify(data)}),
 draftPreview:data=>api('/scheduling/draft-preview',{method:'POST',body:JSON.stringify(data)}),
 plans:()=>api('/scheduling/plans'),
 createPlan:data=>api('/scheduling/plans',{method:'POST',body:JSON.stringify(data)}),
 plan:id=>api('/scheduling/plans/'+id),
 confirm:id=>api('/scheduling/plans/'+id+'/confirm',{method:'POST'}),
 replan:id=>api('/scheduling/plans/'+id+'/replan',{method:'POST'}),
 closureStatus:()=>api('/scheduling/closure-status'),
};
