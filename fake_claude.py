"""Stand-in for `claude -p --input-format stream-json` used by the bridge tests.

Each user turn gets an assistant event almost immediately and a result event a
little later, mirroring the real CLI's post-answer delay. Markers in the turn
text select the behaviour: WARM -> {"ok":true}; DIE -> exit without answering;
SILENT -> emit only the result event.
"""
import json
import sys
import time

RESULT_DELAY = float(sys.argv[1]) if len(sys.argv) > 1 else 0.3


def emit(event):
    sys.stdout.write(json.dumps(event) + "\n")
    sys.stdout.flush()


emit({"type": "system", "subtype": "init"})
for line in sys.stdin:
    message = json.loads(line)
    text = " ".join(block.get("text", "") for block in message["message"]["content"]
                    if block.get("type") == "text")
    if "DIE" in text:
        sys.exit(1)
    if "WARM" in text.upper():
        answer = '{"ok":true}'
    else:
        answer = '{"label":"ad","confidence":0.9,"program":"","evidence":"fake pitch","program_changed":false,"category":"unknown","presentation":"full_screen_ad"}'
    time.sleep(0.05)
    if "SILENT" not in text:
        emit({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": answer}]}})
    time.sleep(RESULT_DELAY)
    emit({"type": "result", "subtype": "success", "duration_api_ms": 50})
