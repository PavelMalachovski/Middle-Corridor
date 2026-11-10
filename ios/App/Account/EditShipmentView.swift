import MCCore
import SwiftUI

/// «Изменить груз» (`canManage`): контейнер, тип, описание, план отправления и хвост маршрута —
/// пройденная часть (до последнего узла, где груз уже был) заперта. Уходят только изменённые поля.
struct EditShipmentView: View {
    let account: AccountModel
    let mine: MyShipment
    let segments: [RouteSegment]?
    let labels: Labels
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @State private var container: String
    @State private var containerType: String
    @State private var cargo: String
    @State private var departure: Date
    @State private var route: [String]
    @State private var busy = false
    @State private var error: String?

    private let original: Original

    /// Значения до правки — с ними сравнивается форма.
    private struct Original {
        let container: String
        let containerType: String
        let cargo: String
        let departure: Date
        let route: [String]
    }

    init(account: AccountModel, mine: MyShipment, segments: [RouteSegment]?, labels: Labels) {
        self.account = account
        self.mine = mine
        self.segments = segments
        self.labels = labels
        let s = mine.shipment
        let original = Original(
            container: mine.containerNo ?? s.cargoDetails?.containerNo ?? "",
            containerType: s.cargoDetails?.containerType ?? "",
            cargo: s.cargo,
            departure: s.checkpoints.first?.plannedAt ?? .now,
            route: RouteEdit.route(s))
        self.original = original
        _container = State(initialValue: original.container)
        _containerType = State(initialValue: original.containerType)
        _cargo = State(initialValue: original.cargo)
        _departure = State(initialValue: original.departure)
        _route = State(initialValue: original.route)
    }

    private var graph: RouteGraph? { segments.map(RouteGraph.init(segments:)) }
    private var locked: Int { RouteEdit.lockedCount(mine.shipment) }
    private var containerValid: Bool { ContainerNumber.isValid(container) }
    private var routeValid: Bool { route == original.route || graph?.isValid(route) == true }

    private var patch: ShipmentPatch {
        var patch = ShipmentPatch()
        let no = ContainerNumber.normalize(container)
        if no != ContainerNumber.normalize(original.container) { patch.containerNo = no }
        if containerType != original.containerType {
            patch.containerType = .some(containerType.isEmpty ? nil : containerType)
        }
        let text = cargo.trimmingCharacters(in: .whitespacesAndNewlines)
        if text != original.cargo.trimmingCharacters(in: .whitespacesAndNewlines) {
            patch.cargo = .some(text.isEmpty ? nil : text)
        }
        if departure != original.departure { patch.plannedDepartureAt = departure }
        if route != original.route { patch.route = route }
        return patch
    }

    private var canSubmit: Bool { containerValid && routeValid && patch != ShipmentPatch() && !busy }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(l("new.container.placeholder"), text: $container)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .keyboardType(.asciiCapable)
                        .accessibilityIdentifier("edit.container")
                    Picker(l("new.containerType"), selection: $containerType) {
                        Text(l("new.containerType.none")).tag("")
                        ForEach(typeOptions, id: \.code) { Text($0.title).tag($0.code) }
                    }
                } header: {
                    Text(l("new.container"))
                } footer: {
                    if !containerValid {
                        Text(l("new.container.invalid")).foregroundStyle(Theme.critical)
                    }
                }
                Section(l("new.plan")) {
                    DatePicker(l("new.departure"), selection: $departure)
                }
                Section(l("new.cargo")) {
                    TextField(l("new.cargo.placeholder"), text: $cargo, axis: .vertical)
                        .lineLimit(1...4)
                        .accessibilityIdentifier("edit.cargo")
                }
                routeSection
                if let error { FormErrorSection(text: error) }
            }
            .navigationTitle(l("edit.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(l("add.cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    SubmitToolbarButton(title: l("edit.submit"), busy: busy, enabled: canSubmit, id: "edit.submit") {
                        Task { await submit() }
                    }
                }
            }
        }
    }

    /// Тип с сервера, которого нет в списке, остаётся выбираемым.
    private var typeOptions: [(code: String, title: String)] {
        let known = ContainerTypes.all
        if original.containerType.isEmpty || known.contains(where: { $0.code == original.containerType }) {
            return known
        }
        return known + [(original.containerType, original.containerType)]
    }

    @ViewBuilder
    private var routeSection: some View {
        Section {
            if let graph {
                RouteEditor(route: $route, locked: locked, graph: graph, labels: labels)
            } else {
                Text(route.map(labels.nodeName).joined(separator: " → "))
            }
        } header: {
            Text(l("new.route"))
        } footer: {
            Text(l(graph == nil ? "edit.route.noSnapshot" : "edit.route.hint"))
        }
    }

    private func submit() async {
        guard canSubmit else { return }
        busy = true
        defer { busy = false }
        error = nil
        do {
            try await account.update(ref: mine.shipment.ref, patch)
            dismiss()
        } catch {
            self.error = l.accountError(error)
        }
    }
}
