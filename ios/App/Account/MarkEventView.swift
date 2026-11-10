import MCCore
import SwiftUI

/// «Отметить событие»: узел (только из `eventNodes` и маршрута), вид — прибыл / убыл / стоит
/// (причина из списка) / снят со стоянки, время (по умолчанию «сейчас», не в будущем), судно —
/// только если следующее плечо из узла морское, примечание. После записи — назад в карточку.
struct MarkEventView: View {
    let account: AccountModel
    let mine: MyShipment
    let segments: [RouteSegment]?
    let labels: Labels
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @State private var draft: EventDraft
    @State private var time = Date.now
    @State private var busy = false
    @State private var error: String?

    init(account: AccountModel, mine: MyShipment, segments: [RouteSegment]?, labels: Labels) {
        self.account = account
        self.mine = mine
        self.segments = segments
        self.labels = labels
        let choices = EventDraft.nodeChoices(mine)
        // по умолчанию — узел, где груз сейчас (если он в правах), иначе первый доступный
        let current = mine.shipment.checkpoints.first { $0.state.known == .current }?.code
        let node = current.flatMap { choices.contains($0) ? $0 : nil } ?? choices.first ?? ""
        _draft = State(initialValue: EventDraft(node: node))
    }

    private var choices: [String] { EventDraft.nodeChoices(mine) }
    private var route: [String] { RouteEdit.route(mine.shipment) }
    private var vesselAllowed: Bool {
        segments.map { RouteGraph(segments: $0).nextLegIsSea(from: draft.node, route: route) } ?? false
    }

    var body: some View {
        Form {
            Section(l("event.node")) {
                if choices.count > 1 {
                    Picker(l("event.node"), selection: $draft.node) {
                        ForEach(choices, id: \.self) { Text(labels.nodeName($0)).tag($0) }
                    }
                    .accessibilityIdentifier("event.node")
                } else {
                    Text(labels.nodeName(draft.node)).accessibilityIdentifier("event.node")
                }
            }
            Section(l("event.kind")) {
                Picker(l("event.kind"), selection: $draft.kind) {
                    ForEach(CheckpointKind.allCases, id: \.self) { kind in
                        Text(l("event.kind.\(kind.rawValue)")).tag(kind)
                    }
                }
                .pickerStyle(.inline)
                .labelsHidden()
            }
            if draft.kind == .held {
                Section {
                    Picker(l("event.hold"), selection: $draft.hold) {
                        ForEach(HoldCode.allCases, id: \.self) { code in
                            Text(labels.holdChoice(code)).tag(HoldCode?.some(code))
                        }
                    }
                    .pickerStyle(.inline)
                    .labelsHidden()
                } header: {
                    Text(l("event.hold"))
                } footer: {
                    if draft.hold == .other { Text(l("event.hold.otherHint")) }
                }
            }
            Section {
                DatePicker(l("event.time"), selection: $time, in: ...Date.now)
                    .accessibilityIdentifier("event.time")
                if vesselAllowed {
                    TextField(l("event.vessel"), text: $draft.vessel)
                        .autocorrectionDisabled()
                        .accessibilityIdentifier("event.vessel")
                }
                TextField(l(draft.hold == .other && draft.kind == .held ? "event.note.required" : "event.note"),
                    text: $draft.note, axis: .vertical)
                    .lineLimit(1...4)
                    .accessibilityIdentifier("event.note")
            } footer: {
                if draft.note.count > EventDraft.noteMax {
                    Text(l("account.error.note_too_long")).foregroundStyle(Theme.critical)
                }
            }
            if let error { FormErrorSection(text: error) }
        }
        .navigationTitle(l("event.title"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .confirmationAction) {
                SubmitToolbarButton(
                    title: l("event.submit"), busy: busy, enabled: draft.canSubmit && !draft.node.isEmpty,
                    id: "event.submit"
                ) {
                    Task { await submit() }
                }
            }
        }
        .onChange(of: time) { draft.occurredAt = time }
        .onChange(of: draft.kind) {
            if draft.kind != .held { draft.hold = nil }
        }
    }

    private func submit() async {
        guard draft.canSubmit, !busy else { return }
        busy = true
        defer { busy = false }
        error = nil
        do {
            try await account.addEvent(ref: mine.shipment.ref, draft.input(vesselAllowed: vesselAllowed))
            dismiss()
        } catch {
            self.error = l.accountError(error)
        }
    }
}
