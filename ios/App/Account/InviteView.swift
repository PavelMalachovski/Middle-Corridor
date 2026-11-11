import MCCore
import SwiftUI

/// Приглашение в компанию: e-mail, роль (администратор / агент / наблюдатель), узлы агента.
/// Ссылок нет — приглашённый входит в приложении кодом из письма на этот адрес.
struct InviteView: View {
    let account: AccountModel
    let org: MembershipInfo
    let labels: Labels
    /// Узлы для агента — из снимка; без снимка — узлы готовых маршрутов.
    var nodeCodes: [String] = []
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var role = AccountRole.agent
    @State private var nodes: Set<String> = []
    @State private var busy = false
    @State private var error: String?

    /// Агенты — только у экспедитора: у клиента нет узлов, где отмечать события.
    private var roles: [AccountRole] {
        org.orgKind.known == .forwarder ? [.admin, .agent, .viewer] : [.admin, .viewer]
    }

    private var choices: [String] {
        if !nodeCodes.isEmpty { return nodeCodes }
        var seen = Set<String>()
        return RoutePreset.allCases.flatMap(\.codes).filter { seen.insert($0).inserted }
    }

    private var canSubmit: Bool { LoginView.looksLikeEmail(email) && !busy }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(l("login.email"), text: $email)
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .accessibilityIdentifier("invite.email")
                } footer: {
                    Text(l("invite.hint"))
                }
                Section(l("invite.role")) {
                    Picker(l("invite.role"), selection: $role) {
                        ForEach(roles, id: \.self) { Text(roleTitle($0)).tag($0) }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                }
                if role == .agent {
                    Section {
                        ForEach(choices, id: \.self) { code in nodeRow(code) }
                    } header: {
                        Text(l("invite.nodes"))
                    } footer: {
                        Text(l("invite.nodes.hint"))
                    }
                }
                if let error { FormErrorSection(text: error) }
            }
            .navigationTitle(l("invite.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(l("add.cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    SubmitToolbarButton(title: l("invite.submit"), busy: busy, enabled: canSubmit, id: "invite.submit") {
                        Task { await submit() }
                    }
                }
            }
            .onAppear {
                if !roles.contains(role) { role = .viewer }
            }
        }
    }

    /// «агент» → «Агент»: в списке выбора — с заглавной.
    private func roleTitle(_ role: AccountRole) -> String {
        let text = l("account.role.\(role.rawValue)")
        return text.prefix(1).uppercased() + text.dropFirst()
    }

    private func nodeRow(_ code: String) -> some View {
        Button {
            if nodes.contains(code) { nodes.remove(code) } else { nodes.insert(code) }
        } label: {
            HStack {
                Text(labels.nodeName(code)).foregroundStyle(.primary)
                Spacer()
                if nodes.contains(code) {
                    Image(systemName: "checkmark").foregroundStyle(Theme.accent)
                }
            }
        }
        .accessibilityIdentifier("invite.node.\(code)")
        .accessibilityAddTraits(nodes.contains(code) ? .isSelected : [])
    }

    private func submit() async {
        guard canSubmit else { return }
        busy = true
        defer { busy = false }
        error = nil
        // узлы — в порядке списка; не агенту узлы не отправляем (сервер: nodes_for_agent_only)
        let codes = role == .agent ? choices.filter(nodes.contains) : []
        do {
            _ = try await account.invite(orgId: org.orgId, email: email, role: role, nodeCodes: codes)
            dismiss()  // письмо не ушло — строка приглашения в «Команде» скажет об этом
        } catch {
            self.error = l.accountError(error)
        }
    }
}
