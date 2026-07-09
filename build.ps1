# Camera Orbit Rig — 확장 패키지 빌드 스크립트
# blender_manifest.toml의 version을 읽어 zip을 만들고 index.json을 재생성한다.
# 사용법: 버전 수정 후  powershell -ExecutionPolicy Bypass -File build.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# 매니페스트에서 메타데이터 읽기
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

$zipName = "$id-$version.zip"
$zipPath = Join-Path $root $zipName

# 이전 버전 zip 정리
Get-ChildItem $root -Filter "$id-*.zip" | Remove-Item -Force

# 소스 파일만 zip으로 묶기 (manifest가 zip 최상위에 오도록)
Compress-Archive -Path (Join-Path $root "__init__.py"), (Join-Path $root "blender_manifest.toml") -DestinationPath $zipPath

# 해시/크기 계산
$hash = (Get-FileHash $zipPath -Algorithm SHA256).Hash.ToLower()
$size = (Get-Item $zipPath).Length

# 블렌더 원격 저장소 인덱스 생성
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
            archive_url         = "./$zipName"
            archive_size        = $size
            archive_hash        = "sha256:$hash"
        }
    )
}

$json = $index | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText((Join-Path $root "index.json"), $json, (New-Object System.Text.UTF8Encoding($false)))

Write-Output "빌드 완료: $zipName (v$version, $size bytes)"
