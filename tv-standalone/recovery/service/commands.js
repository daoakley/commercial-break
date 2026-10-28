'use strict';
function create(config) {
if (!/^([0-9]{1,3}\.){3}[0-9]{1,3}$/.test(config.restoreHost) || config.restoreHost.split('.').some(function(n){return +n>255})) throw new Error('Invalid restoreHost');
var HOME='/opt/usr/home/owner/commercial-block';
var flags="sqlite3 /opt/dbspace/.pkgmgr_parser.db \"SELECT app_onboot || '|' || app_autorestart FROM package_app_info WHERE app_id='cBRecov001.svc';\"";
var enable="set -e\n[ \"$(id -u)\" = 0 ]\n"+
 "H="+HOME+"\nmkdir -p \"$H/backups/recovery-widget\"\n"+
 "test -f \"$H/backups/recovery-widget/registry.sqlite\" || sqlite3 /opt/dbspace/.pkgmgr_parser.db \".backup '$H/backups/recovery-widget/registry.sqlite'\"\n"+
 "count=$(sqlite3 /opt/dbspace/.pkgmgr_parser.db \"SELECT COUNT(*) FROM package_app_info WHERE app_id='cBRecov001.svc' AND package='cBRecov001';\")\n[ \"$count\" = 1 ]\n"+
 "sqlite3 /opt/dbspace/.pkgmgr_parser.db \"BEGIN IMMEDIATE; UPDATE package_app_info SET app_onboot='true',app_autorestart='true' WHERE app_id='cBRecov001.svc' AND package='cBRecov001'; COMMIT;\"\n"+flags;
var engine="set -e\n[ \"$(id -u)\" = 0 ]\nH="+HOME+"\n"+
 "if ! systemctl is-active --quiet commercial-break-engine.service; then\n"+
 "for f in CommercialBlock.dll engine-supervisor.sh release-owned.sh commercial-break-engine.service; do test -f \"$H/$f\"; done\n"+
 "cp \"$H/commercial-break-engine.service\" /run/systemd/system/commercial-break-engine.service\nsystemctl daemon-reload\nsystemctl start commercial-break-engine.service\nfi\n"+
 "systemctl show commercial-break-engine.service -p ActiveState -p SubState -p MainPID -p NRestarts\n";
var snapshot="cat /proc/sys/kernel/random/boot_id; cat /proc/uptime; "+flags+"\n"+
 "systemctl show commercial-break-engine.service -p ActiveState -p SubState -p MainPID -p NRestarts\n"+
 "curl --fail --silent --max-time 3 --config "+HOME+"/control.curl http://127.0.0.1:18764/status";
var restoreHost="set -e\n[ \"$(id -u)\" = 0 ]\nvconftool set -f -t string db/sdk/develop/ip "+config.restoreHost+"\nvconftool get db/sdk/develop/ip";
var disable="sqlite3 /opt/dbspace/.pkgmgr_parser.db \"BEGIN IMMEDIATE; UPDATE package_app_info SET app_onboot='false',app_autorestart='false' WHERE app_id='cBRecov001.svc' AND package='cBRecov001'; COMMIT;\"\n"+flags;
return {enable:enable,engine:engine,snapshot:snapshot,restoreHost:restoreHost,disable:disable};
}
module.exports={create:create};
