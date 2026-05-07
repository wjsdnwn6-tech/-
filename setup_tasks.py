import sys
import subprocess
import os

exe = sys.executable
project_dir = os.path.dirname(os.path.abspath(__file__)).replace('\\', '\\\\')
script_path = os.path.join(project_dir, 'analyze_ichimoku.py').replace('\\', '\\\\')

ps_code = f"""
$action_krx = New-ScheduledTaskAction -Execute '{exe}' -Argument '{script_path} --market KRX' -WorkingDirectory '{project_dir}'
$trigger_krx = New-ScheduledTaskTrigger -Daily -At 4:00PM
Register-ScheduledTask -Action $action_krx -Trigger $trigger_krx -TaskName 'Ichimoku_KRX' -Force

$action_ndx = New-ScheduledTaskAction -Execute '{exe}' -Argument '{script_path} --market NASDAQ' -WorkingDirectory '{project_dir}'
$trigger_ndx = New-ScheduledTaskTrigger -Daily -At 6:30AM
Register-ScheduledTask -Action $action_ndx -Trigger $trigger_ndx -TaskName 'Ichimoku_NASDAQ' -Force
"""

setup_ps1_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'setup.ps1')
with open(setup_ps1_path, 'w', encoding='utf-8') as f:
    f.write(ps_code)

subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", setup_ps1_path])
