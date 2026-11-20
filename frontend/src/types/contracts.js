/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,code:string,name:string,teams:string[]}} Roadway */
/** @typedef {{id:number,shift:string,closure_limit:number}} ShiftQuota */
/** @typedef {{id:number,name:string,shift_id:number,threshold:number,status:'draft'|'confirming'|'confirmed',snapshot:Object,confirmed_at:number|null}} SchedulePlan */
export {};
