// Keep upstream release validation available, but never replace this fork with an upstream app.
enum ForkPolicy {
    static let upstreamUpdatesEnabled = false
    static let updateNotice = "Shift + Space fork 버전입니다. 자동 업데이트를 지원하지 않습니다. 새 버전은 fork에서 직접 빌드해 설치해주세요."
}
