# Camera Orbit Rig — 확장 패키지 빌드 스크립트
# blender_manifest.toml의 version을 읽어 zip을 dist/ 에 만들고, index.json이
# GitHub Release 다운로드 URL을 가리키도록 갱신한다. zip 자체는 저장소에
#커밋하지 않고 GitHub Release 첨부파일로만 영구 보관한다(버전별 다운로드 보존).
#
# 사용법 (버전 올릴 때마다):
#   1) blender_manifest.toml 의 version 수정
#   2) powershell -ExecutionPolicy Bypass -File build.ps1
#   3) git add -A; git commit -m "vX.Y.Z ..."; git push
#   4) git tag vX.Y.Z; git push origin vX.Y.Z
#   5) gh release create vX.Y.Z "dist/<zip>" --title "vX.Y.Z" --notes "..."

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$repoSlug = "ODZSTUDIO/camera-orbit-rig"

$manifest = Get-Content (Join-Path $root "blender_manifest.toml") -Raw

function Get-TomlValue($key) {
    if ($manifest -match "(?m)^$key\s*=\s*`"([^`"]+)`"") { return $Matches[1] }
    throw "manifest에서 $key 를 찾을 수 없습니다"
}

$version    = Get-TomlValue "version"
$id         = Get-TomlValue "id"
$name       = Get-TomlValue "name"
$tagline    = Get-TomlValue "tagline"
$maintainer = Get-TomlValue "maintainer"
$blenderMin = Get-TomlValue "blender_version_min"

$distDir = Join-Path $root "dist"
New-Item -ItemType Directory -Force -Path $distDir | Out-Null

$zipName = "$id-$version.zip"
$zipPath = Join-Path $distDir $zipName

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
Compress-Archive -Path (Join-Path $root "__init__.py"), (Join-Path $root "blender_manifest.toml") -DestinationPath $zipPath

$hash = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $zipPath).Length
$archiveUrl = "https://github.com/$repoSlug/releases/download/v$version/$zipName"

$index = [ordered]@{
    version   = "v1"
    blocklist = @()
    data      = @(
        [ordered]@{
            schema_version      = "1.0.0"
            id                  = $id
            name                = $name
            tagline             = $tagline
            version             = $version
            type                = "add-on"
            maintainer          = $maintainer
            license             = @("SPDX:GPL-3.0-or-later")
            blender_version_min = $blenderMin
            tags                = @("Camera", "3D View")
            archive_url         = $archiveUrl
            archive_size        = $size
            archive_hash        = "sha256:$hash"
        }
    )
}

$json = $index | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText((Join-Path $root "index.json"), $json, (New-Object System.Text.UTF8Encoding($false)))

Write-Output "빌드 완료: dist/$zipName (v$version, $size bytes)"
Write-Output "index.json -> $archiveUrl"
Write-Output ""
Write-Output "다음 단계:"
Write-Output "  git add -A; git commit -m `"v$version ...`"; git push"
Write-Output "  git tag v$version; git push origin v$version"
Write-Output "  gh release create v$version `"dist/$zipName`" --title `"v$version`" --notes `"...`""
