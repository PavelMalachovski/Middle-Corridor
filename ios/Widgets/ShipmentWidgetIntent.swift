import AppIntents
import WidgetKit

/// Настройки виджета («Изменить виджет»): номер груза и адрес сервера. На iPhone без App Group —
/// единственный способ сказать виджету, что показывать.
struct ShipmentWidgetIntent: WidgetConfigurationIntent {
    static let title: LocalizedStringResource = "Груз"
    static let description = IntentDescription("Статус груза в Среднем коридоре")

    @Parameter(title: "Номер груза")
    var ref: String?

    @Parameter(title: "Сервер", default: "http://localhost:8000")
    var server: String?
}
