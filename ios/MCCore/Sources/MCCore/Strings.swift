// Подписи для данных бэкенда — дословно ключи web/src/i18n/{ru,en}.ts, чтобы
// приложение и сайт говорили одно и то же. Тексты интерфейса — в Localizable.xcstrings.

public enum Lang: String, Sendable, CaseIterable {
    case ru, en
}

enum Strings {
    static let ru: [String: String] = [
        "state.planned": "Ожидает отправления",
        "state.in_transit": "В пути",
        "state.waiting": "Стоянка",
        "state.delivered": "Доставлен",
        "event.departed": "Отправление: {node}",
        "event.arrived": "Прибытие: {node}",
        "event.none": "Ожидает отправления",
        "note.loaded_on_ferry": "погружен на паром «{vessel}»",
        "note.loaded_on_vessel": "погружен на судно «{vessel}»",
        "note.gauge_change_done": "перегруз на колею 1520 завершён",
        "hold.weather_ban": "Погодный запрет на швартовку: {node} — критический ветер",
        "hold.customs_wait": "Таможенное оформление AZ/GE — ожидание досмотра",
        "hold.ferry_loading_wait": "Ожидание погрузки на паром «{vessel}»",
        "hold.ferry_return_wait": "Ожидание парома «{vessel}» с обратного рейса",
        "card.delivered": "Доставлен: {node}",
        "card.routeDone": "Маршрут завершён",
        "card.atNode": "В узле {node}",
        "card.confirmedNext": "Подтверждено событием · далее {node}",
        "card.confirmed": "Подтверждено событием",
        "card.onFerry": "На пароме «{vessel}»",
        "card.legProgress": "{from} → {to}, {pct}% плеча",
        "card.estimate": "Оценка по расписанию ({vehicle}) — живой позиции нет",
        "card.onVessel": "на судне «{vessel}»",
        "card.atSea": "в море",
        "card.byRail": "по железной дороге",
    ]

    static let en: [String: String] = [
        "state.planned": "Awaiting departure",
        "state.in_transit": "In transit",
        "state.waiting": "Waiting",
        "state.delivered": "Delivered",
        "event.departed": "Departure: {node}",
        "event.arrived": "Arrival: {node}",
        "event.none": "Awaiting departure",
        "note.loaded_on_ferry": "loaded onto ferry “{vessel}”",
        "note.loaded_on_vessel": "loaded onto vessel “{vessel}”",
        "note.gauge_change_done": "transloaded to 1520 mm gauge",
        "hold.weather_ban": "Weather berthing ban: {node} — critical wind",
        "hold.customs_wait": "Customs clearance AZ/GE — awaiting inspection",
        "hold.ferry_loading_wait": "Waiting to load onto ferry “{vessel}”",
        "hold.ferry_return_wait": "Waiting for ferry “{vessel}” to return",
        "card.delivered": "Delivered: {node}",
        "card.routeDone": "Route completed",
        "card.atNode": "At {node}",
        "card.confirmedNext": "Confirmed by event · next {node}",
        "card.confirmed": "Confirmed by event",
        "card.onFerry": "On ferry “{vessel}”",
        "card.legProgress": "{from} → {to}, {pct}% of the leg",
        "card.estimate": "Schedule estimate ({vehicle}) — no live position",
        "card.onVessel": "on vessel “{vessel}”",
        "card.atSea": "at sea",
        "card.byRail": "by rail",
    ]

    static func t(_ lang: Lang, _ key: String, _ params: [String: String] = [:]) -> String {
        let table = lang == .ru ? ru : en
        var text = table[key] ?? key
        for (name, value) in params {
            text = text.replacingOccurrences(of: "{\(name)}", with: value)
        }
        return text
    }
}
