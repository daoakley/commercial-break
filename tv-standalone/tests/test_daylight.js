// Keep controller previews aligned with the engine's UTC solar calculation.
const fs=require('fs'),vm=require('vm'),assert=require('assert'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../app/appearance.js'),'utf8');
const solar=source.slice(source.indexOf('  function raleighDay('),source.indexOf('  function previewTheme('));
const context={};vm.createContext(context);vm.runInContext(solar,context);
for(const [time,day] of [
 ['2026-06-21T16:00:00Z',true],['2026-06-22T03:00:00Z',false],
 ['2026-10-27T10:45:00Z',false],['2026-10-27T12:00:00Z',true],
 ['2026-10-27T21:45:00Z',true],['2026-10-27T23:00:00Z',false],
 ['2026-03-08T17:00:00Z',true],['2026-11-01T05:00:00Z',false],
 ['2028-02-29T17:00:00Z',true]
])assert.strictEqual(context.raleighDay(new Date(time)),day,time);
console.log('Daylight preview: summer, winter, sunrise, sunset, DST and leap-year cases passed.');
