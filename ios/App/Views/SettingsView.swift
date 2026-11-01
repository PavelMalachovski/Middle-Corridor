import MCCore
import SwiftUI

/// Настройки: адрес сервера (симулятор/iPhone) и язык.
struct SettingsView: View {
    let model: AppModel
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @AppStorage(LangChoice.key) private var langChoice = LangChoice.system.rawValue
    @State private var server = ""
    @State private var probe: Result<Int, APIError>?
    @State private var probing = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(AppModel.defaultServer, text: $server)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityIdentifier("settings.server")
                    Button {
                        Task { await check() }
                    } label: {
                        HStack {
                            Text(l("settings.check"))
                            if probing {
                                Spacer()
                                ProgressView()
                            }
                        }
                    }
                    .disabled(probing)
                    if let probe { probeText(probe) }
                } header: {
                    Text(l("settings.server"))
                } footer: {
                    Text(l("settings.serverHint"))
                }

                Section(l("settings.language")) {
                    Picker(l("settings.language"), selection: $langChoice) {
                        Text(l("settings.lang.system")).tag(LangChoice.system.rawValue)
                        Text("Русский").tag(LangChoice.ru.rawValue)
                        Text("English").tag(LangChoice.en.rawValue)
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                }

                Section(l("settings.notify")) {
                    ForEach(NoticeKind.allCases, id: \.self) { kind in
                        NotifyToggle(kind: kind, title: l("notify.\(kind.rawValue)"))
                    }
                }

                if model.demo.isActive {
                    DemoSection(demo: model.demo)
                }

                Section {
                    LabeledContent(l("settings.version"), value: version)
                        .contentShape(Rectangle())
                        .onLongPressGesture(minimumDuration: 1) {
                            model.demo.isEnabled.toggle()
                            Task { await model.demo.probe() }
                        }
                        .accessibilityIdentifier("settings.version")
                }
            }
            .navigationTitle(l("settings.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(l("settings.done")) {
                        model.setServer(server)
                        dismiss()
                    }
                }
            }
            .onAppear { server = model.serverURL }
            .task { await model.demo.probe() }
            .onChange(of: server) { probe = nil }
        }
    }

    private func check() async {
        probing = true
        defer { probing = false }
        probe = await model.probe(server)
    }

    @ViewBuilder
    private func probeText(_ result: Result<Int, APIError>) -> some View {
        switch result {
        case .success(let nodes):
            Label(l("settings.ok", ["value": String(nodes)]), systemImage: "checkmark.circle.fill")
                .foregroundStyle(Theme.ok)
        case .failure(let error):
            Label(l("settings.fail", ["value": String(describing: error)]), systemImage: "wifi.slash")
                .foregroundStyle(Theme.critical)
        }
    }

    private var version: String {
        let info = Bundle.main.infoDictionary
        let short = info?["CFBundleShortVersionString"] as? String ?? "?"
        let build = info?["CFBundleVersion"] as? String ?? "?"
        return "\(short) (\(build))"
    }
}

/// Переключатель вида уведомлений; по умолчанию включён.
private struct NotifyToggle: View {
    let kind: NoticeKind
    let title: String
    @AppStorage private var isOn: Bool

    init(kind: NoticeKind, title: String) {
        self.kind = kind
        self.title = title
        _isOn = AppStorage(wrappedValue: true, NotifyPrefs.key(kind))
    }

    var body: some View {
        Toggle(title, isOn: $isOn).accessibilityIdentifier("notify.\(kind.rawValue)")
    }
}
