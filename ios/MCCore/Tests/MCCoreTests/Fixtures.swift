import Foundation
import XCTest
@testable import MCCore

/// Фикстуры сняты с мок-бэкенда (MOCK_DATA=true) на 31.10.2026 скриптом `ios/scripts/patch_fixtures.py`.
/// Демо — два груза: MC-26-0501 (такт «шторм»: ждёт в Аляте, запрет в Актау, очередь) и
/// MC-26-0431 (санкции: flagged). `MC-26-0501_ferry` — публичный 0501 на «Shahdag» (AIS).
enum Fixture {
    static func data(_ name: String) throws -> Data {
        let url = try XCTUnwrap(
            Bundle.module.url(forResource: name, withExtension: "json", subdirectory: "Fixtures"),
            "нет фикстуры \(name).json"
        )
        return try Data(contentsOf: url)
    }

    static func shipment(_ ref: String) throws -> Shipment {
        try APIDate.makeDecoder().decode(Shipment.self, from: data("shipment_\(ref)"))
    }

    static func snapshot() throws -> MapSnapshot {
        try APIDate.makeDecoder().decode(MapSnapshot.self, from: data("snapshot"))
    }

    /// Статус «проверить вручную»: в демо его нет (как и в бэкенде — тест на своём плане),
    /// поэтому — 0431 со строкой пакинг-листа из бэкенд-теста review (процессоры CN, только код CHPL).
    static func review() throws -> Shipment {
        var s = try shipment("MC-26-0431")
        let match = #"{"line_no": 1, "hs_code": "8542310001", "description": "Микросхемы-процессоры", "description_en": "Processor integrated circuits", "origin_country": "CN", "list_id": "chpl", "list_code": "854231", "ref": "Tier 1", "measure": "export_ban", "strong": false, "reason_code": "code_only"}"#
        s.sanctions?.status = Coded(.review)
        s.sanctions?.matches = [try APIDate.makeDecoder().decode(SanctionsMatch.self, from: Data(match.utf8))]
        return s
    }
}
