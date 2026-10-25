"""Run the real shell loop against isolated capture, app and control fakes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class AgentIdentityTests(unittest.TestCase):
    def run_agent(self, apps, runtime=0):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);state=root/'state';state.mkdir()
            log=root/'controls';capture=root/'frame.png'
            def executable(name,body):
                path=root/name;path.write_text('#!/bin/sh\n'+body);path.chmod(0o700);return str(path)
            vconf=executable('vconf',f'''n=$(cat '{root}/app-count' 2>/dev/null || echo 0)
n=$((n+1)); echo "$n" > '{root}/app-count'
case "$n" in
'''+''.join(f'{i}) app={app} ;;\n' for i,app in enumerate(apps,1))+f'''*) app={apps[-1]} ;;
esac
echo "key, value = $app (String)"
''')
            dotnet=executable('capture',f"echo image > '{capture}'\necho 'rc=0 width=480'\n")
            busctl=executable('busctl',f'''case "$*" in
*GetSpeakerMute*) if [ -f '{root}/muted' ]; then echo 'ii 1 0'; else echo 'ii 0 0'; fi ;;
*SetSpeakerMute*) echo "$*" >> '{log}'; case "$*" in *true) touch '{root}/muted';; *) rm -f '{root}/muted';; esac ;;
esac
''')
            executable('curl',f"echo request >> '{log}'\necho MUTE\n")
            (root/'tv-backlight.sh').write_text(f'''BACKLIGHT_STATE='{root}/backlight'
BACKLIGHT_OVERRIDE='{root}/backlight-override'
release_owned_backlight() {{ :; }}
''')
            (root/'tv-overlay.sh').write_text(f'''OVERLAY_LEASE='{root}/lease'
overlay_release() {{ echo release >> '{log}'; }}
overlay_shutdown() {{ overlay_release; }}
overlay_running() {{ return 1; }}
overlay_start_or_renew() {{ echo cover >> '{log}'; }}
''')
            (root/'tv-watchdog.sh').write_text('exit 0\n')
            (root/'probe').touch();(root/'library').touch()
            source=(Path(__file__).parent/'tv-agent.sh').read_text()
            source=source.replace('STATE_DIR=/run/codex-commercial-muter',f"STATE_DIR='{state}'")
            source=source.replace('CAPTURE_FILE=/home/owner/share/tmp/sdk_tools/codex-display-sample.png.png',f"CAPTURE_FILE='{capture}'")
            source=source.replace('/usr/bin/vconftool',vconf).replace('/usr/bin/dotnet',dotnet).replace('/usr/bin/busctl',busctl)
            script=root/'agent.sh';script.write_text(source)
            env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],FRAME_URL='http://unused.invalid',
                     FRAME_TOKEN='test-only',PROBE_DLL=str(root/'probe'),PATCHED_LIB=str(root/'library'),
                     AGENT_DIR=str(root),MAX_FRAMES='1',MAX_RUNTIME_SECONDS=str(runtime),
                     NAVIGATION_OBSERVER='0',FAST_MODE='0',CAPTURE_PERSISTENT='0',INTERVAL_SECONDS='0',
                     OVERLAY_WARM='0',OBSERVE_ONLY='0',AD_BACKLIGHT='')
            result=subprocess.run(['/bin/sh',str(script)],env=env,capture_output=True,text=True,timeout=8)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse((state/'owned-mute').exists())
            return log.read_text()

    def test_switch_during_capture_does_not_submit_old_frame(self):
        log=self.run_agent(['old.app','new.app'],runtime=1)
        self.assertNotIn('request',log)
        self.assertNotIn('SetSpeakerMute b true',log)

    def test_switch_while_waiting_for_response_rejects_mute(self):
        log=self.run_agent(['old.app','old.app','new.app'])
        self.assertIn('request',log)
        self.assertNotIn('SetSpeakerMute b true',log)
        self.assertNotIn('cover',log)

    def test_switch_during_actuation_releases_owned_controls(self):
        log=self.run_agent(['old.app','old.app','old.app','new.app'])
        self.assertIn('SetSpeakerMute b true',log)
        self.assertIn('SetSpeakerMute b false',log)
        self.assertIn('cover',log)

if __name__=='__main__':unittest.main()
