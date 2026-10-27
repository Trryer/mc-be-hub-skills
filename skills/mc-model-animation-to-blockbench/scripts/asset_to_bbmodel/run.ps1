$ErrorActionPreference = 'Stop'
& python (Join-Path $PSScriptRoot 'convert.py') @args
exit $LASTEXITCODE
