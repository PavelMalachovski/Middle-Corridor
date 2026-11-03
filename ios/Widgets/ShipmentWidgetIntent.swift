import AppIntents
import WidgetKit

/// Настройки виджета («Изменить виджет»): номер груза и адрес сервера. На iPhone без App Group —
/// единственный способ сказать виджету, что показывать.
struct ShipmentWidgetIntent: WidgetConfigurationIntent {
    static let title: LocalizedStringResource = "Груз"
    static let description = IntentDescription("Статус груза в Среднем коридоре")

    @Parameter(title: "Номер груза")
    var ref: String?

    // значение по умолчанию — литерал (метаданные App Intents собираются при компиляции);
    // держать равным AppGroup.defaultServer
    @Parameter(title: "Сервер", default: "https://middle-corridor-weld.vercel.app")
    var server: String?
}
