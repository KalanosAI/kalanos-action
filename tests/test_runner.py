import importlib.util
import json
import os
import re
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runner", ROOT/"scripts/run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()  # macOS: /var is a symlink to /private/var
        self.data = self.root/"data with spaces"
        self.data.mkdir()
        self.runner_temp = self.root/"temp"
        self.runner_temp.mkdir()
        self.env = {"INPUT_PATH":str(self.data),"INPUT_INSTALL":"false",
                    "INPUT_EXECUTABLE":"/usr/bin/true","RUNNER_TEMP":str(self.runner_temp),
                    "GITHUB_OUTPUT":str(self.root/"outputs")}
    def fake(self,code=0,valid=True):
        def call(args, **kwargs):
            self.args = args
            self.child_env = kwargs["env"]
            if valid:
                counts = {"total":1,"pass_count":1,"blocked":0,"review":0,"unknown":0,
                          "inventory_complete":True}
                Path(args[args.index("--report")+1]).write_text(json.dumps({"eligibility_counts":counts}))
            return subprocess.CompletedProcess(args,code)
        return call
    def test_default_version_matches_action_metadata(self):
        text = (ROOT/"action.yml").read_text()
        match = re.search(r"\n  version:\n(?:    .*\n)*?    default: '([^']+)'", text)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), runner.config(self.env)["version"])

    def test_pass_and_report(self):
        with patch.object(runner.subprocess,"run",side_effect=self.fake()):
            self.assertEqual(runner.run(self.env),0)
        self.assertIn("status=pass",(self.root/"outputs").read_text())
    def test_decision_failure_preserved(self):
        with patch.object(runner.subprocess,"run",side_effect=self.fake(1)):
            self.assertEqual(runner.run(self.env),1)
    def test_operational_failure_preserved(self):
        with patch.object(runner.subprocess,"run",side_effect=self.fake(2,False)):
            self.assertEqual(runner.run(self.env),2)
    def test_missing_report_fails_closed(self):
        with patch.object(runner.subprocess,"run",side_effect=self.fake(0,False)):
            self.assertEqual(runner.run(self.env),2)
    def test_unknown_exit_normalized(self):
        with patch.object(runner.subprocess,"run",side_effect=self.fake(137,False)):
            self.assertEqual(runner.run(self.env),2)
    def test_timeout_fails(self):
        with patch.object(runner.subprocess,"run",side_effect=subprocess.TimeoutExpired("kalanos",1)):
            self.assertEqual(runner.run(self.env),2)
    def test_path_is_single_argument_no_publish(self):
        self.env["KALANOS_API_KEY"]="secret-not-for-child"
        with patch.object(runner.subprocess,"run",side_effect=self.fake()):
            runner.run(self.env)
        self.assertEqual(self.args[2],str(self.data))
        self.assertNotIn("--publish",self.args)
        self.assertNotIn("KALANOS_API_KEY",self.child_env)
    def test_remote_rejected(self):
        self.env["INPUT_PATH"]="hf://datasets/org/data"
        with patch.object(runner.subprocess,"run") as call:
            self.assertEqual(runner.run(self.env),2)
            call.assert_not_called()
    def test_output_inside_data_rejected(self):
        self.env["RUNNER_TEMP"]=str(self.data)
        self.assertEqual(runner.run(self.env),2)
    def test_summary_off_default(self):
        self.env["GITHUB_STEP_SUMMARY"]=str(self.root/"summary")
        with patch.object(runner.subprocess,"run",side_effect=self.fake()):
            runner.run(self.env)
        self.assertFalse((self.root/"summary").exists())
    def test_summary_opt_in(self):
        self.env.update(INPUT_SUMMARY="true",GITHUB_STEP_SUMMARY=str(self.root/"summary"))
        with patch.object(runner.subprocess,"run",side_effect=self.fake()):
            runner.run(self.env)
        self.assertIn("pass_count",(self.root/"summary").read_text())
    def test_invalid_extra(self):
        self.env["INPUT_EXTRAS"]="video]; touch injected"
        with self.assertRaises(ValueError): runner.config(self.env)
    def test_unpinned_version(self):
        self.env["INPUT_VERSION"]="latest"
        with self.assertRaises(ValueError): runner.config(self.env)
    def test_invalid_fail_on(self):
        self.env["INPUT_FAIL_ON"]="pass"
        with self.assertRaises(ValueError): runner.config(self.env)
    def test_option_like_profile_safe(self):
        self.env["INPUT_PROFILE"]="x; touch injected"
        cfg=runner.config(self.env)
        self.assertIn("x; touch injected",runner.command(cfg,"kalanos",self.root/"audit"))
    def test_nonexistent_source(self):
        self.env["INPUT_PATH"]=str(self.root/"missing")
        self.assertEqual(runner.run(self.env),2)
    def test_preinstalled_cli_missing(self):
        self.env["INPUT_EXECUTABLE"]="nonexistent-kalanos-92834"
        self.assertEqual(runner.run(self.env),2)
    def test_empty_counts(self):
        p=self.root/"report.json"
        p.write_text(json.dumps({"eligibility_counts":{"total":0,"pass_count":0,"review":0,"unknown":0,"blocked":0,"inventory_complete":True}}))
        with self.assertRaises(ValueError): runner.report_counts(p)
    def test_standard_tier_supported(self):
        self.env["INPUT_TIER"]="standard"
        self.assertEqual(runner.config(self.env)["tier"], "standard")
    def test_sampled_not_a_cli_tier(self):
        self.env["INPUT_TIER"]="sampled"
        with self.assertRaises(ValueError): runner.config(self.env)
    def test_real_subprocess_stub(self):
        stub = self.root/"stub-kalanos"
        stub.write_text("#!/usr/bin/env python3\n"
            "import json,sys\nfrom pathlib import Path\n"
            "assert sys.argv[1] == 'grade'\n"
            "assert '--publish' not in sys.argv\n"
            "p=Path(sys.argv[sys.argv.index('--report')+1])\n"
            "p.write_text(json.dumps({'eligibility_counts':"
            "{'total':1,'pass_count':1,'blocked':0,'review':0,'unknown':0,'inventory_complete':True}}))\n")
        stub.chmod(0o700)
        self.env["INPUT_EXECUTABLE"]=str(stub)
        self.env["PATH"]=os.environ["PATH"]
        self.assertEqual(runner.run(self.env),0)
    def test_install_error_returns_operational_error(self):
        self.env["INPUT_INSTALL"]="true"
        with patch.object(runner.subprocess,"run",side_effect=subprocess.CalledProcessError(1,"pip")):
            self.assertEqual(runner.run(self.env),2)
    def test_repeated_runs_unique_output(self):
        with patch.object(runner.subprocess,"run",side_effect=self.fake()):
            runner.run(self.env)
            runner.run(self.env)
        self.assertEqual(len(list(self.runner_temp.iterdir())),2)

if __name__=="__main__": unittest.main()
