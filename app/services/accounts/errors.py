"""Ошибки сервисов аккаунтов: права (→ 404) и данные (ValueError → 422)."""


class AccountsError(Exception):
    pass


class PermissionDenied(AccountsError):
    """Нет прав — наружу отвечаем 404, не 403."""


class NotFound(AccountsError):
    pass


class InvitationMailFailed(Exception):
    """Приглашение сохранено, письмо не ушло — вызывающий сообщает «создано, письмо нет»."""

    def __init__(self, invitation_id: int) -> None:
        super().__init__("invitation_mail_failed")
        self.invitation_id = invitation_id
