# 원본 변경 감지와 fork 병합

이 fork는 Shift + Space를 한영 키 목록에 추가한다. 기본 한영 키는 우측 Command로 유지한다. 원본 앱으로 자동 업데이트하면 fork 기능이 사라질 수 있어 업데이트 확인·설치와 helper 실행을 차단한다. 새 앱은 직접 빌드해 설치한다.

## 실행 구조

이 Codex 채팅의 자동화가 매월 1일 한국 시간 10:17에 `scripts/watch-upstream.py`를 실행한다. 원본 `codingnoye/gksdud`의 main 커밋이 fork `livekthgpters/gksdud-shift`에 포함되어 있으면 종료한다. 새 변경이 있으면 `upstream_changed` dispatch를 보내 fork의 `Sync upstream` workflow를 실행한다.

Workflow는 임시 후보에서 원본을 병합하고 `scripts/validate.sh`로 검사한다. 통과한 후보의 Git bundle만 별도 반영 job에 전달한다. 읽기 전용 검증 job에는 쓰기 토큰을 전달하지 않는다. 반영 job은 검증한 SHA와 두 저장소의 이력을 확인하고 fork main에 일반 push한다. 원본에는 push하지 않는다.

충돌, 보호 파일 변경, 테스트 실패, main 동시 변경에서는 자동 반영을 중단한다. Reset·force push·충돌 한쪽 자동 선택은 사용하지 않는다. Fork 전용 정책·테스트·검증·workflow 파일이 바뀌면 사람이 검토한다. Bundle artifact는 1일 보관하며 앱 ZIP은 업로드하지 않는다.

## 외부 감지 실행

GitHub connector에는 dispatch 전송 기능이 없어 감지 스크립트는 로컬 `gh` 인증을 사용한다. Fork 읽기·Actions 읽기·dispatch 권한이 필요하다. Fine-grained token을 사용하는 별도 실행 환경에서는 fork의 Contents 쓰기와 Actions 읽기를 부여한다. 토큰은 인증 저장소나 `GH_TOKEN` 환경 변수로 제공하고 저장소에 저장하지 않는다.

저장소 루트에서 실행한다.

```sh
# 확인만 수행하고 dispatch·상태 저장은 하지 않는다.
python3 scripts/watch-upstream.py --dry-run

# 변경이 있을 때만 workflow를 호출한다.
python3 scripts/watch-upstream.py

# 충돌이나 실패 원인을 수정한 뒤 같은 변경을 재시도한다.
python3 scripts/watch-upstream.py --retry
```

감지 상태는 `.local/upstream-watch.json`에 저장한다. 실행 중인 같은 원본 변경은 중복 호출하지 않는다. 실패한 SHA 조합은 재호출하지 않으며 원본 또는 fork main이 바뀌거나 `--retry`를 지정하면 다시 시도한다. Dispatch가 실행 목록에 나타나지 않고 1시간 이상 지났다면 다음 감지 실행에서 재전송한다.

## 운영과 복구

Dispatch workflow는 fork main에 있어야 한다. 이 저장소의 Actions 예약 기능은 사용하지 않으므로 공개 저장소의 60일 무활동 예약 중단에 의존하지 않는다. Codex 자동화는 Mac과 Codex가 실행 중일 때 확인하며 다시 실행되면 최신 원본 커밋을 확인한다. 상시 감지가 필요하면 같은 스크립트를 상시 실행 환경에서 주기적으로 실행한다.

변경 없음·진행 중에는 알리지 않고 반영 완료·실패·조치 필요 시 이 채팅에 알린다. 실패하면 Actions 실행 요약에서 원본/fork SHA, 충돌 파일, 검사 로그를 확인한다. 충돌을 해결하고 `GKSDUD_SIGN_MODE=ad-hoc bash build.sh`를 통과시킨 뒤 fork main에 반영하거나 Actions에서 수동 재실행한다.

자동 병합은 GitHub 소스만 갱신한다. 로컬 checkout이나 설치 앱은 자동 교체하지 않는다. 실제 좌우 Shift 입력, 한글 조합 중 전환, 빠른 연속 입력, 접근성 권한 회복은 설치 후 별도로 확인한다.
