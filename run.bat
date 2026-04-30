@echo off
echo 백엔드 서버를 시작합니다...
start cmd /k "python -m uvicorn main:app --reload"

echo 프론트엔드 서버를 시작합니다...
start cmd /k "cd frontend && npm run dev"

echo 실행이 완료되었습니다. 브라우저에서 http://localhost:5173 으로 접속하세요.
