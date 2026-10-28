const assert=require('assert'),vm=require('vm'),fs=require('fs'),path=require('path');
const commandFactory=require('../service/commands');
const commands=commandFactory.create({restoreHost:'192.0.2.2'});
assert.throws(()=>commandFactory.create({restoreHost:'1.2.3.999'}));
assert.throws(()=>commandFactory.create({restoreHost:'127.0.0.1; id'}));
function harness(armed){
 let files={'/proc/sys/kernel/random/boot_id':'test-boot'},handler,tick,started=0,calls=[];
 if(armed)files['/opt/usr/home/owner/share/commercial-break-recovery/armed']='true';
 let connected=false;
 const platform={start(){started++},stop(){connected=false},status(){return{agent:{connected}}},execute(cmd){calls.push(cmd);return Promise.resolve({exit_code:0,timed_out:false,stdout:cmd===commands.enable?'true|true\n':'healthy'})}};
 const fakefs={mkdirSync(){},readFileSync(p){if(!(p in files))throw Error('missing');return files[p]},writeFileSync(p,v){files[p]=v},renameSync(a,b){files[b]=files[a];delete files[a]}};
 const server={on(){},listen(p,h,cb){cb()},close(){}};
 const token='a'.repeat(64);
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../service/main.js'),'utf8'),{require(n){return n==='fs'?fakefs:n==='http'?{createServer(cb){handler=cb;return server}}:n==='./platform'?platform:n==='./commands'?{create(){return commands}}:n==='./private-config.json'?{token}:require(n)},process:{pid:5,version:'v12',getuid(){return 5001},on(){},exit(){throw Error('exit')}},Buffer,setInterval(cb){tick=cb},Date,Promise,console});
 function request(method,url,auth){let r={writeHead(c){this.code=c},end(v){this.body=JSON.parse(v)}};handler({method,url,headers:{authorization:auth===false?'':'Bearer '+token}},r);return r}
 return {request,tick,calls,get started(){return started},connect(){connected=true}};
}
(async()=>{
 let h=harness(false);assert.equal(h.started,0);assert.equal(h.request('GET','/status',false).code,401);assert.equal(h.request('GET','/status').body.state.armed,false);
 assert.equal(h.request('POST','/exec').code,404);h.tick();assert.equal(h.calls.length,0);
 assert.equal(h.request('POST','/arm').code,200);assert.equal(h.started,1);h.connect();h.tick();await new Promise(r=>setImmediate(r));assert.deepEqual(h.calls,[commands.enable,commands.engine,commands.snapshot]);
 assert.equal(h.request('GET','/status').body.state.engine.report,'healthy');
 let auto=harness(true);assert.equal(auto.started,1);
 assert(commands.enable.includes("WHERE app_id='cBRecov001.svc' AND package='cBRecov001'"));assert(!commands.engine.includes('restart '));assert(commands.engine.includes('is-active --quiet'));
 console.log('PASS: authenticated fixed endpoints, no root before arming, automatic armed startup, own flags only, existing engine preserved.');
})().catch(e=>{console.error(e);process.exit(1)});
