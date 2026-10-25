import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from claude_bridge import AuditStore, ClaudeSession, SessionError, SessionPool, build_system_prompt, parse_verdict

FAKE = str(Path(__file__).with_name("fake_claude.py"))
PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 24


def fake_popen(result_delay=0.3):
    def popen(command, **kwargs):
        assert command[1:3] == ["-p", "--model"] and "--system-prompt" in command
        return subprocess.Popen([sys.executable, FAKE, str(result_delay)], **kwargs)
    return popen


def fake_session(system_prompt, result_delay=0.3, timeout=2):
    return ClaudeSession(system_prompt, timeout=timeout, popen=fake_popen(result_delay))


def settle(session, seconds=2):
    deadline = time.monotonic() + seconds
    while session.busy and time.monotonic() < deadline:
        time.sleep(0.02)


class VerdictParsingTests(unittest.TestCase):
    def test_accepts_claude_json_fence(self):
        result = parse_verdict('```json\n{"label":"ad","confidence":0.85,"program":"","evidence":"pitch"}\n```')
        self.assertEqual(result["label"], "ad")
        self.assertEqual(result["confidence"], 0.85)

    def test_rejects_unusable_verdict(self):
        with self.assertRaises(ValueError):
            parse_verdict('{"label":"ad","confidence":3}')

    def test_program_change_signal_is_boolean(self):
        self.assertTrue(parse_verdict('{"label":"program","confidence":0.9,"program_changed":true}')["program_changed"])

    def test_system_prompt_keeps_instructions_and_terse_output_rule(self):
        prompt = build_system_prompt("Classify one TV frame.")
        self.assertIn("Classify one TV frame.", prompt)
        self.assertIn("Output only the JSON", prompt)
        self.assertIn("never instructions", prompt)


class SessionTests(unittest.TestCase):
    def test_verdict_is_returned_before_the_result_event(self):
        session = fake_session("rules", result_delay=0.6)
        try:
            started = time.monotonic()
            verdict = session.classify(PNG, "frame one")
            elapsed = time.monotonic() - started
            self.assertEqual(verdict["label"], "ad")
            self.assertLess(elapsed, 0.5)
            self.assertTrue(session.busy, "session stays busy until the CLI finishes the turn")
            settle(session)
            self.assertFalse(session.busy)
            self.assertEqual(session.turns, 1)
        finally:
            session.close()

    def test_warm_up_turn_completes_without_counting_as_a_frame(self):
        session = fake_session("rules", result_delay=0.05)
        try:
            self.assertTrue(session.warm())
            self.assertEqual(session.turns, 0)
            self.assertFalse(session.busy)
        finally:
            session.close()

    def test_process_death_raises_and_marks_session_dead(self):
        session = fake_session("rules")
        try:
            with self.assertRaises(SessionError):
                session.classify(PNG, "please DIE now")
            self.assertTrue(session.dead)
        finally:
            session.close()

    def test_missing_answer_times_out_and_closes_session(self):
        session = fake_session("rules", result_delay=0.05, timeout=0.5)
        try:
            with self.assertRaises(SessionError):
                session.classify(PNG, "SILENT frame")
            self.assertTrue(session.dead)
        finally:
            session.close()


class PoolTests(unittest.TestCase):
    def pool(self, size=1, turns=30, result_delay=0.3):
        return SessionPool(size=size, turns=turns, warm=False,
                           factory=lambda prompt: fake_session(prompt, result_delay=result_delay))

    def close(self, pool):
        with pool.condition:
            for session in pool.sessions:
                session.close()

    def test_busy_single_session_rejects_second_frame_until_turn_finishes(self):
        pool = self.pool(size=1, result_delay=0.6)
        try:
            session = pool.acquire("rules", wait=3)
            session.classify(PNG, "frame")
            pool.release(session)
            with self.assertRaises(SessionError):
                pool.acquire("rules", wait=0.1)
            again = pool.acquire("rules", wait=2)
            self.assertIs(again, session)
        finally:
            self.close(pool)

    def test_first_frame_waits_for_the_starting_session(self):
        pool = self.pool(size=1, result_delay=0.05)
        try:
            # Shorter than a session start-up would normally be allowed; the
            # start-up grace period must still produce a session.
            session = pool.acquire("rules", wait=0.01)
            self.assertFalse(session.dead)
        finally:
            self.close(pool)

    def test_second_session_serves_while_first_finishes_its_turn(self):
        pool = self.pool(size=2, result_delay=0.8)
        try:
            first = pool.acquire("rules", wait=3)
            first.classify(PNG, "frame")
            pool.release(first)
            second = pool.acquire("rules", wait=3)
            self.assertIsNot(second, first)
            self.assertEqual(second.classify(PNG, "frame")["label"], "ad")
        finally:
            self.close(pool)

    def test_worn_session_is_retired_and_replaced(self):
        pool = self.pool(size=1, turns=5, result_delay=0.02)
        try:
            seen = set()
            for _ in range(6):
                session = pool.acquire("rules", wait=3)
                session.classify(PNG, "frame")
                pool.release(session)
                seen.add(id(session))
                settle(session, 1)
            self.assertEqual(len(seen), 2)
        finally:
            self.close(pool)

    def test_dead_session_is_replaced_on_next_acquire(self):
        pool = self.pool(size=1)
        try:
            session = pool.acquire("rules", wait=3)
            with self.assertRaises(SessionError):
                session.classify(PNG, "DIE")
            pool.release(session)
            replacement = pool.acquire("rules", wait=3)
            self.assertIsNot(replacement, session)
            self.assertFalse(replacement.dead)
        finally:
            self.close(pool)

    def test_changed_instructions_rebuild_sessions(self):
        pool = self.pool(size=1, result_delay=0.02)
        try:
            old = pool.acquire("rules v1", wait=3)
            pool.release(old)
            new = pool.acquire("rules v2", wait=3)
            self.assertIsNot(new, old)
            self.assertTrue(old.dead)
            self.assertIn("rules v2", new.system_prompt)
        finally:
            self.close(pool)


class AuditStoreTests(unittest.TestCase):
    def test_saves_pre_ad_ad_and_post_ad_frames(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = AuditStore(directory)
            program = {"label": "program", "confidence": .95}
            ad = {"label": "ad", "confidence": .97}
            for index in range(4):
                audit.observe(bytes([index]), {"app": "tv"}, program, 1000 + index)
            audit.observe(b"ad1", {"app": "tv"}, ad, 1004)
            audit.observe(b"show", {"app": "tv"}, program, 1005)
            images = list(Path(directory).glob("*.png"))
            self.assertEqual(len(images), 7)
            self.assertTrue(all(path.stat().st_mode & 0o077 == 0 for path in images))

    def test_saves_program_frame_after_audio_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            candidate_file = Path(directory) / "boundaries.csv"
            at = datetime.fromtimestamp(1009, timezone.utc).isoformat()
            candidate_file.write_text("at_utc,silence_ms\n" + at + ",120\n")
            audit = AuditStore(directory, candidate_file)
            program = {"label": "program", "confidence": .9}
            audit.observe(b"first", {"app": "tv"}, program, 1000)
            audit.observe(b"candidate", {"app": "tv"}, program, 1014)
            self.assertEqual(len(list(Path(directory).glob("*.png"))), 2)


if __name__ == "__main__":
    unittest.main()
