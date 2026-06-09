@echo off
echo [mgkh-local-agent] 작업 스케줄러 등록 중...

if not exist "C:\A\mgkh-local-agent\logs" (
    mkdir "C:\A\mgkh-local-agent\logs"
    echo logs 폴더 생성 완료
)

schtasks /create /tn "mgkh-local-agent" ^
  /tr "C:\A\mgkh-local-agent\run.bat" ^
  /sc onstart ^
  /ru SYSTEM ^
  /rl HIGHEST ^
  /f

if %errorlevel% equ 0 (
    echo 등록 완료
) else (
    echo 등록 실패
)
pause
