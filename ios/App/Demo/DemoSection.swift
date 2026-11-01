import MCCore
import SwiftUI

/// Секция «Демо» в настройках: мок-время, сдвиг, шаги истории, сброс.
struct DemoSection: View {
    let demo: DemoController
    /// Лист предпросмотра показывает SettingsView: `.sheet` на строке Form теряется при перерисовке.
    let onPreview: () -> Void
    @Environment(\.l10n) private var l

    var body: some View {
        Section {
            if let state = demo.state {
                LabeledContent(l("demo.now"), value: l.dateTime(state.now))
                LabeledContent(l("demo.offset"), value: l.hours(state.offsetHours))
                    .accessibilityIdentifier("demo.offset")
            }
            HStack {
                button("demo.advance6", .advance(hours: 6))
                button("demo.advance24", .advance(hours: 24))
            }
            button("demo.next", .nextBeat)
            Picker(l("demo.delay"), selection: Bindable(demo).notifyDelay) {
                ForEach([0, 5, 10], id: \.self) { Text(l("demo.delay.value", ["n": String($0)])).tag($0) }
            }
            .accessibilityIdentifier("demo.delay")
            button("demo.reset", .reset, role: .destructive)
            Button(l("demo.preview"), action: onPreview)
                .frame(maxWidth: .infinity)
                .accessibilityIdentifier("demo.preview")
        } header: {
            Text(l("demo.title")).accessibilityIdentifier("demo.section")
        } footer: {
            Text(l("demo.hint"))
        }
        .disabled(demo.busy)
    }

    private func button(_ key: String, _ action: DemoAction, role: ButtonRole? = nil) -> some View {
        Button(l(key), role: role) {
            Task { await demo.perform(action) }
        }
        .buttonStyle(.bordered)
        .frame(maxWidth: .infinity)
        .accessibilityIdentifier(key)
    }
}
