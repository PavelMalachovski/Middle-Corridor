import MCCore
import SwiftUI

/// «Груз» в карточке: описание, контейнер, места и вес, опасный груз, главные позиции по весу.
/// Стоимости, получателя и пломб тут нет — ответ API публичный.
struct CargoSection: View {
    let cargo: CargoDetails
    let lang: Lang
    @Environment(\.l10n) private var l

    var body: some View {
        Section(l("card.cargoBlock")) {
            VStack(alignment: .leading, spacing: 8) {
                if let text = pick(cargo.description, cargo.descriptionEn) {
                    Text(text).font(.headline)
                }
                ForEach(Array(cargo.dangerous.enumerated()), id: \.offset) { _, dg in
                    Label {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(l("card.cargo.dangerous", ["un": dg.unNumber, "cls": dg.hazardClass]))
                                .fontWeight(.semibold)
                            if let text = pick(dg.description, dg.descriptionEn) {
                                Text(text).font(.footnote).foregroundStyle(.secondary)
                            }
                        }
                    } icon: {
                        Image(systemName: "exclamationmark.triangle.fill")
                    }
                    .foregroundStyle(Theme.warning)
                }
                if let container = containerLine {
                    Text(container).font(.subheadline).monospacedDigit()
                }
                if let packages = cargo.packages {
                    let kind = pick(cargo.packageKind, cargo.packageKindEn) ?? ""
                    Text(l("card.cargo.packages", ["n": String(packages), "kind": kind]))
                        .font(.subheadline)
                }
                if let weight = weightLine {
                    Text(weight).font(.subheadline).monospacedDigit()
                }
                if !cargo.topItems.isEmpty {
                    Divider()
                    ForEach(Array(cargo.topItems.enumerated()), id: \.offset) { _, item in
                        HStack(alignment: .firstTextBaseline) {
                            Text(pick(item.description, item.descriptionEn) ?? item.hsCode)
                            Spacer()
                            if let amount = amountLine(item) {
                                Text(amount).foregroundStyle(.secondary).monospacedDigit()
                            }
                        }
                        .font(.subheadline)
                    }
                    if cargo.moreItems > 0 {
                        Text(l("card.cargo.more", ["n": String(cargo.moreItems)]))
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }
            }
            .padding(.vertical, 2)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier("card.cargo")
        }
    }

    private func pick(_ ru: String?, _ en: String?) -> String? {
        lang == .en ? (en ?? ru) : (ru ?? en)
    }

    private var containerLine: String? {
        switch (cargo.containerNo, cargo.containerType) {
        case let (no?, type?): "\(no) · \(type)"
        case let (no?, nil): no
        case let (nil, type?): type
        case (nil, nil): nil
        }
    }

    private var weightLine: String? {
        switch (cargo.grossKg, cargo.netKg) {
        case let (gross?, net?): l("card.cargo.weight", ["gross": kg(gross), "net": kg(net)])
        case let (gross?, nil): l("card.cargo.gross", ["gross": kg(gross)])
        case let (nil, net?): l("card.cargo.net", ["net": kg(net)])
        case (nil, nil): nil
        }
    }

    private func amountLine(_ item: CargoItem) -> String? {
        switch (item.quantity, item.netKg) {
        case let (qty?, net?): l("card.cargo.item", ["qty": kg(qty), "kg": kg(net)])
        case let (nil, net?): l("card.cargo.itemKg", ["kg": kg(net)])
        case let (qty?, nil): l("card.cargo.itemQty", ["qty": kg(qty)])
        case (nil, nil): nil
        }
    }

    /// Целое с разделителем разрядов по языку: «12 449» / «12,449».
    private func kg(_ value: Double) -> String {
        Int(value.rounded()).formatted(.number.locale(l.locale))
    }
}
