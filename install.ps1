pip install -r requirements.txt

$CurrentDir = Get-Location

$Content = Get-Content -Path settings_template.yaml
$UpdatedContent = $Content -replace "<aws_credentials_path>", "$HOME\.aws\credentials"
$UpdatedContent = $UpdatedContent -replace "<log_path>", "$PSScriptRoot\log"

New-Item -Path "$PSScriptRoot\log" -ItemType Directory -Force

$UpdatedContent | Set-Content -Path "$PSScriptRoot\settings.yaml"
