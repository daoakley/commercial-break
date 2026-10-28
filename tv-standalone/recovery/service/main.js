'use strict';
var fs=require('fs'),http=require('http'),crypto=require('crypto');
var platform=require('./platform'),config=require('./private-config.json');
if (!/^[a-f0-9]{64}$/.test(config.token)) throw new Error('Invalid recovery token');
var commands=require('./commands').create(config);
var DATA='/opt/usr/home/owner/share/commercial-break-recovery';
fs.mkdirSync(DATA,{recursive:true,mode:0o700});
function read(p){try{return fs.readFileSync(p,'utf8').trim()}catch(e){return null}}
var boot=read('/proc/sys/kernel/random/boot_id');
var state={version:'0.1.1',startedAt:Date.now(),bootId:boot,pid:process.pid,uid:process.getuid(),node:process.version,armed:read(DATA+'/armed')==='true',events:[],engine:null};
var busy=false,initialized=false,lastAttempt=0,lastSnapshot=0,agentPid=null;
function persist(){try{fs.writeFileSync(DATA+'/status.json.tmp',JSON.stringify(state),{mode:0o600});fs.renameSync(DATA+'/status.json.tmp',DATA+'/status.json')}catch(e){}}
function note(kind,message){state.events.push({at:Date.now(),kind:kind,message:String(message).slice(0,500)});if(state.events.length>30)state.events.shift();persist()}
function checked(command){return platform.execute(command,15000).then(function(r){if(r.timed_out||r.exit_code!==0)throw new Error('Operation failed: '+r.exit_code);return r.stdout})}
function snapshot(){return checked(commands.snapshot).then(function(out){state.engine={at:Date.now(),report:out};persist();return out})}
function tick(){
 if(busy||!state.armed)return;
 var p=platform.status();
 if(!p.agent.connected){persist();return}
 if(agentPid!==p.agent.pid){agentPid=p.agent.pid;initialized=false;lastAttempt=0}
 if(!initialized && Date.now()-lastAttempt<60000)return;
 if(initialized && Date.now()-lastSnapshot<15000)return;
 busy=true;lastSnapshot=Date.now();
 var task=Promise.resolve();
 if(!initialized){lastAttempt=Date.now();task=checked(commands.enable).then(function(out){if(out.trim()!=='true|true')throw new Error('Boot flags were not enabled');return checked(commands.engine)}).then(function(){initialized=true;note('engine-ready','Root confirmed; existing supervised engine started or already running')});}
 task.then(snapshot).catch(function(e){note('recovery-error',e.message)}).then(function(){busy=false});
}
function authorized(req){var value=String(req.headers.authorization||'');var expected='Bearer '+config.token;return value.length===expected.length&&crypto.timingSafeEqual(Buffer.from(value),Buffer.from(expected))}
function reply(res,code,data){res.writeHead(code,{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'});res.end(JSON.stringify(data))}
var server=http.createServer(function(req,res){
 if(!authorized(req))return reply(res,401,{error:'unauthorized'});
 if(req.method==='GET'&&req.url==='/status')return reply(res,200,{state:state,platform:platform.status()});
 if(req.method!=='POST')return reply(res,404,{error:'not found'});
 if(busy)return reply(res,409,{error:'busy'});
 if(req.url==='/arm'){
  fs.writeFileSync(DATA+'/armed','true',{mode:0o600});state.armed=true;initialized=false;lastAttempt=0;note('armed','Automatic recovery requested');platform.start();return reply(res,200,{armed:true});
 }
 if(req.url==='/restore-developer-host'){
  busy=true;return checked(commands.restoreHost).then(function(out){note('developer-host-restored',out);reply(res,200,{restored:true})}).catch(function(e){reply(res,503,{error:e.message})}).then(function(){busy=false});
 }
 if(req.url==='/disarm'){
  busy=true;return checked(commands.disable).then(function(){fs.writeFileSync(DATA+'/armed','false',{mode:0o600});state.armed=false;platform.stop();note('disarmed','Startup disabled; current engine preserved');reply(res,200,{armed:false})}).catch(function(e){reply(res,503,{error:e.message})}).then(function(){busy=false});
 }
 return reply(res,404,{error:'not found'});
});
server.on('error',function(e){note('http-error',e.code);process.exit(1)});
server.listen(18765,'0.0.0.0',function(){note('service-start','Signed JavaScript service running');if(state.armed)platform.start()});
server.timeout=5000;
setInterval(tick,5000);
process.on('SIGTERM',function(){platform.stop();server.close();process.exit(0)});
