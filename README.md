# Camera Orbit Rig

중심점을 기준으로 회전하는 블렌더 카메라 리그 확장.
N 패널(`N` 키 → **Camera Rig** 탭)에서 Orbit / Tilt / Bank / Distance / Focus를 조절할 수 있다.

## 설치 (원격 저장소 연동)

Blender 4.2 이상에서:

1. `Edit > Preferences > Get Extensions > Repositories` 우측 `+` → **Add Remote Repository**
2. URL에 아래 주소 입력:

   ```
   https://raw.githubusercontent.com/ODZSTUDIO/camera-orbit-rig/main/index.json
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
CamRig_Root (중심점/마스터)     ← G: 중심점 이동 / R: Orbit / S: Distance 배율
 ├ CamRig_OrbitPath (궤도 원)  ← 시각 표시 전용 (선택 불가, 거리/틸트 따라 자동 갱신)
 ├ CamRig_Target (조준점)      ← G로 이동하면 카메라가 따라봄 (Damped Track, 롤 보존)
 ├ CamRig_Focus (초점)         ← G로 이동하면 DOF 초점이 따라감 (focus object)
 └ CamRig_Pivot                ← R: Tilt
    └ CamRig_Camera            ← G: Distance / R: Bank
```

- **Target Tracking** 슬라이더로 타깃 추적 강도(constraint influence)를 조절할 수 있다
- 패널의 **선택** 버튼으로 Root / Cam / Target / Focus를 빠르게 선택

## 뷰포트 조작 (v1.1.0+)

슬라이더가 오브젝트 트랜스폼을 직접 읽고 쓰기 때문에 뷰포트에서 G/R/S로
움직이면 N 패널 슬라이더에 그대로 반영되고, 반대도 마찬가지다.
리그에 필요 없는 축은 잠겨 있어서 G/R/S가 정확히 해당 컨트롤만 움직인다.

- 애니메이션: 오브젝트 트랜스폼에 키프레임을 넣거나, N 패널의 **Keyframe Rig**(열쇠 아이콘)
  버튼으로 현재 프레임에 리그 전체 키프레임을 한 번에 삽입
- **Reset Aim**: 카메라 조준이 틀어졌을 때 중심점을 다시 바라보게 정리 (Bank는 유지)
- v1.0.0에서 만든 리그를 선택하면 패널에 **Upgrade Rig** 버튼이 표시된다
