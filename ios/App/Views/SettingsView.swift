import MCCore
import SwiftUI
import UIKit
import UserNotifications

/// Настройки: уведомления (и честный статус разрешения iOS), язык, о приложении.
/// Адрес сервера и пульт демо — раздел для разработчика: долгое нажатие на строку версии.
struct SettingsView: View {
    let model: AppModel
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var scenePhase
    @AppStorage(LangChoice.key) private var langChoice = LangChoice.system.rawValue
    @State private var server = ""
    @State private var probe: Result<Int, APIError>?
    @State private var probing = false
    @State private var showPreview = false
    @State private var notificationsDenied = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    if notificationsDenied {
                        Button(action: openNotificationSettings) {
                            Label {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(l("settings.notifyDenied")).foregroundStyle(Theme.warning)
                                    Text(l("settings.openSystem")).font(.footnote)
                                }
                            } icon: {
                                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(Theme.warning)
                            }
                        }
                        .accessibilityIdentifier("settings.notifyDenied")
                    }
                    ForEach(NoticeKind.allCases, id: \.self) { kind in
                        NotifyToggle(kind: kind, title: l("notify.\(kind.rawValue)"))
                            .disabled(notificationsDenied)
                    }
                } header: {
                    Text(l("settings.notify"))
                } footer: {
                    Text(l("settings.notifyHint"))
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

                if model.demo.isEnabled {
                    serverSection
                }
                if model.demo.isActive {
                    DemoSection(demo: model.demo) { showPreview = true }
                }

                Section(l("settings.about")) {
                    LabeledContent(l("settings.version"), value: version)
                        .contentShape(Rectangle())
                        .onLongPressGesture(minimumDuration: 1) {
                            model.demo.isEnabled.toggle()
                            Task { await model.demo.probe() }
                        }
                        .accessibilityIdentifier("settings.version")
                    if let updated = model.store.updatedAt {
                        LabeledContent(l("settings.data"), value: l("list.updated", ["value": l.relative(updated)]))
                    }
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
            .task { await refreshAuthorization() }
            .onChange(of: scenePhase) { _, phase in
                // вернулись из настроек iOS — разрешение могло поменяться
                if phase == .active { Task { await refreshAuthorization() } }
            }
            .sheet(isPresented: $showPreview) {
                PreviewSheet(status: model.demo.previewStatus(lang: l.lang))
            }
            .onChange(of: server) { probe = nil }
        }
    }

    /// Адрес бэкенда: симулятор — localhost, iPhone — IP Мака. Пользователю без пульта не виден.
    private var serverSection: some View {
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
    }

    private func check() async {
        probing = true
        defer { probing = false }
        probe = await model.probe(server)
    }

    private func refreshAuthorization() async {
        notificationsDenied = await model.notifier.isDenied()
    }

    private func openNotificationSettings() {
        if let url = URL(string: UIApplication.openNotificationSettingsURLString) { openURL(url) }
    }

    @ViewBuilder
    private func probeText(_ result: Result<Int, APIError>) -> some View {
        switch result {
        case .success(let nodes):
            Label(l("settings.ok", ["value": String(nodes)]), systemImage: "checkmark.circle.fill")
                .foregroundStyle(Theme.ok)
        case .failure(let error):
            Label(Self.message(for: error, l), systemImage: "wifi.slash")
                .foregroundStyle(Theme.critical)
        }
    }

    /// Ошибка проверки связи словами, а не `String(describing:)`.
    static func message(for error: APIError, _ l: L10n) -> String {
        switch error {
        case .offline: l("settings.fail.offline")
        case .notFound: l("settings.fail.notFound")
        case .http(let code): l("settings.fail.http", ["code": String(code)])
        case .decoding: l("settings.fail.decoding")
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
