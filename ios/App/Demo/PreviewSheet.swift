import MCCore
import SwiftUI

/// Предпросмотр Live Activity и виджета для текущего груза — проверить вид и показать без
/// добавления виджета на домашний экран.
struct PreviewSheet: View {
    let status: LiveStatus?
    @Environment(\.l10n) private var l
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                if let status {
                    VStack(alignment: .leading, spacing: 20) {
                        Text(l("preview.lock")).font(.headline)
                        LiveStatusLockView(status: status, lang: l.lang)
                            .padding()
                            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 22))
                            .accessibilityElement(children: .combine)
                            .accessibilityIdentifier("preview.live")

                        Text(l("preview.island")).font(.headline)
                        HStack {
                            Image(systemName: LiveStatusStyle.icon(status)).foregroundStyle(Theme.tone(status.tone))
                            Spacer()
                            Text(LiveStatusStyle.etaShort(status, lang: l.lang)).font(.caption).foregroundStyle(.white)
                        }
                        .padding(.horizontal, 16)
                        .frame(width: 250, height: 36)
                        .background(.black, in: Capsule())
                        .frame(maxWidth: .infinity)

                        Text(l("preview.widget")).font(.headline)
                        HStack(alignment: .top, spacing: 16) {
                            widget(status, .small).frame(width: 158, height: 158)
                            Spacer(minLength: 0)
                        }
                        widget(status, .medium).frame(height: 158)
                            .accessibilityElement(children: .combine)
                            .accessibilityIdentifier("preview.widget")
                    }
                    .padding()
                } else {
                    ContentUnavailableView(l("preview.empty"), systemImage: "shippingbox")
                }
            }
            .navigationTitle(l("preview.title"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button(l("settings.done")) { dismiss() } }
            }
        }
    }

    private func widget(_ status: LiveStatus, _ family: WidgetFamilyKind) -> some View {
        ShipmentWidgetContent(status: status, lang: l.lang, note: nil, family: family)
            .padding(14)
            .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 22))
    }
}
