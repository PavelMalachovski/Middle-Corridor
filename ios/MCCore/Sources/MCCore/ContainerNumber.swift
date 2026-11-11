import Foundation

/// Номер контейнера по ISO 6346 — то же правило, что у сервера
/// (`app.services.accounts.shipments.iso6346_valid`): 4 буквы, 6 цифр серийного номера
/// и контрольная цифра. Только ASCII: «арабско-индийская» цифра номером не считается.
public enum ContainerNumber {
    /// Пробелы убраны, регистр верхний — как отправляется на сервер.
    public static func normalize(_ input: String) -> String {
        String(input.filter { !$0.isWhitespace }).uppercased()
    }

    public static func isValid(_ input: String) -> Bool {
        let code = Array(normalize(input).unicodeScalars)
        guard code.count == 11 else { return false }
        var total = 0
        for (i, scalar) in code.enumerated() {
            let value: Int
            switch i {
            case 0..<4:
                guard let v = letterValue(scalar) else { return false }
                value = v
            default:
                guard scalar.value >= 48, scalar.value <= 57 else { return false }
                value = Int(scalar.value) - 48
            }
            if i < 10 { total += value << i }
        }
        return total % 11 % 10 == Int(code[10].value) - 48
    }

    /// A=10, дальше по возрастанию, пропуская кратные 11.
    private static func letterValue(_ s: Unicode.Scalar) -> Int? {
        guard s.value >= 65, s.value <= 90 else { return nil }
        var n = 10
        for letter in 65...Int(s.value) {
            if n % 11 == 0 { n += 1 }
            if letter == Int(s.value) { return n }
            n += 1
        }
        return nil
    }
}
