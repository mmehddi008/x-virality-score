// Harmless renderer check: inspect generated markup without executing injected HTML.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const html = fs.readFileSync(path.join(__dirname, '../board/index.html'), 'utf8');
const script = html.split('<script>')[1].split('</script>')[0];
new vm.Script(script);
const els = {};
const context = vm.createContext({ document: { getElementById(id) { return els[id] ||= {querySelectorAll(){return []}}; } } });
vm.runInContext(script.slice(0, script.lastIndexOf('initTheme();')), context);
vm.runInContext(`renderExp({totals:{trend:{n:1,median_x:'<img src=x onerror="window.auditMarker=1">'}}})`, context);
assert(!els.exp.innerHTML.includes('<img'));
assert.equal(vm.runInContext("safeURL('javascript:alert(1)')",context),'#');
assert.equal(vm.runInContext("safeURL('https://u:p@example.com/')",context),'#');
vm.runInContext('configureTargets({dashboard_targets:{minHitViews:300,starViews:1500}})',context);
assert.equal(vm.runInContext('DASHBOARD_TARGETS.minHitViews',context),300);
assert.equal(vm.runInContext('scoreFor(12,100000)',context),100);
assert.equal(vm.runInContext('scoreFor(0,0)',context),0);
console.log('PASS: JavaScript syntax and score boundaries');
console.log('PASS: injected HTML and unsafe URL schemes blocked; profile thresholds applied');

vm.runInContext(`renderProfile({profile:{name:'Example',accounts:[]},daily_research:{collected_at:'2020-01-01T00:00:00Z',summary:'<img src=x>',source_checks:{source:'sampled'},posts:[{url:'javascript:alert(1)',posted_at:'2020-01-01',views:null,summary:'Sample'}],drafts:[{title:'Draft',text:'Original text',visual:'Diagram',source_urls:[]}]}})`,context);
assert(els.profile.innerHTML.includes('Update overdue'));
assert(els.profile.innerHTML.includes('View counts are unavailable'));
assert(els.profile.innerHTML.includes('Pending approval'));
assert(!els.profile.innerHTML.includes('<img'));
assert(!/[\u0600-\u06ff]/.test(els.profile.innerHTML));
assert.equal(els.analytics.hidden,true);
console.log('PASS: English daily research, pending drafts, overdue status and unknown metrics');

(async()=>{
 const handlers={},fields={};let saved=null;
 const setting={model:'a6api/gpt-6-sol',provider:'Server AI gateway',last_run:{status:'failed',at:'today',error_type:'HTTPError'},last_success:{model:'old/model',at:'yesterday'},pending_change:true};
 context.location={pathname:'/twitter/o2co/'};
 context.document.getElementById=id=>fields[id] ||= {value:'new/model',addEventListener(event,fn){handlers[id+event]=fn;},querySelector(){return {disabled:false}}};
 context.fetch=async(url,options)=>{if(options&&options.method==='PUT'){saved=JSON.parse(options.body);setting.model=saved.model;}return {ok:true,json:async()=>setting}};
 await vm.runInContext('loadAISettings()',context);
 assert(fields['ai-settings'].innerHTML.includes('failed'));
 assert(fields['ai-settings'].innerHTML.includes('awaiting a successful run'));
 await handlers['ai-model-formsubmit']({preventDefault(){},target:fields['ai-model-form']});
 assert.equal(saved.model,'new/model');
 assert(fields['ai-save-status'].textContent.includes('Saved.'));
 setting.last_run.status='ok';fields['desk-run-status'].textContent='Update overdue';
 await vm.runInContext('loadAISettings()',context);
 assert.equal(fields['desk-run-status'].textContent,'Update overdue');
 console.log('PASS: settings save, failure status and overdue status after an old successful run');
})().catch(error=>{console.error(error);process.exitCode=1});

(async()=>{
 const fields={},events={};let state='queued';let method;
 const c=vm.createContext({location:{pathname:'/twitter/o2co/'},setTimeout(){return 1},clearTimeout(){},document:{getElementById(id){return fields[id] ||= {addEventListener(e,fn){events[id+e]=fn}}}},fetch:async(u,options)=>{method=options?.method;return {ok:true,json:async()=>({status:state})}}});
 vm.runInContext(script.slice(0,script.lastIndexOf('initTheme();')),c);
 await vm.runInContext('loadRunControls()',c);
 assert(fields['run-now'].disabled);assert(fields['manual-run-status'].textContent.includes('Queued'));
 state='ok';await events['run-nowclick']();assert.equal(method,'POST');assert(!fields['run-now'].disabled);assert(!fields['run-refresh'].hidden);
 state='failed';await events['run-nowclick']();assert(fields['run-refresh'].hidden);assert(fields['manual-run-status'].textContent.includes('retained'));
 console.log('PASS: run request, active button, completion link and failure status');
})().catch(error=>{console.error(error);process.exitCode=1});
