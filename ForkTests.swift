import AppKit

#if TESTS
func runForkTests() {
    let shift: UInt64 = 0xffff00000004
    featureCheck(spaceCombos == [0xffff00000001, 0xffff00000002, 0xffff00000003, shift], "Keep saved combination IDs stable")
    featureCheck(spaceComboNames.last == "Shift ⇧ + Space ␣" && hangulKeys.contains(shift))
    for side in [NX_DEVICELSHIFTKEYMASK, NX_DEVICERSHIFTKEYMASK] {
        let flags = CGEventFlags(rawValue: CGEventFlags.maskShift.rawValue | UInt64(side))
        featureCheck(spaceCombo(flags: flags) == shift)
        featureCheck(spaceCombo(flags: flags.union(.maskAlphaShift)) == shift, "Caps Lock does not change the combination")
        for extra: CGEventFlags in [.maskControl, .maskCommand, .maskAlternate] {
            featureCheck(spaceCombo(flags: flags.union(extra)) == nil)
        }
        var gate = SpaceComboGate()
        let press = gate.handle(down: true, repeatKey: false, flags: flags, chosen: [shift])
        featureCheck(press.consume && press.switchNow)
        let repeated = gate.handle(down: true, repeatKey: true, flags: [], chosen: [shift])
        featureCheck(repeated.consume && !repeated.switchNow)
        let release = gate.handle(down: false, repeatKey: false, flags: [], chosen: [])
        featureCheck(release.consume && !release.switchNow, "Own Space release even after modifier release or disable")
        featureCheck(!gate.handle(down: true, repeatKey: false, flags: flags, chosen: [spaceCombos[0]]).consume)
        featureCheck(!gate.handle(down: false, repeatKey: false, flags: flags, chosen: [shift]).consume)
        featureCheck(!gate.handle(down: true, repeatKey: false, flags: [], chosen: [shift]).consume)
    }
    let suite = "io.gksdud.fork-tests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    let engine = Engine(defaults: defaults, discover: { [] })
    featureCheck(engine.defaultSources == [sources[0]], "Keep the upstream default")
    engine.defaultSources = [shift]
    let restored = Engine(defaults: defaults, discover: { [] })
    featureCheck(restored.defaultSources == [shift] && restored.chosenCombos == [shift] && restored.mappedSources.isEmpty)
    featureCheck(decodeSources(encodeSources([shift])) == [shift])

    let release = AppRelease(tag_name: "v99.0.0", html_url: "https://github.com/codingnoye/gksdud/releases/tag/v99.0.0", body: nil, draft: false, prerelease: false)
    defaults.set(try! JSONEncoder().encode(release), forKey: "updates.release")
    var fetched = false
    let checker = UpdateChecker(defaults: defaults, installedVersion: "1.0.0", fetch: { _, _ in fetched = true })
    checker.check(); checker.check(force: true)
    featureCheck(!ForkPolicy.upstreamUpdatesEnabled && !checker.enabled && !fetched && !checker.checking && checker.available == nil)
    featureCheck(!AppDelegate(engine: engine).updates.enabled, "The production app must use the disabled checker")
    featureCheck(checker.release == nil && checker.lastChecked == nil, "Ignore inherited upstream cache")
    let installer = UpdateInstaller()
    installer.start(release)
    featureCheck(!installer.busy && installer.status == ForkPolicy.updateNotice)
    do { try UpdateInstaller.runHelper([]); featureCheck(false, "Fork helper must reject installation") }
    catch { featureCheck(error.localizedDescription == ForkPolicy.updateNotice) }
    let placeholder = URL(fileURLWithPath: "/private/tmp/gksdud-unused")
    do {
        try UpdateInstaller.launchHelper(PreparedUpdate(directory: placeholder, candidate: placeholder, version: "99.0.0"))
        featureCheck(false, "Fork must not launch an update helper")
    } catch { featureCheck(error.localizedDescription == ForkPolicy.updateNotice) }
    print("PASS: fork Shift + Space on both sides, repeat/release ownership, persistence, modifier isolation, disabled upstream updates and helper")
}
#endif
