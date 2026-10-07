param([switch]$Web, [switch]$Prepare)
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if ($Web) {
    Set-Location (Join-Path $projectRoot 'apps\web')
    $env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:8315'
    node node_modules\vite\bin\vite.js --host 127.0.0.1 --port 4315 --strictPort
} else {
    Set-Location (Join-Path $projectRoot 'apps\api')
    $env:APP_MODE = 'demo'
    $env:OPENAI_API_KEY = ''
    $env:CALENDAR_PROVIDER = 'local'
    $env:DATABASE_URL = 'sqlite:///./voicedesk-upgrade-demo.db'
    $env:DEMO_DATA_SIZE = 'quick'
    $env:CORS_ORIGINS = 'http://127.0.0.1:4315,http://localhost:4315'
    if ($Prepare) {
        & .\.venv\Scripts\python.exe -m alembic upgrade head
        if ($LASTEXITCODE) { exit $LASTEXITCODE }
        & .\.venv\Scripts\python.exe -m voicedesk.seed
        exit $LASTEXITCODE
    }
    & .\.venv\Scripts\python.exe -m uvicorn voicedesk.main:app --host 127.0.0.1 --port 8315
}
