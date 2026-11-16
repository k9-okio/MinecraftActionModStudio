$ErrorActionPreference = 'Stop'

$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
$jdk = 'D:\mc\tools\jdk25\jdk-25.0.5+8\bin'
$javac = Join-Path $jdk 'javac.exe'
$jarTool = Join-Path $jdk 'jar.exe'

$rsArgs = Get-Content 'D:\mc\roulette_survival\javac_args.txt' -Raw
$cpMatch = [regex]::Match($rsArgs, '-classpath\s+"([^"]+)"')
if (-not $cpMatch.Success) { throw 'cannot find Forge classpath in roulette_survival/javac_args.txt' }
$cp = $cpMatch.Groups[1].Value

$classes = Join-Path $proj 'build\classes'
$libsOut = Join-Path $proj 'build\libs'
Remove-Item $classes -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $libsOut -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $classes | Out-Null
New-Item -ItemType Directory -Force -Path $libsOut | Out-Null

$sources = Get-ChildItem (Join-Path $proj 'src\main\java') -Recurse -Filter '*.java' |
    ForEach-Object { $_.FullName }

$argsFile = Join-Path $proj 'javac_args.txt'
$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('-encoding UTF-8')
$lines.Add('--release 21')
$lines.Add('-d "' + ($classes -replace '\\', '/') + '"')
$lines.Add('-classpath "' + $cp + '"')
foreach ($source in $sources) {
    $lines.Add('"' + ($source -replace '\\', '/') + '"')
}
Set-Content -Path $argsFile -Value $lines -Encoding ASCII

& $javac "@$argsFile"
if ($LASTEXITCODE -ne 0) { throw "javac failed with exit code $LASTEXITCODE" }

Copy-Item (Join-Path $proj 'src\main\resources\*') $classes -Recurse -Force

$outJar = Join-Path $libsOut 'player_model-1.0.0.jar'
& $jarTool --create --file $outJar --manifest (Join-Path $proj 'manifest.txt') -C $classes .
if ($LASTEXITCODE -ne 0) { throw "jar failed with exit code $LASTEXITCODE" }

Get-Item $outJar | Select-Object FullName, Length | Format-List
