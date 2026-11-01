import Foundation

/// Номер груза из ввода, буфера обмена и ссылок.
///
/// Формат — как у мока бэкенда: `MC-26-0412` (`[A-Z]{2,4}-\d{2}-\d{3,6}`). Ищется в
/// любом месте строки без учёта регистра — вставка из письма тоже сработает.
public enum ShipmentRef {
    public static func parse(_ input: String) -> String? {
        let pattern = /([A-Za-z]{2,4})-(\d{2})-(\d{3,6})/
        for match in input.matches(of: pattern) {
            // границы слова руками: «XMC-26-0412» или «MC-26-04123456» — не номер
            if match.range.lowerBound > input.startIndex,
                isWordChar(input[input.index(before: match.range.lowerBound)])
            {
                continue
            }
            if match.range.upperBound < input.endIndex, isWordChar(input[match.range.upperBound]) {
                continue
            }
            return String(input[match.range]).uppercased()
        }
        return nil
    }

    /// `mcstatus://s/<номер>` или `https://<любой хост>/?s=<номер>` (как `?s=` сайта).
    public static func from(url: URL) -> String? {
        guard let components = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
            return nil
        }
        switch components.scheme?.lowercased() {
        case "mcstatus":
            guard components.host?.lowercased() == "s" else { return nil }
            return parse(components.path)
        case "https", "http":
            guard let value = components.queryItems?.first(where: { $0.name == "s" })?.value else {
                return nil
            }
            return parse(value)
        default:
            return nil
        }
    }

    /// Ссылка, которая откроет груз на сайте (и в приложении — когда будут Universal Links).
    public static func shareURL(ref: String, base: URL) -> URL {
        var components = URLComponents(url: base, resolvingAgainstBaseURL: false) ?? URLComponents()
        if components.path.isEmpty { components.path = "/" }
        components.queryItems = [URLQueryItem(name: "s", value: ref)]
        return components.url ?? base
    }

    private static func isWordChar(_ c: Character) -> Bool {
        c.isLetter || c.isNumber || c == "_"
    }
}
