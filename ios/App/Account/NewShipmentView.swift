import MCCore
import SwiftUI

/// Типы контейнеров в формах (уходят строкой `container_type`; подпись — размер).
enum ContainerTypes {
    static let all: [(code: String, title: String)] = [
        ("20GP", "20′"), ("40GP", "40′"), ("40HC", "40′ HC"), ("45HC", "45′ HC"),
    ]
}

/// «Новый груз» (экспедитор, owner/admin): компания (если их несколько), контейнер с проверкой
/// ISO 6346, маршрут — пресет или узлы по плечам из снимка, план отправления, описание груза.
/// Номер груза выдаёт сервер; после создания открывается его карточка.
struct NewShipmentView: View {
    let account: AccountModel
    /// Плечи коридора из уже загруженного снимка; nil — только пресеты.
    let segments: [RouteSegment]?
    let labels: Labels
    let onCreated: (MyShipment) -> Void
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @State private var orgId: Int?
    @State private var container = ""
    @State private var containerType = ""
    @State private var choice = RouteChoice.europeToKazakhstan
    @State private var manual: [String] = []
    @State private var departure = NewShipmentView.defaultDeparture()
    @State private var cargo = ""
    @State private var busy = false
    @State private var error: String?

    private enum RouteChoice: String, CaseIterable, Identifiable {
        case europeToKazakhstan, chinaToEurope, manual
        var id: String { rawValue }
    }

    private var graph: RouteGraph? { segments.map(RouteGraph.init(segments:)) }
    private var orgs: [MembershipInfo] { account.creatableOrgs }
    private var containerValid: Bool { ContainerNumber.isValid(container) }

    private var route: [String] {
        switch choice {
        case .europeToKazakhstan: RoutePreset.europeToKazakhstan.codes
        case .chinaToEurope: RoutePreset.chinaToEurope.codes
        case .manual: manual
        }
    }

    private var routeValid: Bool {
        choice == .manual ? graph?.isValid(manual) == true : route.count >= 2
    }

    private var canSubmit: Bool { selectedOrg != nil && containerValid && routeValid && !busy }
    private var selectedOrg: Int? { orgId ?? (orgs.count == 1 ? orgs.first?.orgId : nil) }

    var body: some View {
        NavigationStack {
            Form {
                if orgs.count > 1 {
                    Section(l("new.company")) {
                        Picker(l("new.company"), selection: $orgId) {
                            Text(l("new.company.choose")).tag(Int?.none)
                            ForEach(orgs, id: \.orgId) { Text($0.orgName).tag(Int?.some($0.orgId)) }
                        }
                        .accessibilityIdentifier("new.company")
                    }
                }
                containerSection
                routeSection
                Section(l("new.plan")) {
                    DatePicker(l("new.departure"), selection: $departure)
                        .accessibilityIdentifier("new.departure")
                }
                Section(l("new.cargo")) {
                    TextField(l("new.cargo.placeholder"), text: $cargo, axis: .vertical)
                        .lineLimit(1...4)
                        .accessibilityIdentifier("new.cargo")
                }
                if let error { FormErrorSection(text: error) }
            }
            .navigationTitle(l("new.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(l("add.cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    SubmitToolbarButton(title: l("new.submit"), busy: busy, enabled: canSubmit, id: "new.submit") {
                        Task { await submit() }
                    }
                }
            }
        }
    }

    private var containerSection: some View {
        Section {
            HStack {
                TextField(l("new.container.placeholder"), text: $container)
                    .textInputAutocapitalization(.characters)
                    .autocorrectionDisabled()
                    .keyboardType(.asciiCapable)
                    .accessibilityIdentifier("new.container")
                if containerValid {
                    Image(systemName: "checkmark.circle.fill").foregroundStyle(Theme.ok).accessibilityHidden(true)
                }
            }
            Picker(l("new.containerType"), selection: $containerType) {
                Text(l("new.containerType.none")).tag("")
                ForEach(ContainerTypes.all, id: \.code) { Text($0.title).tag($0.code) }
            }
        } header: {
            Text(l("new.container"))
        } footer: {
            if !container.isEmpty, !containerValid {
                Text(l("new.container.invalid"))
                    .foregroundStyle(Theme.critical)
                    .accessibilityIdentifier("new.container.invalid")
            }
        }
    }

    private var routeSection: some View {
        Section {
            Picker(l("new.route"), selection: $choice) {
                Text(l("route.preset.europeToKazakhstan")).tag(RouteChoice.europeToKazakhstan)
                Text(l("route.preset.chinaToEurope")).tag(RouteChoice.chinaToEurope)
                if graph != nil { Text(l("route.manual")).tag(RouteChoice.manual) }
            }
            .pickerStyle(.inline)
            .labelsHidden()
            .accessibilityIdentifier("new.route")
            if choice == .manual, let graph {
                RouteEditor(route: $manual, locked: 0, graph: graph, labels: labels)
            }
        } header: {
            Text(l("new.route"))
        } footer: {
            if choice != .manual {
                Text(route.map(labels.nodeName).joined(separator: " → "))
            } else if graph == nil {
                Text(l("route.noSnapshot"))
            }
        }
    }

    private func submit() async {
        guard canSubmit, let orgId = selectedOrg else { return }
        busy = true
        defer { busy = false }
        error = nil
        let text = cargo.trimmingCharacters(in: .whitespacesAndNewlines)
        let new = NewShipment(
            orgId: orgId, containerNo: ContainerNumber.normalize(container),
            containerType: containerType.isEmpty ? nil : containerType, route: route,
            plannedDepartureAt: departure, cargo: text.isEmpty ? nil : text)
        do {
            let created = try await account.create(new)
            onCreated(created)
        } catch {
            self.error = l.accountError(error)
        }
    }

    /// Завтра, 08:00 — типичное начало: удобнее, чем текущая минута.
    private static func defaultDeparture(now: Date = .now) -> Date {
        let tomorrow = Calendar.current.date(byAdding: .day, value: 1, to: now) ?? now
        return Calendar.current.date(bySettingHour: 8, minute: 0, second: 0, of: tomorrow) ?? tomorrow
    }
}
