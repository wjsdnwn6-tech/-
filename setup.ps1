
$action_krx = New-ScheduledTaskAction -Execute 'C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe' -Argument 'c:\Users\User\Desktop\kkkkk\analyze_ichimoku.py --market KRX' -WorkingDirectory 'c:\Users\User\Desktop\kkkkk'
$trigger_krx = New-ScheduledTaskTrigger -Daily -At 4:00PM
Register-ScheduledTask -Action $action_krx -Trigger $trigger_krx -TaskName 'Ichimoku_KRX' -Force

$action_ndx = New-ScheduledTaskAction -Execute 'C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe' -Argument 'c:\Users\User\Desktop\kkkkk\analyze_ichimoku.py --market NASDAQ' -WorkingDirectory 'c:\Users\User\Desktop\kkkkk'
$trigger_ndx = New-ScheduledTaskTrigger -Daily -At 6:30AM
Register-ScheduledTask -Action $action_ndx -Trigger $trigger_ndx -TaskName 'Ichimoku_NASDAQ' -Force
