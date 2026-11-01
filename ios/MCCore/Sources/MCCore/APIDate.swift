import Foundation

/// Даты `/api/v1`: ISO 8601 в UTC, часто с микросекундами (`2026-10-31T11:08:54.312620Z`).
///
/// `ISO8601DateFormatter` больше трёх знаков дробной части не разбирает, а сам он
/// не Sendable — поэтому свой разбор без форматтеров, одинаковый на iOS и Linux.
public enum APIDate {
    /// `YYYY-MM-DDTHH:MM:SS[.ffffff][Z|±HH:MM|±HHMM|±HH]`; без пояса — UTC.
    public static func parse(_ string: String) -> Date? {
        let b = Array(string.utf8)
        guard b.count >= 19,
            b[4] == UInt8(ascii: "-"), b[7] == UInt8(ascii: "-"),
            b[10] == UInt8(ascii: "T") || b[10] == UInt8(ascii: " ") || b[10] == UInt8(ascii: "t"),
            b[13] == UInt8(ascii: ":"), b[16] == UInt8(ascii: ":"),
            let year = digits(b, 0, 4), let month = digits(b, 5, 2), let day = digits(b, 8, 2),
            let hour = digits(b, 11, 2), let minute = digits(b, 14, 2), let second = digits(b, 17, 2),
            (1...12).contains(month), (1...31).contains(day),
            (0...23).contains(hour), (0...59).contains(minute), (0...60).contains(second)
        else { return nil }

        var i = 19
        var fraction = 0.0
        if i < b.count, b[i] == UInt8(ascii: ".") {
            i += 1
            let start = i
            var scale = 0.1
            while i < b.count, let d = digit(b[i]) {
                fraction += Double(d) * scale
                scale /= 10
                i += 1
            }
            guard i > start else { return nil }
        }

        var offset = 0
        if i < b.count {
            switch b[i] {
            case UInt8(ascii: "Z"), UInt8(ascii: "z"):
                i += 1
            case UInt8(ascii: "+"), UInt8(ascii: "-"):
                let sign = b[i] == UInt8(ascii: "-") ? -1 : 1
                guard let hh = digits(b, i + 1, 2) else { return nil }
                i += 3
                if i < b.count, b[i] == UInt8(ascii: ":") { i += 1 }
                var mm = 0
                if i < b.count {
                    guard let m = digits(b, i, 2) else { return nil }
                    mm = m
                    i += 2
                }
                offset = sign * (hh * 3600 + mm * 60)
            default:
                return nil
            }
        }
        guard i == b.count else { return nil }

        let days = daysFromCivil(year: year, month: month, day: day)
        let seconds = days * 86_400 + hour * 3600 + minute * 60 + second - offset
        return Date(timeIntervalSince1970: Double(seconds) + fraction)
    }

    /// Обратное к `parse`: UTC с `Z`, микросекунды — только если они есть.
    public static func format(_ date: Date) -> String {
        let t = date.timeIntervalSince1970
        var seconds = Int(t.rounded(.down))
        var micros = Int(((t - Double(seconds)) * 1_000_000).rounded())
        if micros >= 1_000_000 {
            seconds += 1
            micros -= 1_000_000
        }
        let days = seconds >= 0 ? seconds / 86_400 : (seconds - 86_399) / 86_400
        let rest = seconds - days * 86_400
        let (y, m, d) = civilFromDays(days)
        var out = String(format: "%04ld-%02ld-%02ldT%02ld:%02ld:%02ld", y, m, d, rest / 3600, rest % 3600 / 60, rest % 60)
        if micros > 0 { out += String(format: ".%06ld", micros) }
        return out + "Z"
    }

    public static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            guard let date = parse(raw) else {
                throw DecodingError.dataCorruptedError(
                    in: container, debugDescription: "не дата ISO 8601: \(raw)")
            }
            return date
        }
        return decoder
    }

    public static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .custom { date, encoder in
            var container = encoder.singleValueContainer()
            try container.encode(format(date))
        }
        return encoder
    }

    // MARK: - Календарь (Howard Hinnant, «chrono-compatible low-level date algorithms»)

    static func daysFromCivil(year: Int, month: Int, day: Int) -> Int {
        let y = month <= 2 ? year - 1 : year
        let era = (y >= 0 ? y : y - 399) / 400
        let yoe = y - era * 400
        let mp = (month + 9) % 12
        let doy = (153 * mp + 2) / 5 + day - 1
        let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy
        return era * 146_097 + doe - 719_468
    }

    static func civilFromDays(_ days: Int) -> (year: Int, month: Int, day: Int) {
        let z = days + 719_468
        let era = (z >= 0 ? z : z - 146_096) / 146_097
        let doe = z - era * 146_097
        let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365
        let doy = doe - (365 * yoe + yoe / 4 - yoe / 100)
        let mp = (5 * doy + 2) / 153
        let day = doy - (153 * mp + 2) / 5 + 1
        let month = mp < 10 ? mp + 3 : mp - 9
        let year = yoe + era * 400 + (month <= 2 ? 1 : 0)
        return (year, month, day)
    }

    private static func digit(_ c: UInt8) -> Int? {
        c >= UInt8(ascii: "0") && c <= UInt8(ascii: "9") ? Int(c - UInt8(ascii: "0")) : nil
    }

    private static func digits(_ b: [UInt8], _ from: Int, _ count: Int) -> Int? {
        guard from >= 0, from + count <= b.count else { return nil }
        var value = 0
        for i in from..<(from + count) {
            guard let d = digit(b[i]) else { return nil }
            value = value * 10 + d
        }
        return value
    }
}
