import MCCore
import SwiftUI

/// Добавление груза: номер руками, из буфера или ссылкой.
///
/// Вставка — системной `PasteButton`: она не вызывает запрос «Разрешить вставку?» (его показывает
/// чтение `UIPasteboard` в коде). Номер проверяется при вводе: «Добавить» активна, когда он распознан.
struct AddShipmentView: View {
    let store: TrackedShipments
    let onAdded: (String) -> Void
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @State private var input = ""
    @State private var error: AddError?
    @State private var busy = false
    @FocusState private var focused: Bool

    /// Номер, найденный в строке (в ссылке оператора тоже — `parse` ищет его в любом месте).
    private var recognized: String? { ShipmentRef.parse(input) }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    HStack {
                        TextField(l("add.placeholder"), text: $input)
                            .textInputAutocapitalization(.characters)
                            .autocorrectionDisabled()
                            .keyboardType(.asciiCapable)
                            .submitLabel(.done)
                            .focused($focused)
                            .onSubmit(add)
                            .accessibilityIdentifier("add.field")
                        // «формат верный» не спорит с ошибкой: после ответа «не найден» галочку прячем
                        if recognized != nil, error == nil {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(Theme.ok)
                                .accessibilityHidden(true)
                        }
                    }
                    PasteButton(payloadType: String.self) { strings in
                        input = strings.first ?? ""
                    }
                    .labelStyle(.titleAndIcon)
                    .accessibilityIdentifier("add.paste")
                } footer: {
                    footer
                }
            }
            .navigationTitle(l("add.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(l("add.cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    if busy {
                        ProgressView()
                    } else {
                        Button(l("add.submit"), action: add)
                            .disabled(recognized == nil)
                            .accessibilityIdentifier("add.submit")
                    }
                }
            }
            .onChange(of: input) { error = nil }
            .onAppear { focused = true }
            .sensoryFeedback(.error, trigger: error) { _, new in new != nil }
        }
    }

    @ViewBuilder
    private var footer: some View {
        if let error {
            Text(Self.message(for: error, l))
                .foregroundStyle(Theme.critical)
                .accessibilityIdentifier("add.error")
        } else if let ref = recognized {
            Text(l("add.recognized", ["ref": ref]))
                .foregroundStyle(Theme.ok)
                .accessibilityIdentifier("add.recognized")
        } else {
            Text(l("add.hint"))
        }
    }

    private func add() {
        guard !busy, recognized != nil else { return }
        busy = true
        Task {
            defer { busy = false }
            do {
                let ref = try await store.add(input)
                onAdded(ref)
            } catch {
                self.error = (error as? AddError) ?? .server
            }
        }
    }

    static func message(for error: AddError, _ l: L10n) -> String {
        switch error {
        case .invalidRef: l("add.error.invalidRef")
        case .notFound: l("add.error.notFound")
        case .offline: l("add.error.offline")
        case .server: l("add.error.server")
        }
    }
}
