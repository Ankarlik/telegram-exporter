"""
ApiKeysModal — ввод api_id и api_hash для Telegram API.

Вызывается с LoginView до того, как пользователь сможет ввести номер телефона.
Ссылка на my.telegram.org — там пользователь получает ключи.
"""

from __future__ import annotations

import webbrowser
from typing import TYPE_CHECKING
import customtkinter as ctk

from ..theme import C, SPACING, WIDGET, font, font_display
from ..components.button import AppButton
from ..components.entry import AppEntry
from ..modal_utils import prepare_modal, show_modal

if TYPE_CHECKING:
    from ..app import App


class ApiKeysModal(ctk.CTkToplevel):
    """Диалог ввода api_id / api_hash."""

    def __init__(self, app: "App") -> None:
        super().__init__(app)
        prepare_modal(self, app, 460, 440, "Настройка API ключей")
        self._app = app
        self._build()
        self._load()
        show_modal(self, app)

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        pad = SPACING["2xl"]

        ctk.CTkLabel(
            self, text="Настройка API ключей",
            font=font_display(18, "bold"), text_color=C["text"],
        ).pack(pady=(pad, SPACING["xs"]))

        ctk.CTkLabel(
            self,
            text="Получите их на my.telegram.org → API development tools.",
            font=font(12), text_color=C["text_sec"],
            wraplength=400, justify="center",
        ).pack(pady=(0, SPACING["md"]))

        AppButton(
            self, text="Открыть my.telegram.org", variant="ghost", size="sm",
            command=lambda: webbrowser.open("https://my.telegram.org"),
        ).pack(pady=(0, SPACING["lg"]))

        # api_id
        ctk.CTkLabel(
            self, text="API ID", font=font(12), text_color=C["text_sec"], anchor="w",
        ).pack(fill="x", padx=pad)
        self._api_id_entry = AppEntry(self, placeholder_text="например, 1234567", size="md")
        self._api_id_entry.pack(fill="x", padx=pad, pady=(SPACING["xs"], SPACING["md"]))

        # api_hash
        ctk.CTkLabel(
            self, text="API Hash", font=font(12), text_color=C["text_sec"], anchor="w",
        ).pack(fill="x", padx=pad)
        self._api_hash_entry = AppEntry(
            self, placeholder_text="32 символа", show="•", size="md",
        )
        self._api_hash_entry.pack(fill="x", padx=pad, pady=(SPACING["xs"], SPACING["md"]))

        # Статус
        self._status_lbl = ctk.CTkLabel(
            self, text="", font=font(11),
            text_color=C["error"], wraplength=400, justify="left", anchor="w",
        )
        self._status_lbl.pack(fill="x", padx=pad, pady=(SPACING["sm"], 0))

        # Кнопки
        btn_h = WIDGET["btn_h"]
        btn_row = ctk.CTkFrame(self, fg_color="transparent", height=btn_h)
        btn_row.pack(side="bottom", fill="x", padx=pad, pady=(SPACING["md"], pad))
        btn_row.pack_propagate(False)

        AppButton(btn_row, text="Отмена", variant="secondary", size="md",
                  command=self.destroy).pack(
            side="left", expand=True, fill="both", padx=(0, SPACING["sm"]),
        )
        AppButton(btn_row, text="Сохранить", variant="primary", size="md",
                  command=self._save).pack(side="left", expand=True, fill="both")

    # ------------------------------------------------------------------ load / save

    def _load(self) -> None:
        """Если API уже настроен — показываем значения (hash скрыт)."""
        if self._app.config.api_id:
            self._api_id_entry.set_text(self._app.config.api_id)
        api_hash = self._app.credentials.load_api_hash(self._app.config.api_id) if self._app.config.api_id else ""
        if api_hash:
            self._api_hash_entry.set_text(api_hash)

    def _save(self) -> None:
        api_id = self._api_id_entry.get().strip()
        api_hash = self._api_hash_entry.get().strip()
        if not api_id or not api_id.isdigit():
            self._status_lbl.configure(text="API ID должен быть числом.")
            return
        if not api_hash or len(api_hash) < 10:
            self._status_lbl.configure(text="API Hash выглядит некорректно.")
            return
        try:
            self._app.save_config(api_id, api_hash)
        except Exception as exc:
            self._status_lbl.configure(text=f"Ошибка сохранения: {exc}")
            return
        self.destroy()
