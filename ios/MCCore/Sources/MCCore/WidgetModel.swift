import Foundation

/// Какой груз показывает виджет: номер из настроек виджета → номер из приложения (App Group,
/// только симулятор) → первый из кэша. Нет ни одного — подсказка «Выберите груз».
public enum WidgetModel {
    public static func resolve(intentRef: String?, sharedRef: String?, cachedRefs: [String]) -> String? {
        if let ref = intentRef.flatMap(ShipmentRef.parse) { return ref }
        if let ref = sharedRef.flatMap(ShipmentRef.parse) { return ref }
        return cachedRefs.first
    }
}
