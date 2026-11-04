import MCCore
import SwiftUI

/// Заставка «Переправа» поверх приложения при холодном старте: кадр 0 совпадает с экраном
/// запуска (эмблема по центру), дальше рельсы приходят к портам, паром идёт Актау → Алят,
/// проявляется подпись — и всё растворяется. Подпись только английская (решение владельца).
struct SplashView: View {
    /// `-mc.splash hold` (UI-тесты, скриншоты): замереть на полном кадре до тапа.
    var hold = false
    let onFinish: () -> Void

    @State private var start = Date.now
    @State private var skippedAt: Double?

    var body: some View {
        TimelineView(.animation(paused: hold)) { context in
            let t = hold ? SplashTimeline.fullFrameAt : context.date.timeIntervalSince(start)
            let frame = SplashTimeline.frame(at: t, skippedAt: skippedAt)
            GeometryReader { geo in
                scene(frame, in: geo.size)
            }
            .opacity(frame.opacity)
        }
        .ignoresSafeArea()
        .contentShape(Rectangle())
        .onTapGesture(perform: skip)
        .task(id: skippedAt) {
            if hold && skippedAt == nil { return }
            let wait = skippedAt.map { _ in SplashTimeline.skipFade } ?? SplashTimeline.duration
            try? await Task.sleep(for: .seconds(wait))
            if !Task.isCancelled { onFinish() }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Text(verbatim: "Middle Corridor"))
        .accessibilityIdentifier("splash")
    }

    private func skip() {
        guard skippedAt == nil else { return }
        if hold {
            onFinish()
        } else {
            skippedAt = Date.now.timeIntervalSince(start)
        }
    }

    @ViewBuilder
    private func scene(_ frame: SplashFrame, in size: CGSize) -> some View {
        let emblem = CaspianEmblem.size
        // как у экрана запуска: эмблема по центру всего экрана, без учёта safe area
        let origin = CGPoint(x: (size.width - emblem.width) / 2, y: (size.height - emblem.height) / 2)
        ZStack {
            Color("LaunchBackground")
            CaspianEmblem()
                .position(x: size.width / 2, y: size.height / 2)
            Canvas { context, _ in
                Self.drawRails(&context, origin: origin, width: size.width, progress: frame.rails)
                Self.drawFerry(&context, origin: origin, at: frame.ferry, opacity: frame.ferryOpacity)
            }
            VStack(spacing: 6) {
                Text(verbatim: "Middle Corridor")
                    .font(.system(size: 28, weight: .semibold))
                    .foregroundStyle(.white)
                Text(verbatim: "Aktau → Alat")
                    .font(.system(size: 15, weight: .medium))
                    .foregroundStyle(EmblemColor.caption)
            }
            .fixedSize()
            .opacity(frame.wordmark)
            .offset(y: (1 - frame.wordmark) * 6)
            .position(x: size.width / 2, y: origin.y + emblem.height + 44)
        }
    }

    /// Рельсы как в иконке: с востока — в Актау, с запада — в Алят; рисуются от края экрана к порту.
    private static func drawRails(_ context: inout GraphicsContext, origin: CGPoint, width: CGFloat, progress: Double) {
        guard progress > 0 else { return }
        let s = CaspianEmblem.scale
        let a = CGPoint(x: origin.x + CaspianEmblem.aktau.x, y: origin.y + CaspianEmblem.aktau.y)
        let b = CGPoint(x: origin.x + CaspianEmblem.alat.x, y: origin.y + CaspianEmblem.alat.y)
        let cap = CaspianEmblem.railWidth  // скруглённый конец не выглядывает из-за края

        var east = Path()
        east.move(to: CGPoint(x: width + cap, y: a.y - 34 * s))
        east.addLine(to: CGPoint(x: a.x + 64 * s, y: a.y - 34 * s))
        east.addQuadCurve(to: CGPoint(x: a.x, y: a.y + 4 * s), control: CGPoint(x: a.x, y: a.y - 34 * s))

        var west = Path()
        west.move(to: CGPoint(x: -cap, y: b.y + 36 * s))
        west.addLine(to: CGPoint(x: b.x - 64 * s, y: b.y + 36 * s))
        west.addQuadCurve(to: CGPoint(x: b.x, y: b.y - 4 * s), control: CGPoint(x: b.x, y: b.y + 36 * s))

        let style = StrokeStyle(lineWidth: CaspianEmblem.railWidth, lineCap: .round, lineJoin: .round)
        for rail in [east, west] {
            context.stroke(rail.trimmedPath(from: 0, to: progress), with: .color(EmblemColor.rail), style: style)
        }
        // порт поверх конца рельса — как в иконке
        context.fill(CaspianEmblem.disc(a, CaspianEmblem.portRadius), with: .color(EmblemColor.rail))
        context.fill(CaspianEmblem.disc(b, CaspianEmblem.portRadius), with: .color(EmblemColor.rail))
    }

    /// Паром «где сейчас» — амберное кольцо с белым ядром.
    private static func drawFerry(_ context: inout GraphicsContext, origin: CGPoint, at t: Double, opacity: Double) {
        guard opacity > 0 else { return }
        let p = CaspianEmblem.crossing(t)
        let center = CGPoint(x: origin.x + p.x, y: origin.y + p.y)
        context.opacity = opacity
        context.fill(CaspianEmblem.disc(center, CaspianEmblem.ringRadius), with: .color(EmblemColor.ring))
        context.fill(CaspianEmblem.disc(center, CaspianEmblem.coreRadius), with: .color(EmblemColor.core))
    }
}
