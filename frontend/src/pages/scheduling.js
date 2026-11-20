import {scheduling} from '../api/entities.js';
import {session} from '../stores/session.js';
import {heading} from '../components/common/shell.js';
import {esc,date,notify,fmt} from '../utils/dom.js';
import {submit} from '../hooks/forms.js';

const canWrite=()=>session.user.role!=='viewer';
const isAdmin=()=>session.user.role==='admin';
const STATUS={draft:'草案 · 不占额度',confirming:'确认中断 · 可恢复',confirmed:'已确认 · 已占额度'};

function clusterCard(cl,kind){
 const badge=kind==='selected'?'入选':(kind==='rejected'?'落选 · 同退':'额度不足 · 暂缓');
 const cls=kind==='selected'?'ok':(kind==='rejected'?'bad':'hold');
 return '<article class="sched-cluster '+cls+'"><header><span class="cluster-badge">'+esc(badge)+'</span><strong>'+esc(cl.cluster_id)+'</strong><small>巷道 '+cl.roadway_count+' 条 · 覆盖 '+cl.operators+' 人</small></header>'
  +'<div class="cluster-roadways">'+cl.roadways.map(r=>'<span class="tag">'+esc(r.code)+'</span>').join('')+'</div>'
  +'<table class="reason-table"><thead><tr><th>小组</th><th>是否合格</th><th>依据</th><th>区间下界(秒)</th><th>人数</th></tr></thead><tbody>'
  +cl.team_results.map(t=>'<tr class="'+(t.eligible?'eligible':'ineligible')+'"><td>'+esc(t.team)+'</td><td>'+(t.eligible?'达标':'未达标')+'</td><td>'+esc(t.reason)+'</td><td>'+(t.ci_lower==null?'—':fmt(t.ci_lower))+'</td><td>'+t.operators+'</td></tr>').join('')
  +'</tbody></table>'+(cl.skip_reason?'<p class="skip-reason">'+esc(cl.skip_reason)+'</p>':'')+'</article>';
}

function snapshotView(snap){
 if(!snap||!snap.all_clusters)return '<p class="empty">暂无选包结果。</p>';
 const groups=[['selected','入选巷道组（同进同退）'],['rejected','落选巷道组（一组不合格全组同退）'],['skipped_quota','限额内暂缓的合格组']];
 return '<div class="sched-summary"><div><span>封道上限</span><strong>'+snap.closure_limit+' 条</strong></div>'
  +'<div><span>本单占用</span><strong>'+snap.closures_used+' 条</strong></div><div><span>剩余额度</span><strong>'+snap.closures_remaining+' 条</strong></div>'
  +'<div><span>覆盖作业员</span><strong>'+snap.operators_covered+' 人</strong></div><div><span>改善门槛(下界)</span><strong>'+fmt(snap.threshold)+' 秒</strong></div></div>'
  +groups.map(([k,title])=>snap[k].length?'<section class="panel sched-section"><div class="section-title"><h2>'+esc(title)+'</h2><span>'+snap[k].length+' 组</span></div><div class="cluster-grid">'+snap[k].map(c=>clusterCard(c,k)).join('')+'</div></section>':'').join('');
}

export async function schedulePage(){
 const [roadways,quotas,plans,status]=await Promise.all([
   scheduling.roadways(),scheduling.quotas(),scheduling.plans(),scheduling.closureStatus()]);
 const shiftOptions=quotas.map(q=>'<option value="'+q.id+'">'+esc(q.shift)+'（封道上限 '+q.closure_limit+' 条）</option>').join('');
 return heading('06 / SHIFT SCHEDULING','扩测排班与封道额度','登记每班封道上限与各组必经巷道；只用已批准且改善区间下界达标的小组复测结果排班，同巷道组同进同退。草案不占额度，确认时整单占用。')
 +'<div class="sched-grid">'
 // 左：登记
 +'<section class="panel"><div class="section-title"><h2>巷道与额度登记</h2></div>'
 +'<form id="roadway-form"><label>巷道编号<input name="code" required maxlength="40" placeholder="RW-D1"></label><label>巷道名称<input name="name" maxlength="120" placeholder="东翼主运巷"></label>'
 +'<label>必经小组（逗号分隔，同巷组同进同退）<input name="teams" required placeholder="一组,三组"></label><button type="submit" class="primary" '+(canWrite()?'':'disabled')+'>登记必经巷道</button></form>'
 +'<form id="quota-form" class="quota-form"><label>班次<input name="shift" required placeholder="早班"></label><label>每班封道上限（条）<input name="closure_limit" type="number" min="0" max="1000" value="3" required></label><button type="submit" '+(isAdmin()?'':'disabled')+'>保存班次额度</button></form>'
 +'<div class="registered"><h3>已登记巷道</h3>'+(roadways.length?roadways.map(r=>'<div class="reg-row"><strong>'+esc(r.code)+'</strong><span>'+esc(r.name)+'</span><small>'+r.teams.map(esc).join(' / ')+'</small></div>').join(''):'<p class="empty">尚未登记巷道。</p>')+'</div></section>'
 // 右：排班
 +'<section class="panel"><div class="section-title"><h2>生成排班草案</h2><span>不占用封道额度</span></div>'
 +'<form id="plan-form"><div class="parameter-grid"><label>班次<select name="shift_id" required>'+(shiftOptions||'<option value="">请先登记班次额度</option>')+'</select></label>'
 +'<label>改善区间下界门槛（秒）<input name="threshold" type="number" step="any" min="0" value="8" required></label></div>'
 +'<div class="form-actions"><button type="button" id="preview-btn" '+(quotas.length?'':'disabled')+'>预览选包依据</button><button type="submit" class="primary" '+(canWrite()&&quotas.length?'':'disabled')+'>保存为草案</button></div></form>'
 +'<div id="draft-preview"></div></section></div>'
 // 额度台账
 +'<section class="panel"><div class="section-title"><h2>各班封道额度台账</h2><button class="button small" id="refresh-sched">刷新 ↻</button></div><div class="quota-status">'+(status.length?status.map(s=>'<div class="quota-card"><strong>'+esc(s.shift)+'</strong><div class="quota-bar"><span style="width:'+(s.closure_limit?Math.round(100*s.used/s.closure_limit):0)+'%"></span></div><small>'+s.used+' / '+s.closure_limit+' 条已用 · 剩余 '+s.remaining+'</small><div class="closure-list">'+s.closures.map(c=>'<span class="tag">'+esc(c.roadway_code)+' · '+esc(c.team)+' · 单#'+c.plan_id+'</span>').join('')+'</div></div>').join(''):'<p class="empty">暂无班次额度。</p>')+'</div></section>'
 // 排班单
 +'<section class="panel"><div class="section-title"><h2>排班单与入选/落选依据</h2><span>'+plans.length+' 张</span></div><div class="plan-list">'+(plans.length?plans.map(p=>'<article class="plan-card status-'+esc(p.status)+'"><header><div><strong>'+esc(p.name)+'</strong><p>'+esc(p.snapshot?.shift?.shift||'')+' · 门槛 '+fmt(p.threshold)+' 秒 · 创建 '+date(p.created_at)+'</p></div><span class="plan-status">'+esc(STATUS[p.status]||p.status)+'</span></header>'
   +'<div class="plan-actions"><button class="button small" data-view="'+p.id+'">查看选包依据</button>'
   +(p.status==='draft'?'<button class="primary small" data-confirm="'+p.id+'" '+(isAdmin()?'':'disabled')+'>确认并整单占额</button><button class="button small" data-replan="'+p.id+'" '+(canWrite()?'':'disabled')+'>按剩余额度重排</button>':'')
   +(p.status==='confirming'?'<button class="primary small" data-confirm="'+p.id+'" '+(isAdmin()?'':'disabled')+'>恢复确认（不重复占额）</button>':'')
   +'</div><div class="plan-detail" id="plan-detail-'+p.id+'" hidden>'+snapshotView(p.snapshot)+'</div></article>').join(''):'<p class="empty">尚无排班单。先生成一张草案。</p>')+'</div></section>';
}

export function bindSchedule(refresh){
 document.querySelector('#refresh-sched').onclick=refresh;
 const rwForm=document.querySelector('#roadway-form');
 if(rwForm)submit(rwForm,async f=>{
   const teams=f.get('teams').split(/[,，]/).map(s=>s.trim()).filter(Boolean);
   await scheduling.registerRoadway({code:f.get('code'),name:f.get('name'),teams});
   notify('必经巷道已登记');await refresh();
 });
 const qForm=document.querySelector('#quota-form');
 if(qForm)submit(qForm,async f=>{await scheduling.upsertQuota({shift:f.get('shift'),closure_limit:Number(f.get('closure_limit'))});notify('班次封道额度已保存');await refresh();});
 const planForm=document.querySelector('#plan-form');
 if(planForm){
   const payload=()=>({shift_id:Number(new FormData(planForm).get('shift_id')),threshold:Number(new FormData(planForm).get('threshold'))});
   document.querySelector('#preview-btn').onclick=async()=>{
     try{const snap=await scheduling.draftPreview(payload());document.querySelector('#draft-preview').innerHTML=snapshotView(snap);notify('已生成选包预览（未保存、未占额度）');}
     catch(e){notify(e.message,true);}
   };
   submit(planForm,async f=>{const p=await scheduling.createPlan({name:'扩测排班 · '+new Date().toLocaleString('zh-CN'),shift_id:Number(f.get('shift_id')),threshold:Number(f.get('threshold'))});notify('草案已保存，未占用封道额度');await refresh();document.querySelector('#plan-detail-'+p.id)&&(document.querySelector('#plan-detail-'+p.id).hidden=false);});
 }
 document.querySelectorAll('[data-view]').forEach(b=>b.onclick=()=>{const el=document.querySelector('#plan-detail-'+b.dataset.view);if(el)el.hidden=!el.hidden;});
 document.querySelectorAll('[data-confirm]').forEach(b=>b.onclick=async()=>{
   try{const r=await scheduling.confirm(b.dataset.confirm);notify(r.confirm_outcome==='already_confirmed'?'该单已确认，未重复占用额度':'确认成功，封道额度已整单占用');await refresh();}
   catch(e){notify(e.message+(e.message.includes('重排')?'':'（如额度变化请使用“按剩余额度重排”）'),true);}
 });
 document.querySelectorAll('[data-replan]').forEach(b=>b.onclick=async()=>{try{await scheduling.replan(b.dataset.replan);notify('已按当前剩余额度重排为新草案，可再次确认');await refresh();}catch(e){notify(e.message,true);}});
}
