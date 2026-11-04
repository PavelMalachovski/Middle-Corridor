import AppIntents
import WidgetKit

/// Настройки виджета («Изменить виджет»): номер груза и адрес сервера. На iPhone без App Group —
/// единственный способ сказать виджету, что показывать.
struct ShipmentWidgetIntent: WidgetConfigurationIntent {
    static let title: LocalizedStringResource = "Груз"
    static let description = IntentDescription("Статус груза в Среднем коридоре")

    @Parameter(title: "Номер груза")
    var ref: String?

    /// Без значения по умолчанию: пустое поле — адрес из приложения (App Group) или сборки
    /// (`BackendConfig`); с литералом виджет всегда ходил бы на него, мимо настроек приложения.
    @Parameter(title: "Сервер")
    var server: String?
}
