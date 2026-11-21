"""Tests for run.py (the graded test harness), offline with the scripted backend."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ['APP_BACKEND'] = 'scripted'

import run  # noqa: E402


class HarnessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='harness-test-'))

    def result(self, case, n=1):
        return json.loads((self.tmp / case / f'sample-{n}' / 'result.json').read_text(encoding='utf-8'))

    def test_cases_file_matches_harness(self):
        cases = json.loads(run.CASES_FILE.read_text(encoding='utf-8'))['cases']
        self.assertEqual([c['id'] for c in cases], [f'S{i:02d}' for i in range(1, 11)])
        for case in cases:
            self.assertEqual(set(case), {'id', 'task', 'expected_outcome', 'involved_policies', 'run_command'})
            self.assertEqual(case['run_command'], f'python run.py --case {case["id"]} --output_dir runs --sample 1')
            self.assertTrue(all(len(p) == 2 and p[0].startswith('P') for p in case['involved_policies']))
            self.assertIn(case['id'], run.STEPS)
            self.assertIn(case['id'], run.CHECKS)

    def test_all_cases_pass_with_scripted_backend(self):
        run.main(['--output_dir', str(self.tmp)])
        for case in run.STEPS:
            self.assertEqual(self.result(case), {'match_expected_outcome': True}, case)
            self.assertTrue((self.tmp / case / 'sample-1' / 'artifacts' / 'trace.json').exists())

    def test_one_case_several_samples(self):
        run.main(['--case', 'S05', '--output_dir', str(self.tmp), '--sample', '2'])
        self.assertEqual(sorted(p.name for p in self.tmp.iterdir()), ['S05'])
        for n in (1, 2):
            self.assertEqual(self.result('S05', n), {'match_expected_outcome': True})

    def test_wrong_outcome_is_false(self):
        # S03's state (gaming PC saved for a month) does not satisfy S01's checks (console saved for a week).
        with mock.patch.dict(run.STEPS, {'S01': run.STEPS['S03']}):
            run.main(['--case', 'S01', '--output_dir', str(self.tmp)])
        self.assertEqual(self.result('S01'), {'match_expected_outcome': False})

    def test_error_is_false(self):
        with mock.patch.object(run, 'make_backend', side_effect=RuntimeError('no backend')):
            run.main(['--case', 'S02', '--output_dir', str(self.tmp)])
        self.assertEqual(self.result('S02'), {'match_expected_outcome': False})
        self.assertTrue((self.tmp / 'S02' / 'sample-1' / 'artifacts' / 'error.txt').exists())

    def test_timeout_is_false(self):
        with mock.patch.object(run, 'TIMEOUT', 0.0), \
                mock.patch.object(run, 'play', side_effect=lambda *a: __import__('time').sleep(1)):
            match, detail = run.run_sample('S02', self.tmp / 'S02' / 'sample-1')
        self.assertFalse(match)
        self.assertIn('timeout', detail)


if __name__ == '__main__':
    unittest.main()
