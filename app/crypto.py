from cryptography.fernet import Fernet

from app.config import TOKEN_ENCRYPTION_KEY

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        if not TOKEN_ENCRYPTION_KEY:
            raise RuntimeError(
                "TOKEN_ENCRYPTION_KEY chưa được cấu hình. Tạo bằng: "
                "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        _fernet = Fernet(TOKEN_ENCRYPTION_KEY.encode())
    return _fernet


def encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()
