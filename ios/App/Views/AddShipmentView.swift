import MCCore
import SwiftUI
import UIKit

/// Добавление груза: номер руками, из буфера или ссылкой.
struct AddShipmentView: View {
    let store: TrackedShipments
    let onAdded: (String) -> Void
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @State private var input = ""
    @State private var error: AddError?
    @State private var busy = false
    @FocusState private var focused: Bool

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(l("add.placeholder"), text: $input)
                        .textInputAutocapitalization(.characters)
                        .autocorrectionDisabled()
                        .keyboardType(.asciiCapable)
                        .submitLabel(.done)
                        .focused($focused)
                        .onSubmit(add)
                        .accessibilityIdentifier("add.field")
                    Button {
                        if let text = UIPasteboard.general.string { input = text }
                    } label: {
                        Label(l("add.paste"), systemImage: "doc.on.clipboard")
                    }
                } footer: {
                    if let error {
                        Text(Self.message(for: error, l))
                            .foregroundStyle(Theme.critical)
                            .accessibilityIdentifier("add.error")
                    } else {
                        Text(l("add.hint"))
                    }
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
                            .disabled(input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            .accessibilityIdentifier("add.submit")
                    }
                }
            }
            .onChange(of: input) { error = nil }
            .onAppear { focused = true }
        }
    }

    private func add() {
        guard !busy else { return }
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
