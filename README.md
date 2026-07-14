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

zip은 저장소에 커밋하지 않고 **GitHub Release 첨부파일**로 버전마다 영구 보관한다
(`index.json`은 항상 최신 버전의 Release 다운로드 URL을 가리킨다). 과거 버전도
저장소의 [Releases](https://github.com/ODZSTUDIO/camera-orbit-rig/releases) 탭에서
계속 내려받을 수 있다.

1. `__init__.py` 수정
2. `blender_manifest.toml`의 `version` 올리기 (예: `1.4.0`)
3. 빌드 (dist/ 에 zip 생성 + index.json을 Release URL로 갱신):

   ```powershell
   powershell -ExecutionPolicy Bypass -File build.ps1
   ```

4. 커밋 & 푸시:

   ```powershell
   git add -A; git commit -m "v1.4.0 ..."; git push
   ```

5. 태그 푸시 & Release 생성 (dist/ 의 zip을 그대로 첨부):

   ```powershell
   git tag v1.4.0; git push origin v1.4.0
   gh release create v1.4.0 "dist/camera_orbit_rig-1.4.0.zip" --title "v1.4.0" --notes "..."
   ```

블렌더가 원격 저장소의 `index.json`을 읽어 최신 버전 업데이트를 감지한다.

## 리그 구조

```
📷 CamRig_Root (중심점)        ← G: 중심점 이동 / S: Distance 배율 (회전은 쓰지 않음)
 ├ CamRig_Target (조준점)      ← G로 이동하면 카메라가 따라봄 (Damped Track, 롤 보존)
 ├ CamRig_Focus (초점)         ← G로 이동하면 DOF 초점이 따라감 (focus object)
 └ CamRig_OrbitPath (궤도 원)  ← R: Orbit — Camera의 실제 부모
    └ CamRig_Camera            ← G(Z만): Tilt / R: 자유 회전(XYZ, Bank=Z)
```

- Pivot은 없다. OrbitPath가 Camera의 **실제 부모**라서 OrbitPath를 R로 돌리면
  그 아래 Camera가 그대로 함께 돈다 — 드라이버가 아니라 순수 부모-자식 관계라서
  의존성 순환(dependency cycle) 걱정 없이 동작한다
- Camera의 Z 위치 자체가 Tilt다. Camera는 OrbitPath 중심으로부터 항상 일정
  거리(반지름)를 유지한 채 Z로만 움직이도록 Y 위치가 드라이버로 자동
  계산된다 — Camera를 잡고 **Z로만 이동(G, Z)**해도 거리는 그대로 유지된 채
  Tilt만 바뀐다. 기본 Tilt는 0
- 조준은 Pivot 회전이 아니라 Target을 향한 Damped Track이 항상 담당하므로
  위치가 바뀌어도 자동으로 다시 조준된다
- Camera의 회전은 X/Y/Z 모두 열려 있지만, Damped Track 때문에 **Target
  Tracking** 영향력이 1(기본값)일 때는 X/Y 회전이 거의 상쇄되고 Z(Bank)만
  항상 반영된다. 영향력을 낮추면 X/Y/Z 모두 완전한 수동 조준이 된다
- 패널의 **선택** 버튼으로 Root / Path / Cam / Target / Focus를 빠르게 선택

## 뷰포트 조작 (v1.1.0+)

슬라이더가 오브젝트 트랜스폼을 직접 읽고 쓰기 때문에 뷰포트에서 G/R/S로
움직이면 N 패널 슬라이더에 그대로 반영되고, 반대도 마찬가지다.
리그에 필요 없는 축은 잠겨 있어서 G/R/S가 정확히 해당 컨트롤만 움직인다.

- 애니메이션: 오브젝트 트랜스폼에 키프레임을 넣거나, N 패널의 **Keyframe Rig**(열쇠 아이콘)
  버튼으로 현재 프레임에 리그 전체 키프레임을 한 번에 삽입
- **Reset Aim**: 카메라 조준이 틀어졌을 때 중심점을 다시 바라보게 정리 (Bank는 유지)
- 구버전에서 만든 리그를 선택하면 패널에 **Upgrade Rig** 버튼이 표시되어
  기존 값을 보존한 채 최신 구조로 변환한다
