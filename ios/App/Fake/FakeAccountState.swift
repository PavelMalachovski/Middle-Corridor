#if DEBUG
    import Foundation
    import MCCore

    /// Состояние фейкового сервера аккаунтов: грузы — JSON-словари в формате `/my/shipments`
    /// (так их проще менять, чем неизменяемые модели), команда «Caspian Freight», события.
    actor FakeAccountState {
        static let clientId = 10
        private var list: [[String: Any]]?
        private var records: [String: [[String: Any]]] = [:]
        private var nextNumber = 3
        private var nextEventId = 1
        private var nextInvitation = 1
        private var revoked: Set<Int> = []
        /// Имена и координаты узлов: снимок мока + узлы фикстуры (заводы и порты Европы).
        private var nodes: [String: (name: String, lat: Double, lon: Double)] = [:]

        // MARK: - Грузы

        func shipments() throws -> [MyShipment] {
            try decode(loaded())
        }

        func create(_ new: NewShipment) throws -> MyShipment {
            var list = try loaded()
            guard ContainerNumber.isValid(new.containerNo) else { throw APIError.rejected("bad_container") }
            guard new.route.count >= 2, Set(new.route).count == new.route.count else {
                throw APIError.rejected("bad_route")
            }
            let ref = String(format: "MC-27-%04d", nextNumber)
            nextNumber += 1
            // шаблон — первый груз фикстуры: все поля `Shipment` на месте
            guard var shipment = list.first?["shipment"] as? [String: Any] else { throw APIError.http(500) }
            shipment["ref"] = ref
            shipment["client"] = "Caspian Freight"
            shipment["cargo"] = new.cargo ?? "—"
            shipment["cargo_en"] = NSNull()
            shipment["state"] = "planned"
            for key in ["hold_reason", "hold_code", "hold_node", "hold_vessel", "last_event_kind", "last_event_node",
                "last_event_note_code", "last_event_note_vessel", "last_event_at", "eta_latest", "queue",
                "sanctions", "cargo_details"]
            {
                shipment[key] = NSNull()
            }
            shipment["delay_hours"] = 0.0
            shipment["delay_breakdown"] = [Any]()
            shipment["last_event"] = "Ожидает отправления"
            shipment["progress"] = 0.0
            setRoute(&shipment, new.route, departure: new.plannedDepartureAt, keep: [])
            let entry: [String: Any] = [
                "shipment": shipment, "org_id": new.orgId, "can_manage": true, "event_nodes": new.route,
                "container_no": ContainerNumber.normalize(new.containerNo),
            ]
            list.append(entry)
            self.list = list
            return try decode([entry])[0]
        }

        func update(ref: String, _ patch: ShipmentPatch) throws -> MyShipment {
            var list = try loaded()
            guard let i = list.firstIndex(where: { Self.ref($0) == ref }), list[i]["can_manage"] as? Bool == true,
                var shipment = list[i]["shipment"] as? [String: Any]
            else { throw APIError.notFound }
            if let no = patch.containerNo {
                guard ContainerNumber.isValid(no) else { throw APIError.rejected("bad_container") }
                list[i]["container_no"] = ContainerNumber.normalize(no)
            }
            if let cargo = patch.cargo { shipment["cargo"] = cargo ?? "—" }
            if let route = patch.route {
                guard route.count >= 2, Set(route).count == route.count else { throw APIError.rejected("bad_route") }
                let old = shipment["checkpoints"] as? [[String: Any]] ?? []
                let departure = (old.first?["planned_at"] as? String).flatMap(APIDate.parse) ?? .now
                setRoute(&shipment, route, departure: patch.plannedDepartureAt ?? departure, keep: old)
                list[i]["event_nodes"] = route
            }
            list[i]["shipment"] = shipment
            self.list = list
            return try decode([list[i]])[0]
        }

        // MARK: - События

        func addEvent(ref: String, _ event: CheckpointEventInput) throws -> CheckpointEventRecord {
            var list = try loaded()
            guard let i = list.firstIndex(where: { Self.ref($0) == ref }),
                var shipment = list[i]["shipment"] as? [String: Any]
            else { throw APIError.notFound }
            let allowed = list[i]["event_nodes"] as? [String] ?? []
            guard allowed.contains(event.nodeCode) else { throw APIError.rejected("node_not_allowed") }
            let at = event.occurredAt ?? .now
            guard at <= .now.addingTimeInterval(60) else { throw APIError.rejected("in_future") }
            if event.kind == .held, event.holdCode == nil { throw APIError.rejected("hold_code_required") }
            if event.kind == .released, shipment["hold_node"] as? String != event.nodeCode {
                throw APIError.rejected("no_open_hold")
            }
            apply(event, at: at, to: &shipment)
            list[i]["shipment"] = shipment
            self.list = list
            let record: [String: Any] = [
                "id": nextEventId, "kind": event.kind.rawValue, "node_code": event.nodeCode,
                "occurred_at": APIDate.format(at), "hold_code": event.holdCode ?? NSNull(),
                "note": event.note ?? NSNull(), "vessel": event.vessel ?? NSNull(), "source": "manual",
                "created_by": 1, "supersedes_id": NSNull(), "created_at": APIDate.format(.now), "superseded": false,
            ]
            nextEventId += 1
            records[ref, default: []].append(record)
            return try APIDate.makeDecoder().decode(
                CheckpointEventRecord.self, from: JSONSerialization.data(withJSONObject: record))
        }

        func events(ref: String) throws -> [CheckpointEventRecord] {
            try APIDate.makeDecoder().decode(
                [CheckpointEventRecord].self, from: JSONSerialization.data(withJSONObject: records[ref] ?? []))
        }

        // MARK: - Команда

        func members(selfEmail: String) throws -> [OrgMember] {
            let all: [[String: Any]] = [
                ["user_id": 1, "email": selfEmail, "name": NSNull(), "role": "owner", "node_codes": [String]()],
                [
                    "user_id": 3, "email": "dispatch@caspian.example", "name": "Айгерим", "role": "admin",
                    "node_codes": [String](),
                ],
                ["user_id": 4, "email": "poti@caspian.example", "name": NSNull(), "role": "agent", "node_codes": ["POTI"]],
            ]
            let visible = all.filter { !revoked.contains($0["user_id"] as? Int ?? 0) }
            return try APIDate.makeDecoder().decode([OrgMember].self, from: JSONSerialization.data(withJSONObject: visible))
        }

        /// Адрес с «fail» — письмо «не ушло» (проверка текста «Приглашение создано, письмо не ушло»).
        func invite(email: String) throws -> Invitation {
            defer { nextInvitation += 1 }
            let json: [String: Any] = ["invitation_id": nextInvitation, "mail": email.contains("fail") ? "failed" : "sent"]
            return try APIDate.makeDecoder().decode(Invitation.self, from: JSONSerialization.data(withJSONObject: json))
        }

        func revoke(userId: Int) throws {
            guard userId != 1 else { throw APIError.rejected("last_owner") }
            revoked.insert(userId)
        }

        // MARK: - Внутреннее

        private static func ref(_ entry: [String: Any]) -> String? {
            (entry["shipment"] as? [String: Any])?["ref"] as? String
        }

        private func decode(_ list: [[String: Any]]) throws -> [MyShipment] {
            try APIDate.makeDecoder().decode([MyShipment].self, from: JSONSerialization.data(withJSONObject: list))
        }

        /// Фикстура → два груза: «Caspian Freight» (владелец) и копия для агента Актау без стоянки.
        private func loaded() throws -> [[String: Any]] {
            if let list { return list }
            guard let url = Bundle.main.url(forResource: "my_shipments", withExtension: "json"),
                let fixture = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [[String: Any]],
                var first = fixture.first, var shipment = first["shipment"] as? [String: Any]
            else { throw APIError.http(500) }
            loadNodes(shipment)
            shipment["client"] = "Caspian Freight"
            first["shipment"] = shipment
            var second = first
            shipment["ref"] = "MC-27-0002"
            shipment["client"] = "Aktau Port Agency"
            // стоит в Актау без причины — причину отмечает агент (UI-тест «Отметить событие»)
            shipment["hold_code"] = NSNull()
            shipment["hold_node"] = NSNull()
            shipment["hold_reason"] = NSNull()
            second["shipment"] = shipment
            second["org_id"] = 2
            second["can_manage"] = false
            second["event_nodes"] = ["AKTAU"]
            list = [first, second]
            return [first, second]
        }

        private func loadNodes(_ shipment: [String: Any]) {
            for c in shipment["checkpoints"] as? [[String: Any]] ?? [] {
                if let code = c["code"] as? String, let name = c["name"] as? String {
                    nodes[code] = (name, c["lat"] as? Double ?? 0, c["lon"] as? Double ?? 0)
                }
            }
            guard let url = Bundle.main.url(forResource: "snapshot", withExtension: "json"),
                let data = try? Data(contentsOf: url),
                let snapshot = try? APIDate.makeDecoder().decode(MapSnapshot.self, from: data)
            else { return }
            for n in snapshot.nodes { nodes[n.code] = (n.name, n.lat, n.lon) }
        }

        private func name(_ code: String) -> String { nodes[code]?.name ?? code }

        /// Новые точки маршрута — план по суткам на плечо; узлы, что были в старом маршруте, — как были.
        private func setRoute(_ s: inout [String: Any], _ route: [String], departure: Date, keep: [[String: Any]]) {
            let old = Dictionary(keep.compactMap { c in (c["code"] as? String).map { ($0, c) } }) { a, _ in a }
            s["checkpoints"] = route.enumerated().map { i, code -> [String: Any] in
                if let existing = old[code] { return existing }
                let node = nodes[code] ?? (code, 0, 0)
                return [
                    "code": code, "name": node.name, "lat": node.lat, "lon": node.lon,
                    "planned_at": APIDate.format(departure.addingTimeInterval(Double(i) * 86_400)),
                    "actual_at": NSNull(), "state": "planned",
                ]
            }
            s["track"] = route.map { [nodes[$0]?.lon ?? 0, nodes[$0]?.lat ?? 0] }
            s["origin"] = name(route[0])
            s["origin_code"] = route[0]
            s["destination"] = name(route[route.count - 1])
            s["destination_code"] = route[route.count - 1]
            s["eta"] = APIDate.format(departure.addingTimeInterval(Double(route.count - 1) * 86_400))
            if keep.isEmpty {
                let first = nodes[route[0]] ?? (route[0], 0, 0)
                s["position"] = [
                    "lat": first.lat, "lon": first.lon, "heading": NSNull(), "confirmed": false, "source": "projection",
                    "on_vessel": NSNull(), "mode": NSNull(), "from_code": route[0], "to_code": route[1],
                    "leg_progress": 0.0,
                ]
            }
        }

        /// Событие в проекции — как у сервера в общих чертах: последнее событие, стоянка, точки маршрута.
        private func apply(_ e: CheckpointEventInput, at: Date, to s: inout [String: Any]) {
            let titles: [CheckpointKind: String] = [
                .arrived: "Прибытие", .departed: "Отправление", .held: "Стоянка", .released: "Стоянка снята",
            ]
            s["last_event"] = "\(titles[e.kind] ?? ""): \(name(e.nodeCode))"
            s["last_event_kind"] = e.kind.rawValue
            s["last_event_node"] = e.nodeCode
            s["last_event_note_code"] = NSNull()
            s["last_event_at"] = APIDate.format(at)
            switch e.kind {
            case .held:
                s["state"] = "waiting"
                s["hold_code"] = e.holdCode == HoldCode.other.rawValue ? NSNull() : (e.holdCode ?? NSNull())
                s["hold_reason"] = e.note ?? NSNull()
                s["hold_node"] = e.nodeCode
                s["hold_vessel"] = e.vessel ?? NSNull()
            case .released, .departed:
                s["state"] = "in_transit"
                for key in ["hold_code", "hold_reason", "hold_node", "hold_vessel"] { s[key] = NSNull() }
            case .arrived:
                s["state"] = "waiting"
            }
            if var checkpoints = s["checkpoints"] as? [[String: Any]],
                let i = checkpoints.firstIndex(where: { $0["code"] as? String == e.nodeCode })
            {
                for j in checkpoints.indices {
                    checkpoints[j]["state"] = j < i ? "done" : j == i ? (e.kind == .departed ? "done" : "current") : "planned"
                }
                checkpoints[i]["actual_at"] = APIDate.format(at)
                s["checkpoints"] = checkpoints
            }
        }
    }
#endif
