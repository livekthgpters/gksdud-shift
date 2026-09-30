# gksdud Shift + Space 추가 및 원본 변경 감지 병합 계획

작성일: 2026-09-30 (한국 시간)

## 목표와 현재 상태

원본 gksdud를 fork해서 Shift + Space 한영 전환을 추가한다. 이 Codex 채팅의 자동화로 매시간 원본 main의 새 변경을 확인하고, 내 기능을 유지한 채 병합한다. 충돌이 없고 빌드·검증을 통과한 경우에만 fork의 main을 갱신한다.

- 원본: https://github.com/codingnoye/gksdud
- Fork: https://github.com/livekthgpters/gksdud
- 로컬 경로: /Users/tkim/Documents/workspace/03-personal/gksdud-shift
- 조사 기준 원본 커밋: `18b579a8f09bcbeb6dc8806bd66ee26c7b14ea65`
- 기본 브랜치: `main`

이번 구현은 Shift + Space, fork 업데이트 정책, 변경 감지 스크립트와 병합 workflow를 포함한다. 설치 앱 교체와 실제 키보드 설정 변경은 별도 단계다.

## 저장소 운영

Git remote는 `origin`을 내 fork, `upstream`을 원본으로 설정한다. Fork의 main은 Shift + Space를 포함한 유지관리 버전으로 사용한다. 최초 기능 작업은 `codex/shift-space-upstream-sync` 브랜치에서 진행하고, 검증 후 main에 반영한다. 원본의 main은 `upstream/main`으로 추적하므로 별도의 원본 복사 브랜치는 만들지 않는다.

원본 저장소에 push하지 않는다. 원본의 CONTRIBUTING.md는 Agent의 자동 PR 생성을 금지하므로, 이 계획의 원본 업데이트도 PR 없이 fork main에 직접 병합하는 방식으로 구성한다.

## Shift + Space 구현

`main.swift`의 기존 Space 조합 처리 구조를 활용한다.

1. `spaceCombos` 끝에 `0xffff00000004`를 추가한다.
2. `spaceComboNames`의 같은 위치에 `Shift ⇧ + Space ␣`를 추가한다.
3. `spaceCombo(flags:)`의 판별 배열 끝에 `.maskShift`를 추가한다.

기존 식별자와 배열 순서를 유지해 저장된 설정과 호환되게 한다. `hangulKeys`와 SourcePicker는 목록을 읽어 메뉴를 생성하므로 현재 구조에서는 UI 파일을 별도로 수정할 필요가 없다. 기존 기본값인 우측 Command는 유지하고, 사용자가 Shift + Space를 선택하게 한다.

좌우 Shift 모두 지원한다. Shift를 누른 상태에서 Space를 누르면 한 번 전환하고 공백 입력을 막는다. 키를 길게 눌러 발생하는 반복 이벤트와 Space 해제 이벤트는 기존 SpaceComboGate로 처리한다. Shift + Control + Space 등 보조키가 두 개 이상인 조합은 전환 대상으로 삼지 않는다. 접근성 권한이 없을 때는 다른 Space 조합과 동일하게 선택을 비활성화한다. Space 조합은 전체 키보드에 적용되며 키보드별 개별 지정은 기존과 같이 단일 키만 지원한다.

## 검증

현재 `build.sh`는 arm64·x86_64 Universal 앱을 만들고 테스트 모드의 `--self-test`를 실행한다. CI에서는 다음 명령을 사용한다.

```sh
GKSDUD_SIGN_MODE=ad-hoc bash build.sh
```

기존 Space 조합 테스트를 확인하고 Shift 미지원 기대값을 갱신한다. 다음 동작을 자동 테스트에 추가한다.

- Shift + Space가 새 식별자로 판별되고 이름·저장·복원·메뉴 목록에 포함된다.
- 선택했을 때 한 번만 전환하고, 반복·키 해제는 추가 전환을 일으키지 않는다.
- Shift를 먼저 떼어도 해당 Space의 해제 이벤트가 앱으로 새지 않는다.
- 선택하지 않았을 때 Shift + Space를 가로채지 않는다.
- 일반 Space와 복수 보조키 조합은 기존 동작을 유지한다.
- Control·Command·Option + Space와 단일 한영 키의 기존 테스트가 통과한다.

실제 Mac에서는 좌우 Shift, 한글 조합 중 전환, 빠른 연속 입력, Shift를 먼저 떼기, 접근성 권한 해제·재허용, Caps Lock 켜짐, 재실행 후 설정 복원을 확인한다. CI의 논리 테스트와 빌드 성공만으로 실제 입력 동작을 검증했다고 보고하지 않는다.

## 원본 변경 감지와 자동 병합

`scripts/watch-upstream.py`를 이 Codex 채팅의 외부 자동화에서 매시간 실행한다. 원본과 fork의 main SHA를 확인하고 원본 커밋이 fork에 이미 포함되어 있으면 종료한다. 새 변경이 있을 때만 fork에 `repository_dispatch`의 `upstream_changed` 이벤트를 전송한다. 실행 환경은 Mac과 Codex가 실행 중이어야 하며, 꺼져 있던 시간의 변경은 다음 실행에서 확인한다.

`.github/workflows/sync-upstream.yml`은 다음 이벤트와 수동 실행을 받는다. Fork Actions의 `schedule`은 사용하지 않아 예약 workflow의 60일 무활동 중단에 의존하지 않는다. 별도 `sync-status` 브랜치도 만들지 않는다.

```yaml
on:
  repository_dispatch:
    types: [upstream_changed]
  workflow_dispatch:
```

원본 push가 fork에 자동 전달되는 것은 아니다. 현재 구현은 원본 관리자 협조 없이 원본 SHA를 확인하는 방식이며 감지 주기만큼 지연될 수 있다. 나중에 원본 관리자가 webhook을 제공하면 같은 dispatch workflow를 재사용할 수 있다.

감지 스크립트는 `gh`의 기존 인증을 사용한다. 토큰을 파일·코드·로그에 넣지 않는다. 같은 원본 변경의 병합이 실행 중이면 호출하지 않고, 실패한 원본/fork SHA 조합은 수정하거나 `--retry`로 재시도하기 전까지 다시 호출하지 않는다. 원본이나 fork main이 바뀌면 새 후보를 검증한다. Mac의 감지 상태는 Git에서 제외된 `.local/upstream-watch.json`에 저장한다.

실제 갱신 대상은 언제나 fork main으로 고정한다. 같은 동기화 작업은 concurrency 그룹으로 직렬 실행하고 진행 중인 실행을 취소하지 않는다. Dispatch payload는 알림으로만 사용하고 workflow에서 고정된 원본 URL의 현재 main을 다시 가져온다.

처리 순서는 다음과 같다.

1. Fork main과 원본 main의 전체 이력을 가져오고 두 커밋 SHA를 기록한다. 원본은 `codingnoye/gksdud`로 고정한다.
2. 원본 main이 이미 fork main에 포함되어 있으면 성공으로 종료한다. 불필요한 병합 커밋·빌드·알림을 만들지 않는다.
3. 새 변경이 있으면 임시 작업 브랜치에서 `git merge --no-edit upstream/main`으로 병합한다. 내 커밋을 지우는 reset, force push, 일괄 theirs 선택은 사용하지 않는다.
4. 충돌이 있으면 main을 갱신하지 않는다. 충돌 파일과 양쪽 SHA를 실행 요약에 남기고 작업을 실패 처리한다.
5. 충돌이 없으면 fork 기능 보존 검사, 기존 스크립트 검사, Universal 빌드, self-test를 실행한다. 검증 실패 시 main을 갱신하지 않는다.
6. 검증한 정확한 후보 커밋을 fork main에 일반 push한다. 실행 중 main이 바뀌어 push가 거절되면 중단한다. 새 main으로 수동 재실행해 다시 병합·검증한다.
7. 반영된 원본 SHA, 병합 커밋, 검증 결과를 실행 요약에 기록한다.

macOS 빌드는 기존 CI와 같은 표준 `macos-15` 환경을 우선 사용한다. 실행 제한 시간은 20분으로 설정한다. 기존 `.github/workflows/checks.yml`과 동기화 workflow는 공통 `scripts/validate.sh`를 사용해 같은 스크립트 검사와 빌드·self-test를 실행한다.

`GITHUB_TOKEN`으로 push한 변경은 일반 push workflow를 다시 실행시키지 않을 수 있다. 따라서 동기화 workflow 안에서 모든 필수 검증을 끝낸 뒤 push한다.

검증 단계는 `contents: read` 권한으로 실행하고 쓰기 토큰을 빌드 환경에 노출하지 않는다. 별도의 최종 반영 job만 `contents: write` 권한을 갖는다. 반영 job은 후보 SHA와 시작 당시 main SHA를 확인하고 검증한 커밋을 push하며, 후보의 빌드 스크립트를 실행하지 않는다. 검증된 Git bundle만 두 job 사이에 artifact로 전달하고 1일간 보관한다. 앱 ZIP은 업로드하지 않는다. Checkout 등 사용하는 action은 원본 CI처럼 고정된 커밋 SHA로 지정한다.

Fork 전용 테스트·workflow가 병합 과정에서 없어지지 않았는지도 확인한다. 검증 job은 시작 시점 fork의 필수 검사 진입점과 테스트의 보존 여부를 확인하고, 누락·예상 밖 변경이면 자동 반영을 중단한다. ForkPolicy·ForkTests와 동기화·검증 파일은 시작 시점 blob과 비교한다. 빌드 목록과 테스트 진입점도 확인하고 실제 Swift self-test로 기능 보존을 검증한다. 보호 파일 변경은 사람이 검토한 뒤 수동 반영한다.

## 외부 자동화 유지와 실패 알림

Fork에서 Actions를 활성화하고 dispatch workflow가 기본 브랜치에 존재하는지 확인한다. 이 Codex 채팅의 자동화는 매시간 감지 스크립트를 실행한다. 변경이 없거나 병합이 진행 중이면 알리지 않고, 반영 완료·실패·사용자 조치가 필요한 경우에만 알린다. 감지 작업의 상태와 Actions 결과를 함께 확인한다.

GitHub 계정의 Actions 실패 알림도 운영자가 설정할 수 있다. 알림 전달은 계정 설정과 Codex 실행 상태에 의존하므로 코드만 추가해서 이메일이나 상시 감지가 보장된다고 설명하지 않는다. Mac이 꺼져 있어도 감지하려면 같은 스크립트를 별도 상시 실행 환경으로 옮긴다.

충돌이나 빌드 실패는 Actions의 실패 상태·로그로 확인한다. 수동 복구 시 원본 변경과 내 기능을 함께 유지하도록 코드를 수정하고 같은 검증을 통과한 뒤 반영한다. 자동으로 충돌 한쪽을 버리지 않는다.

## Fork 앱의 업데이트 정책

현재 `UpdateChecking.swift`와 `UpdateInstaller.swift`는 원본 `codingnoye/gksdud`의 릴리스·다운로드 URL을 사용한다. 원본 앱을 업데이트로 설치하면 Shift + Space 기능이 사라질 수 있다.

첫 구현에서는 fork 빌드의 원본 앱 업데이트 확인·설치 경로를 비활성화하고 수동 빌드·설치로 운영한다. 관련 UI도 실제 정책을 표시하게 고친다. 기존 원본 동작을 검증하는 테스트는 보존하고 fork 정책을 위한 테스트를 추가한다. 이후 fork 자체 배포를 도입할 때는 릴리스 URL, 다운로드 검증, 버전 번호, 서명 신원까지 함께 설계한다. URL 문자열만 바꿔 자동 업데이트가 완성됐다고 처리하지 않는다.

Ad-hoc 서명은 업데이트 사이의 앱 신원을 보존하지 않아 접근성 권한을 다시 허용해야 할 수 있다. 변경 감지 자동 병합은 GitHub의 소스만 갱신하며 사용자의 Mac에 설치된 앱을 교체하지 않는다. 앱 설치·키보드 설정 변경은 별도 단계다.

## 구현 순서와 완료 기준

1. 기능 브랜치 생성, Shift + Space 추가, 테스트 보강.
2. Fork 빌드의 원본 앱 업데이트 경로 비활성화.
3. 로컬 빌드·self-test와 실제 키 입력 검증.
4. Dispatch workflow와 외부 감지·동기화 스크립트 작성, 제한된 권한 구성.
5. 별도 테스트 브랜치·임시 저장소에서 변경 없음, 정상 병합, 충돌, 테스트 실패, 동시 main 변경을 재현한다. 실패 사례가 main을 바꾸지 않는지 확인한다.
6. 검증된 변경을 fork main에 반영하고 Actions 수동 실행으로 확인한다. Actions와 외부 자동화의 활성화 상태를 확인하고 실패 알림 설정을 문서화한다.

완료 조건은 설정에서 Shift + Space를 선택해 실제 한영 전환이 동작하고, 원본 업데이트가 있을 때 감지 작업과 workflow가 내 기능을 보존하며 검증 후 반영하는 것이다. 충돌·검증 실패에서는 기존 main이 유지되어야 한다. 소스 동기화와 앱 설치 상태는 따로 보고한다.

## 비용과 참고 문서

공개 fork에서 GitHub 표준 실행 환경을 사용하는 실행 시간은 무료다. 고성능 Larger runners는 사용하지 않는다. 빌드 파일을 Actions artifact로 보관할 경우 저장 공간 한도가 있으므로 검증된 Git bundle만 1일 보관하고 앱 빌드 artifact는 업로드하지 않는다.

- Fork 동기화: https://docs.github.com/en/pull-requests/how-tos/work-with-forks/syncing-a-fork
- Dispatch·예약 실행·무활동 제한: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- Token으로 발생한 이벤트의 재실행 제한: https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-when-your-workflow-runs/triggering-a-workflow
- Actions 요금: https://docs.github.com/en/billing/concepts/product-billing/github-actions
- 원본 개발·검증 안내: CONTRIBUTING.md

GitHub Actions 문서는 Context7과 GitHub 공식 문서로 확인했다. 계획서의 소스 구조는 위에 기록한 커밋 기준이며 구현 시 원본 변경 여부를 다시 확인한다.
