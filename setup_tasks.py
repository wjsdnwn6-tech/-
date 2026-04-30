import sys
import subprocess

exe = sys.executable
ps_code = f"""
$action_krx = New-ScheduledTaskAction -Execute '{exe}' -Argument 'c:\\Users\\User\\Desktop\\짬뽕\\analyze_ichimoku.py --market KRX' -WorkingDirectory 'c:\\Users\\User\\Desktop\\짬뽕'
$trigger_krx = New-ScheduledTaskTrigger -Daily -At 4:00PM
Register-ScheduledTask -Action $action_krx -Trigger $trigger_krx -TaskName 'Ichimoku_KRX' -Force

$action_ndx = New-ScheduledTaskAction -Execute '{exe}' -Argument 'c:\\Users\\User\\Desktop\\짬뽕\\analyze_ichimoku.py --market NASDAQ' -WorkingDirectory 'c:\\Users\\User\\Desktop\\짬뽕'
$trigger_ndx = New-ScheduledTaskTrigger -Daily -At 6:30AM
Register-ScheduledTask -Action $action_ndx -Trigger $trigger_ndx -TaskName 'Ichimoku_NASDAQ' -Force
"""

with open('setup.ps1', 'w', encoding='utf-8') as f:
    f.write(ps_code)

subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", "setup.ps1"])
