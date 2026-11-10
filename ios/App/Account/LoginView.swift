import MCCore
import SwiftUI
import UIKit

/// Вход по коду из письма: e-mail → «Получить код» → 6 цифр → «Войти».
/// Ответ на запрос кода один для любого адреса — экран не подсказывает, приглашён ли он.
struct LoginView: View {
    let account: AccountModel
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var code = ""
    /// Адрес, на который ушёл код; правка e-mail возвращает к первому шагу.
    @State private var sentTo: String?
    @State private var busy = false
    @State private var error: String?
    @FocusState private var focus: Field?

    private enum Field { case email, code }

    var body: some View {
        Form {
            Section {
                TextField(l("login.email"), text: $email)
                    .keyboardType(.emailAddress)
                    .textContentType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .submitLabel(.send)
                    .focused($focus, equals: .email)
                    .onSubmit { Task { await requestCode() } }
                    .accessibilityIdentifier("login.email")
                Button {
                    Task { await requestCode() }
                } label: {
                    progressLabel(l(sentTo == nil ? "login.requestCode" : "login.resend"), active: busy && sentTo == nil)
                }
                .disabled(busy || !Self.looksLikeEmail(email))
                .accessibilityIdentifier("login.requestCode")
            } footer: {
                if sentTo != nil {
                    Text(l("login.sent")).accessibilityIdentifier("login.sent")
                }
            }

            if sentTo != nil {
                Section {
                    TextField(l("login.code"), text: $code)
                        .keyboardType(.numberPad)
                        .textContentType(.oneTimeCode)
                        .focused($focus, equals: .code)
                        .font(.title3.monospacedDigit())
                        .accessibilityIdentifier("login.code")
                    Button {
                        Task { await verify() }
                    } label: {
                        progressLabel(l("login.submit"), active: busy)
                    }
                    .disabled(busy || code.count != 6)
                    .accessibilityIdentifier("login.submit")
                }
            }

            if let error {
                Section {
                    Label(error, systemImage: "exclamationmark.triangle.fill")
                        .foregroundStyle(Theme.critical)
                        .accessibilityElement(children: .ignore)
                        .accessibilityLabel(error)
                        .accessibilityIdentifier("login.error")
                }
            }
        }
        .navigationTitle(l("login.title"))
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { focus = .email }
        .onChange(of: email) {
            if let sentTo, AccountModel.normalize(email) != sentTo {
                self.sentTo = nil
                code = ""
            }
        }
        .onChange(of: code) {
            // только цифры, не длиннее 6 (вставка из письма может принести пробелы)
            let digits = String(code.filter(\.isASCIIDigit).prefix(6))
            if digits != code { code = digits }
        }
    }

    private func progressLabel(_ title: String, active: Bool) -> some View {
        HStack {
            Text(title)
            if active {
                Spacer()
                ProgressView()
            }
        }
    }

    private func requestCode() async {
        guard !busy, Self.looksLikeEmail(email) else { return }
        busy = true
        defer { busy = false }
        error = nil
        do {
            try await account.requestCode(email: email)
            sentTo = AccountModel.normalize(email)
            code = ""
            focus = .code
        } catch {
            self.error = Self.message(for: APIError.from(error), l)
        }
    }

    private func verify() async {
        guard !busy, code.count == 6 else { return }
        busy = true
        defer { busy = false }
        error = nil
        do {
            try await account.verify(email: email, code: code, deviceName: UIDevice.current.name)
            dismiss()
        } catch {
            let error = APIError.from(error)
            self.error = Self.message(for: error, l)
            if error == .unauthorized {
                code = ""  // неверный код — набрать заново
                focus = .code
            }
        }
    }

    static func looksLikeEmail(_ text: String) -> Bool {
        let parts = AccountModel.normalize(text).split(separator: "@", omittingEmptySubsequences: false)
        return parts.count == 2 && !parts[0].isEmpty && parts[1].contains(".")
    }

    static func message(for error: APIError, _ l: L10n) -> String {
        switch error {
        case .unauthorized: l("login.error.code")
        case .offline: l("settings.fail.offline")
        case .rejected: l("login.error.email")
        case .http(let code): l("settings.fail.http", ["code": String(code)])
        case .notFound, .decoding: l("login.error.server")
        }
    }
}

extension Character {
    fileprivate var isASCIIDigit: Bool { isASCII && isNumber }
}
