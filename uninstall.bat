@echo off
echo [mgkh-local-agent] 작업 스케줄러 등록 해제 중...

schtasks /delete /tn "mgkh-local-agent" /f

if %errorlevel% equ 0 (
    echo 등록 해제 완료
) else (
    echo 등록 해제 실패 (등록된 작업이 없을 수 있습니다)
)
pause
