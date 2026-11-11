import MCCore
import SwiftUI

/// Действия с грузом аккаунта в карточке: «Отметить событие» — если есть узлы с правом
/// (`eventNodes`), «Изменить груз» и «Открыть клиенту» — при `canManage`.
struct AccountActionsSection: View {
    let account: AccountModel
    let mine: MyShipment
    let segments: [RouteSegment]?
    let labels: Labels
    @Environment(\.l10n) private var l
    @State private var showEdit = false
    @State private var showShare = false

    var body: some View {
        if !mine.eventNodes.isEmpty || mine.canManage {
            Section {
                if !EventDraft.nodeChoices(mine).isEmpty {
                    NavigationLink {
                        MarkEventView(account: account, mine: mine, segments: segments, labels: labels)
                    } label: {
                        Label(l("card.markEvent"), systemImage: "mappin.and.ellipse")
                    }
                    .accessibilityIdentifier("card.markEvent")
                }
                if mine.canManage {
                    Button {
                        showEdit = true
                    } label: {
                        Label(l("card.edit"), systemImage: "square.and.pencil")
                    }
                    .accessibilityIdentifier("card.edit")
                    Button {
                        showShare = true
                    } label: {
                        Label(l("card.shareClient"), systemImage: "person.2")
                    }
                    .accessibilityIdentifier("card.shareClient")
                }
            }
            .sheet(isPresented: $showEdit) {
                EditShipmentView(account: account, mine: mine, segments: segments, labels: labels)
            }
            .sheet(isPresented: $showShare) {
                ShareShipmentView(account: account, mine: mine)
            }
        }
    }
}
