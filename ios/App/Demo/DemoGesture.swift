import SwiftUI
import UIKit

/// Невидимый жест ведущего: долгое нажатие двумя пальцами в любом месте окна.
/// Не двойной тап тремя пальцами: это системный жест «Отменить», и iOS показала бы баннер.
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
        private weak var recognizer: UILongPressGestureRecognizer?

        override func didMoveToWindow() {
            super.didMoveToWindow()
            guard let window, recognizer == nil else { return }
            let press = UILongPressGestureRecognizer(target: self, action: #selector(fire(_:)))
            press.numberOfTouchesRequired = 2
            press.minimumPressDuration = 0.8
            press.cancelsTouchesInView = false
            press.delaysTouchesEnded = false
            press.delegate = self
            window.addGestureRecognizer(press)
            recognizer = press
        }

        @objc private func fire(_ press: UILongPressGestureRecognizer) {
            if press.state == .began { action?() }  // один шаг на одно нажатие
        }

        func gestureRecognizer(
            _ gestureRecognizer: UIGestureRecognizer,
            shouldRecognizeSimultaneouslyWith other: UIGestureRecognizer
        ) -> Bool { true }
    }
}
