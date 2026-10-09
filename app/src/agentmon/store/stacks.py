"""Репозиторий стеков и их элементов поверх адаптера Db."""


class StackRepo:
    """CRUD-обёртка над таблицами stacks и stack_items."""

    def __init__(self, db):
        # сохраняем ссылку на адаптер БД
        self._db = db

    def add(self, *, name: str, now=None) -> int:
        """Создаёт стек, возвращает его id.

        now=None — не записываем время (детерминизм тестов).
        """
        return self._db.returning_id(
            "stacks", ["name", "created_at"], [name, now]
        )

    def get(self, id) -> dict | None:
        """Возвращает стек по первичному ключу или None."""
        return self._db.one("SELECT * FROM stacks WHERE id=?", [id])

    def list(self) -> list[dict]:
        """Возвращает все стеки, упорядоченные по id."""
        return self._db.query("SELECT * FROM stacks ORDER BY id")

    def set_status(self, id, status: str) -> None:
        """Меняет статус стека."""
        self._db.execute(
            "UPDATE stacks SET status=? WHERE id=?", [status, id]
        )

    def delete(self, id) -> None:
        """Удаляет стек по id вместе со всеми его элементами (stack_items)."""
        with self._db.transaction():
            self._db.execute("DELETE FROM stack_items WHERE stack_id=?", [id])
            self._db.execute("DELETE FROM stacks WHERE id=?", [id])

    # --- методы управления элементами стека ---

    def add_item(self, stack_id: int, task_id: int, position=None) -> int:
        """Добавляет задачу в стек.

        position=None — вставить в конец (position = текущий максимум + 1).
        Возвращает id записи stack_items.
        """
        # MAX(position)+1 и INSERT — одна транзакция, иначе два параллельных
        # add_item прочитали бы один максимум и дали одинаковую позицию.
        with self._db.transaction():
            if position is None:
                # вычисляем следующую позицию после текущего максимума
                row = self._db.one(
                    "SELECT MAX(position) AS maxp FROM stack_items WHERE stack_id=?",
                    [stack_id],
                )
                max_pos = row["maxp"] if row and row["maxp"] is not None else -1
                position = max_pos + 1
            return self._db.returning_id(
                "stack_items",
                ["stack_id", "task_id", "position"],
                [stack_id, task_id, position],
            )

    def items(self, stack_id: int) -> list[dict]:
        """Возвращает элементы стека, упорядоченные по position."""
        return self._db.query(
            "SELECT * FROM stack_items WHERE stack_id=? ORDER BY position",
            [stack_id],
        )

    def reorder(self, stack_id: int, ordered_task_ids: list[int]) -> None:
        """Переставляет элементы стека согласно переданному порядку task_id.

        Устанавливает position = индекс task_id в списке ordered_task_ids.
        """
        # Цикл UPDATE — одна транзакция: частичная перестановка оставила бы
        # позиции в несогласованном (возможно, с дублями) состоянии.
        with self._db.transaction():
            for new_pos, task_id in enumerate(ordered_task_ids):
                self._db.execute(
                    "UPDATE stack_items SET position=? WHERE stack_id=? AND task_id=?",
                    [new_pos, stack_id, task_id],
                )

    def remove_item(self, item_id: int) -> None:
        """Удаляет элемент стека по id записи в stack_items."""
        self._db.execute("DELETE FROM stack_items WHERE id=?", [item_id])
