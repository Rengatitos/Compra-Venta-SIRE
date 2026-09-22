"""Errores operativos de captura que se pueden mostrar sin datos de conexión."""


class TransactionsUnavailableError(RuntimeError):
    code = "MONGO_TRANSACTIONS_REQUIRED"
    detail = (
        "La captura requiere MongoDB con transacciones. Configura MongoDB como replica set "
        "o usa MongoDB Atlas y actualiza MONGO_URI del backend. "
        "Vuelve a intentar la operación después de corregir la conexión."
    )

    def __init__(self):
        super().__init__(self.detail)
