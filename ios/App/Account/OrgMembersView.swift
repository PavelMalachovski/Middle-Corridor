import MCCore
import SwiftUI

/// «Команда» компании (owner/admin): кто в ней и с какой ролью, приглашения этой сессии,
/// «Пригласить» и «Убрать из компании» (с подтверждением; владельца и себя — нельзя).
struct OrgMembersView: View {
    let account: AccountModel
    let org: MembershipInfo
    let labels: Labels
    /// Узлы коридора из снимка — выбор узлов агента в приглашении.
    let nodeCodes: [String]
    @Environment(\.l10n) private var l
    @State private var members: [OrgMember]?
    @State private var error: String?
    @State private var showInvite = false
    @State private var removing: OrgMember?

    private var invitations: [PendingInvite] { account.invitations[org.orgId] ?? [] }

    var body: some View {
        List {
            if let members {
                Section(l("members.team")) {
                    ForEach(members) { member in memberRow(member) }
                }
            } else if error == nil {
                Section { ProgressView() }
            }
            if !invitations.isEmpty {
                Section(l("members.invited")) {
                    ForEach(invitations) { invite in inviteRow(invite) }
                }
            }
            if let error { FormErrorSection(text: error) }
        }
        .navigationTitle(org.orgName)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Button { showInvite = true } label: { Image(systemName: "person.badge.plus") }
                    .accessibilityLabel(l("invite.title"))
                    .accessibilityIdentifier("members.invite")
            }
        }
        .sheet(isPresented: $showInvite) {
            InviteView(account: account, org: org, labels: labels, nodeCodes: nodeCodes)
        }
        .confirmationDialog(
            l("members.remove.confirm", ["email": removing?.email ?? ""]),
            isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
            titleVisibility: .visible,
            presenting: removing
        ) { member in
            Button(l("members.remove"), role: .destructive) {
                Task { await revoke(member) }
            }
        }
        .task { await load() }
        .refreshable { await load() }
    }

    private func memberRow(_ m: OrgMember) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(m.name ?? m.email)
            if m.name != nil {
                Text(m.email).font(.footnote).foregroundStyle(.secondary)
            }
            Text(roleText(m.role.known, raw: m.role.raw, nodes: m.nodeCodes))
                .font(.footnote)
                .foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("member.\(m.email)")
        .swipeActions(edge: .trailing) {
            if canRemove(m) {
                Button(l("members.remove"), role: .destructive) { removing = m }
            }
        }
    }

    private func inviteRow(_ invite: PendingInvite) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(invite.email)
            Text(roleText(invite.role, raw: invite.role.rawValue, nodes: invite.nodeCodes))
                .font(.footnote)
                .foregroundStyle(.secondary)
            Text(l(invite.mailSent ? "invite.mail.sent" : "invite.mail.failed"))
                .font(.footnote)
                .foregroundStyle(invite.mailSent ? AnyShapeStyle(.secondary) : AnyShapeStyle(Theme.warning))
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("invite.pending.\(invite.email)")
    }

    /// Роль словами; у агента — его узлы (пусто — все узлы маршрутов).
    private func roleText(_ role: AccountRole?, raw: String, nodes: [String]) -> String {
        let text = role.map { l("account.role.\($0.rawValue)") } ?? raw
        guard role == .agent else { return text }
        let where_ = nodes.isEmpty ? l("invite.nodes.all") : nodes.map(labels.nodeName).joined(separator: ", ")
        return "\(text) · \(where_)"
    }

    /// Владельца убирает только администратор платформы; себя — нельзя (выйти — в настройках).
    private func canRemove(_ m: OrgMember) -> Bool {
        m.role.known != .owner && m.userId != account.me?.id
    }

    private func load() async {
        do {
            members = try await account.members(orgId: org.orgId)
            error = nil
        } catch {
            self.error = l.accountError(error)
        }
    }

    private func revoke(_ member: OrgMember) async {
        removing = nil
        do {
            try await account.revoke(orgId: org.orgId, userId: member.userId)
            await load()
        } catch {
            self.error = l.accountError(error)
        }
    }
}
