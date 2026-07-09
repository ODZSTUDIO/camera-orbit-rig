# Camera Orbit Rig

중심점을 기준으로 회전하는 블렌더 카메라 리그 확장.
N 패널(`N` 키 → **Camera Rig** 탭)에서 Orbit / Tilt / Bank / Distance / Focus를 조절할 수 있다.

## 설치 (원격 저장소 연동)

Blender 4.2 이상에서:

1. `Edit > Preferences > Get Extensions > Repositories` 우측 `+` → **Add Remote Repository**
2. URL에 아래 주소 입력:

   ```
   https://raw.githubusercontent.com/<GITHUB_USER>/<REPO>/main/index.json
   ```

3. `Check for Updates on Startup`를 켜면 새 버전이 올라올 때 블렌더가 자동으로 알려준다.
4. 확장 목록에서 **Camera Orbit Rig** 설치.

## 버전 업데이트 방법 (개발자용)

1. `__init__.py` 수정
2. `blender_manifest.toml`의 `version` 올리기 (예: `1.0.1`)
3. 빌드:

   ```powershell
   powershell -ExecutionPolicy Bypass -File build.ps1
   ```

4. 커밋 & 푸시:

   ```powershell
   git add -A; git commit -m "v1.0.1"; git push
   ```

블렌더가 원격 저장소의 `index.json`을 읽어 업데이트를 감지한다.

## 리그 구조

```
CamRig_Root (Empty, 중심점)   ← Orbit: Z축 회전
 └ CamRig_Pivot (Empty)      ← Tilt: 상하 각도
    └ CamRig_Camera          ← Distance: 중심점과의 거리, Bank: 뷰 축 롤
```

슬라이더 값은 Root의 커스텀 프로퍼티에 드라이버로 연결되어 있어 키프레임 애니메이션이 가능하다.
