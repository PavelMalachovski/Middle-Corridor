import MCCore
import SwiftUI

// Общие части форм аккаунта: подписи узлов, текст ошибки по коду, строка ошибки, редактор маршрута.

extension Labels {
    /// Имя узла; узла нет в снимке (старый мок, нет сети) — код словами («Mlada Boleslav»).
    func nodeName(_ code: String) -> String {
        node(code) ?? code.replacingOccurrences(of: "_", with: " ").capitalized
    }
}

extension L10n {
    /// Ошибка действия аккаунта словами: 422 — по коду причины, неизвестный код — общий текст.
    func accountError(_ error: any Error) -> String {
        self(AccountErrorKey.key(APIError.from(error)))
    }
}

/// Строка ошибки под формой (её же читает VoiceOver и UI-тест: `account.form.error`).
struct FormErrorSection: View {
    let text: String

    var body: some View {
        Section {
            Label(text, systemImage: "exclamationmark.triangle.fill")
                .foregroundStyle(Theme.critical)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(text)
                .accessibilityIdentifier("account.form.error")
        }
    }
}

/// Кнопка «Готово/Сохранить» в панели: пока идёт запрос — индикатор.
struct SubmitToolbarButton: View {
    let title: String
    let busy: Bool
    let enabled: Bool
    let id: String
    let action: () -> Void

    var body: some View {
        if busy {
            ProgressView()
        } else {
            Button(title, action: action)
                .fontWeight(.semibold)
                .disabled(!enabled)
                .accessibilityIdentifier(id)
        }
    }
}

/// Маршрут узел за узлом: каждый следующий — только сосед последнего по плечам коридора.
/// Первые `locked` узлов не меняются (пройденная часть при правке).
struct RouteEditor: View {
    @Binding var route: [String]
    let locked: Int
    let graph: RouteGraph
    let labels: Labels
    @Environment(\.l10n) private var l

    var body: some View {
        ForEach(Array(route.enumerated()), id: \.offset) { index, code in
            HStack {
                Text("\(index + 1). \(labels.nodeName(code))")
                Spacer()
                if index < locked {
                    Image(systemName: "lock.fill")
                        .foregroundStyle(.secondary)
                        .accessibilityLabel(l("route.locked"))
                }
            }
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("route.node.\(code)")
        }
        let choices = graph.nextChoices(after: route)
        if !choices.isEmpty {
            Menu {
                ForEach(choices, id: \.self) { code in
                    Button(labels.nodeName(code)) { route.append(code) }
                }
            } label: {
                Label(l(route.isEmpty ? "route.addFirst" : "route.addNext"), systemImage: "plus.circle")
            }
            .accessibilityIdentifier("route.add")
        }
        if route.count > locked {
            Button(role: .destructive) {
                route.removeLast()
            } label: {
                Label(l("route.removeLast"), systemImage: "minus.circle")
            }
            .accessibilityIdentifier("route.removeLast")
        }
    }
}
