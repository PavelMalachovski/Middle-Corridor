import MCCore
import SwiftUI

/// «Открыть клиенту» (`canManage`): компания-клиент из тех, что администратор платформы связал
/// с экспедитором (`/orgs/{id}/clients`). Клиент видит груз только для чтения.
struct ShareShipmentView: View {
    let account: AccountModel
    let mine: MyShipment
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @State private var clients: [OrgSummary]?
    @State private var shared: Set<Int> = []
    @State private var busy: Int?
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                if let clients {
                    if clients.isEmpty {
                        Section {
                            Text(l("share.empty"))
                                .foregroundStyle(.secondary)
                                .accessibilityIdentifier("share.empty")
                        }
                    } else {
                        Section {
                            ForEach(clients) { client in row(client) }
                        } footer: {
                            Text(l("share.hint"))
                        }
                    }
                } else if error == nil {
                    Section { ProgressView() }
                }
                if let error { FormErrorSection(text: error) }
            }
            .navigationTitle(l("share.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button(l("common.done")) { dismiss() }.accessibilityIdentifier("share.done")
                }
            }
            .task { await load() }
        }
    }

    private func row(_ client: OrgSummary) -> some View {
        Button {
            // занято сразу, до задачи: двойное нажатие не отправит второй запрос
            guard busy == nil, !shared.contains(client.id) else { return }
            busy = client.id
            Task { await share(client) }
        } label: {
            HStack {
                Text(client.name).foregroundStyle(.primary)
                Spacer()
                if busy == client.id {
                    ProgressView()
                } else if shared.contains(client.id) {
                    Label(l("share.done"), systemImage: "checkmark.circle.fill")
                        .labelStyle(.titleAndIcon)
                        .font(.footnote)
                        .foregroundStyle(Theme.ok)
                }
            }
        }
        .disabled(busy != nil || shared.contains(client.id))
        .accessibilityIdentifier("share.client.\(client.id)")
    }

    private func load() async {
        do {
            clients = try await account.clients(orgId: mine.orgId)
        } catch {
            self.error = l.accountError(error)
        }
    }

    /// `busy` ставит нажатие (синхронно), здесь — только снимаем.
    private func share(_ client: OrgSummary) async {
        defer { busy = nil }
        error = nil
        do {
            try await account.share(ref: mine.shipment.ref, orgId: client.id)
            shared.insert(client.id)
        } catch {
            self.error = l.accountError(error)
        }
    }
}
