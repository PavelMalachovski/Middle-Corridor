"""Ошибки сервисов аккаунтов: права (→ 404) и данные (ValueError → 422)."""


class AccountsError(Exception):
    pass


class PermissionDenied(AccountsError):
    """Нет прав — наружу отвечаем 404, не 403."""


class NotFound(AccountsError):
    pass
