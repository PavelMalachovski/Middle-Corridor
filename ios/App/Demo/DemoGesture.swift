import SwiftUI
import UIKit

/// Невидимый жест ведущего: двойной тап тремя пальцами в любом месте окна.
/// Распознаватель вешается на окно и не мешает остальным касаниям.
struct DemoGesture: UIViewRepresentable {
    let action: @MainActor () -> Void

    func makeUIView(context: Context) -> InstallerView {
        let view = InstallerView()
        view.action = action
        view.isUserInteractionEnabled = false
        return view
    }

    func updateUIView(_ view: InstallerView, context: Context) {
        view.action = action
    }

    final class InstallerView: UIView, UIGestureRecognizerDelegate {
        var action: (@MainActor () -> Void)?
        private weak var recognizer: UITapGestureRecognizer?

        override func didMoveToWindow() {
            super.didMoveToWindow()
            guard let window, recognizer == nil else { return }
            let tap = UITapGestureRecognizer(target: self, action: #selector(fire))
            tap.numberOfTouchesRequired = 3
            tap.numberOfTapsRequired = 2
            tap.cancelsTouchesInView = false
            tap.delaysTouchesEnded = false
            tap.delegate = self
            window.addGestureRecognizer(tap)
            recognizer = tap
        }

        @objc private func fire() { action?() }

        func gestureRecognizer(
            _ gestureRecognizer: UIGestureRecognizer,
            shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool { true }
    }
}
