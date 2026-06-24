import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


class WatchTaskScriptsTest(unittest.TestCase):
    def read_script(self, name: str) -> str:
        return (SCRIPTS_DIR / name).read_text(encoding="utf-8")

    def test_register_script_creates_on_demand_task_without_logon_trigger(self):
        script = self.read_script("register_watch_multi_bookmakers_task.ps1")

        self.assertIn('$TaskName = "SurebetWatchMultiBookmakers"', script)
        self.assertIn("Register-ScheduledTask", script)
        self.assertIn("New-ScheduledTaskAction", script)
        self.assertIn("start_watch_multi_bookmakers.ps1", script)
        self.assertIn("-IntervalSeconds", script)
        self.assertIn("7200", script)
        self.assertIn("-MaxCycles", script)
        self.assertIn("0", script)
        self.assertNotIn("New-ScheduledTaskTrigger", script)
        self.assertNotIn("-AtLogOn", script)
        self.assertNotIn("SUREBET_PASSWORD", script)

    def test_task_start_script_starts_registered_task_and_reports_status(self):
        script = self.read_script("start_watch_multi_bookmakers_task.ps1")

        self.assertIn('$TaskName = "SurebetWatchMultiBookmakers"', script)
        self.assertIn("Start-ScheduledTask", script)
        self.assertIn("Get-ScheduledTaskInfo", script)
        self.assertIn("ScheduledTaskState", script)
        self.assertNotIn("py main.py", script)

    def test_stop_script_stops_task_and_remaining_process_tree(self):
        script = self.read_script("stop_watch_multi_bookmakers.ps1")

        self.assertIn('$TaskName = "SurebetWatchMultiBookmakers"', script)
        self.assertIn("Stop-ScheduledTask", script)
        self.assertIn("Stop-Process", script)
        self.assertIn("watch_multi_bookmakers.pid", script)
        self.assertIn("ParentProcessId", script)

    def test_status_script_reports_task_process_logs_history_and_usage(self):
        script = self.read_script("status_watch_multi_bookmakers.ps1")

        self.assertIn('$TaskName = "SurebetWatchMultiBookmakers"', script)
        self.assertIn("Get-ScheduledTask", script)
        self.assertIn("Get-ScheduledTaskInfo", script)
        self.assertIn("RunningProcessCount", script)
        self.assertIn("multi_bookmaker_watch_history.jsonl", script)
        self.assertIn("the_odds_api_usage_history.jsonl", script)
        self.assertIn("watch_multi_bookmakers_7200.log", script)


if __name__ == "__main__":
    unittest.main()
