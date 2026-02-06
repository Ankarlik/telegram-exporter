import asyncio
import datetime
import json
import os
import queue
import re
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from telethon.errors import SessionPasswordNeededError
from telethon.sync import TelegramClient
from telethon.utils import get_display_name


def sanitize_filename(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name or "chat_export"


def normalize_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "text"):
        return str(getattr(value, "text"))
    return str(value)


def build_forwarded_from(fwd_from) -> str | None:
    if not fwd_from:
        return None
    if getattr(fwd_from, "from_name", None):
        return fwd_from.from_name
    if getattr(fwd_from, "from_id", None):
        return f"from_id:{fwd_from.from_id}"
    if getattr(fwd_from, "channel_post", None):
        return f"channel_post:{fwd_from.channel_post}"
    return None


def build_reactions(message) -> list | None:
    reactions = getattr(message, "reactions", None)
    if not reactions or not getattr(reactions, "results", None):
        return None
    results = []
    for result in reactions.results:
        reaction = result.reaction
        emoji = getattr(reaction, "emoticon", None)
        if not emoji:
            emoji = str(reaction)
        results.append({"emoji": emoji, "count": result.count})
    return results or None


def build_poll(message) -> dict | None:
    media_poll = getattr(message, "poll", None)
    if not media_poll:
        return None
    poll = getattr(media_poll, "poll", None)
    if not poll:
        return None
    poll_data = {"question": normalize_text(poll.question)}
    answers = []
    results = getattr(media_poll, "results", None)
    for answer in getattr(poll, "answers", []) or []:
        count = None
        if results and getattr(results, "results", None):
            for res in results.results:
                if res.option == answer.option:
                    count = res.voters
                    break
        answers.append({"text": normalize_text(answer.text), "voters": count})
    if answers:
        poll_data["answers"] = answers
    if results and getattr(results, "total_voters", None) is not None:
        poll_data["total_voters"] = results.total_voters
    return poll_data


def message_to_export(message) -> dict:
    msg_type = "service" if message.action else "message"
    sender = None
    if message.sender:
        sender = get_display_name(message.sender)
    raw_text = getattr(message, "raw_text", None)
    msg_text = raw_text if raw_text is not None else message.message
    msg = {
        "id": message.id,
        "type": msg_type,
        "date": message.date.isoformat(),
        "from": sender,
        "from_id": message.sender_id,
        "text": normalize_text(msg_text),
    }

    if message.reply_to_msg_id:
        msg["reply_to_message_id"] = message.reply_to_msg_id
    forwarded = build_forwarded_from(message.fwd_from)
    if forwarded:
        msg["forwarded_from"] = forwarded
    reactions = build_reactions(message)
    if reactions:
        msg["reactions"] = reactions
    poll_data = build_poll(message)
    if poll_data:
        msg["poll"] = poll_data
    return msg


class ExporterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Telegram Exporter (Desktop JSON)")
        self.root.geometry("820x640")

        self.queue = queue.Queue()
        self._thread_local = threading.local()
        self.session_path = os.path.join(os.path.dirname(__file__), "telegram_session")
        self.dialogs = []
        self.all_dialogs = []
        self.dialog_map = {}
        self.export_thread = None
        self.phone_code_hash = None

        self._build_ui()
        self.root.after(100, self._process_queue)

    def _build_ui(self) -> None:
        main = ttk.Frame(self.root, padding=12)
        main.pack(fill=tk.BOTH, expand=True)

        creds = ttk.LabelFrame(main, text="Telegram API")
        creds.pack(fill=tk.X, pady=6)

        self.api_id_var = tk.StringVar()
        self.api_hash_var = tk.StringVar()
        self.phone_var = tk.StringVar()
        self.code_var = tk.StringVar()
        self.password_var = tk.StringVar()

        ttk.Label(creds, text="API ID").grid(row=0, column=0, sticky="w")
        self.api_id_entry = self._make_entry(
            creds, textvariable=self.api_id_var, width=16
        )
        self.api_id_entry.grid(
            row=0, column=1, sticky="w", padx=6, pady=2
        )
        ttk.Label(creds, text="API Hash").grid(row=0, column=2, sticky="w")
        self.api_hash_entry = self._make_entry(
            creds, textvariable=self.api_hash_var, width=40
        )
        self.api_hash_entry.grid(
            row=0, column=3, sticky="w", padx=6, pady=2
        )

        ttk.Label(creds, text="Телефон").grid(row=1, column=0, sticky="w")
        self.phone_entry = self._make_entry(creds, textvariable=self.phone_var, width=20)
        self.phone_entry.grid(
            row=1, column=1, sticky="w", padx=6, pady=2
        )
        ttk.Button(creds, text="Отправить код", command=self.send_code).grid(
            row=1, column=2, sticky="w", padx=6
        )

        ttk.Label(creds, text="Код").grid(row=2, column=0, sticky="w")
        self.code_entry = self._make_entry(creds, textvariable=self.code_var, width=12)
        self.code_entry.grid(
            row=2, column=1, sticky="w", padx=6, pady=2
        )
        ttk.Label(creds, text="2FA пароль (если нужен)").grid(
            row=2, column=2, sticky="w"
        )
        self.password_entry = self._make_entry(
            creds, textvariable=self.password_var, width=24, show="*"
        )
        self.password_entry.grid(
            row=2, column=3, sticky="w", padx=6, pady=2
        )
        ttk.Button(creds, text="Подтвердить", command=self.verify_code).grid(
            row=3, column=1, sticky="w", padx=6, pady=4
        )

        chats = ttk.LabelFrame(main, text="Чаты и каналы")
        chats.pack(fill=tk.BOTH, expand=True, pady=6)

        chats_toolbar = ttk.Frame(chats)
        chats_toolbar.pack(fill=tk.X, padx=6, pady=4)

        ttk.Button(chats_toolbar, text="Загрузить список", command=self.load_chats).pack(
            side=tk.LEFT
        )

        ttk.Label(chats_toolbar, text="Поиск").pack(side=tk.LEFT, padx=(12, 4))
        self.search_var = tk.StringVar()
        self.search_entry = self._make_entry(chats_toolbar, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.bind("<KeyRelease>", self._on_search)

        self.chat_list = tk.Listbox(chats, height=14)
        self.chat_list.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        export_frame = ttk.Frame(main)
        export_frame.pack(fill=tk.X, pady=6)

        output_frame = ttk.Frame(export_frame)
        output_frame.pack(fill=tk.X, expand=True)

        ttk.Label(output_frame, text="Папка экспорта").pack(side=tk.LEFT, padx=(0, 6))
        self.output_dir_var = tk.StringVar(value=self._default_export_dir())
        self.output_dir_entry = self._make_entry(
            output_frame, textvariable=self.output_dir_var, width=48
        )
        self.output_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(output_frame, text="Выбрать", command=self.browse_output_dir).pack(
            side=tk.LEFT, padx=6
        )

        ttk.Button(export_frame, text="Экспортировать", command=self.export_chat).pack(
            side=tk.LEFT, padx=4, pady=(6, 0)
        )

        self.progress = ttk.Progressbar(
            export_frame, orient="horizontal", mode="determinate"
        )
        self.progress.pack(fill=tk.X, expand=True, side=tk.LEFT, padx=8)

        self.status_var = tk.StringVar(value="Готово")
        ttk.Label(main, textvariable=self.status_var, foreground="#555").pack(
            anchor="w", pady=4
        )

        log_frame = ttk.LabelFrame(main, text="Лог")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=6)
        self.log_text = tk.Text(log_frame, height=10, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def _process_queue(self) -> None:
        try:
            while True:
                action, payload = self.queue.get_nowait()
                if action == "status":
                    self.status_var.set(payload)
                elif action == "log":
                    self._append_log(payload)
                elif action == "progress":
                    current, total = payload
                    if total:
                        self.progress.config(mode="determinate", maximum=total)
                        self.progress["value"] = current
                    else:
                        self.progress.config(mode="indeterminate")
                        if not self.progress.instate(["!disabled"]):
                            self.progress.start(10)
                elif action == "progress_done":
                    self.progress.stop()
                    self.progress["value"] = 0
                elif action == "chats_loaded":
                    self._populate_chats(payload)
                elif action == "error":
                    messagebox.showerror("Ошибка", payload)
        except queue.Empty:
            pass
        self.root.after(120, self._process_queue)

    def _make_entry(self, parent, **kwargs) -> tk.Entry:
        entry = tk.Entry(parent, **kwargs)
        self._bind_clipboard(entry)
        return entry

    def _bind_clipboard(self, widget: tk.Widget) -> None:
        def _copy(_event=None):
            try:
                selection = widget.selection_get()
            except tk.TclError:
                return "break"
            widget.clipboard_clear()
            widget.clipboard_append(selection)
            return "break"

        def _cut(_event=None):
            try:
                selection = widget.selection_get()
            except tk.TclError:
                return "break"
            widget.clipboard_clear()
            widget.clipboard_append(selection)
            try:
                widget.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            return "break"

        def _paste(_event=None):
            try:
                text = widget.clipboard_get()
            except tk.TclError:
                return "break"
            try:
                widget.delete("sel.first", "sel.last")
            except tk.TclError:
                pass
            widget.insert(tk.INSERT, text)
            return "break"

        widget.bind("<Command-c>", _copy)
        widget.bind("<Command-x>", _cut)
        widget.bind("<Command-v>", _paste)
        widget.bind("<Control-c>", _copy)
        widget.bind("<Control-x>", _cut)
        widget.bind("<Control-v>", _paste)

    def _append_log(self, text: str) -> None:
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{text}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def _default_export_dir(self) -> str:
        today = datetime.date.today().strftime("%Y-%m-%d")
        return os.path.expanduser(
            f"~/Downloads/Telegram Desktop/ChatExport_{today}"
        )

    def browse_output_dir(self) -> None:
        initial_dir = self.output_dir_var.get().strip() or os.path.expanduser("~/")
        selected = filedialog.askdirectory(initialdir=initial_dir)
        if selected:
            self.output_dir_var.set(selected)

    def _set_status(self, text: str) -> None:
        self.queue.put(("status", text))

    def _log(self, text: str) -> None:
        self.queue.put(("log", text))

    def _notify_error(self, text: str) -> None:
        self.queue.put(("error", text))

    def _populate_chats(self, dialogs) -> None:
        self.chat_list.delete(0, tk.END)
        self.dialog_map = {}
        for idx, dialog in enumerate(dialogs):
            label = dialog.name or str(dialog.id)
            self.chat_list.insert(tk.END, label)
            self.dialog_map[idx] = dialog

    def _filter_dialogs(self, query: str) -> list:
        if not query:
            return self.all_dialogs
        query_lower = query.strip().lower()
        if not query_lower:
            return self.all_dialogs
        results = []
        for dialog in self.all_dialogs:
            name = (dialog.name or "").lower()
            if query_lower in name:
                results.append(dialog)
                continue
            dialog_id = str(getattr(dialog, "id", ""))
            if query_lower in dialog_id:
                results.append(dialog)
        return results

    def _on_search(self, _event=None) -> None:
        if not self.all_dialogs:
            return
        dialogs = self._filter_dialogs(self.search_var.get())
        self._populate_chats(dialogs)

    def _get_client(self) -> TelegramClient:
        api_id = self.api_id_var.get().strip()
        api_hash = self.api_hash_var.get().strip()
        if not api_id.isdigit() or not api_hash:
            raise ValueError("Укажи корректные API ID и API Hash.")
        self._ensure_event_loop()
        client = getattr(self._thread_local, "client", None)
        if not client:
            client = TelegramClient(self.session_path, int(api_id), api_hash)
            self._thread_local.client = client
        return client

    def _ensure_event_loop(self) -> None:
        try:
            asyncio.get_running_loop()
            return
        except RuntimeError:
            pass
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

    def _release_thread_client(self, client: TelegramClient | None) -> None:
        if not client:
            return
        try:
            client.disconnect()
        finally:
            if getattr(self._thread_local, "client", None) is client:
                self._thread_local.client = None

    def _run_in_thread(self, target, *args) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True)
        thread.start()

    def send_code(self) -> None:
        self._run_in_thread(self._send_code_thread)

    def _send_code_thread(self) -> None:
        client = None
        try:
            client = self._get_client()
            client.connect()
            if client.is_user_authorized():
                self._set_status("Уже авторизован.")
                return
            phone = self.phone_var.get().strip()
            if not phone:
                raise ValueError("Введи номер телефона.")
            sent = client.send_code_request(phone)
            self.phone_code_hash = getattr(sent, "phone_code_hash", None)
            self._set_status("Код отправлен. Введи код и нажми 'Подтвердить'.")
        except Exception as exc:
            self._set_status("Ошибка при отправке кода.")
            self._log(str(exc))
            self._notify_error(str(exc))
        finally:
            self._release_thread_client(client)

    def verify_code(self) -> None:
        self._run_in_thread(self._verify_code_thread)

    def _verify_code_thread(self) -> None:
        client = None
        try:
            client = self._get_client()
            client.connect()
            if client.is_user_authorized():
                self._set_status("Уже авторизован.")
                return
            phone = self.phone_var.get().strip()
            code = self.code_var.get().strip()
            if not phone or not code:
                raise ValueError("Введи телефон и код.")
            if not self.phone_code_hash:
                raise ValueError("Сначала нажми 'Отправить код'.")
            try:
                client.sign_in(
                    phone=phone, code=code, phone_code_hash=self.phone_code_hash
                )
            except SessionPasswordNeededError:
                password = self.password_var.get().strip()
                if not password:
                    raise ValueError("Нужен пароль 2FA.")
                client.sign_in(password=password)
            self._set_status("Авторизация успешна.")
        except Exception as exc:
            self._set_status("Ошибка авторизации.")
            self._log(str(exc))
            self._notify_error(str(exc))
        finally:
            self._release_thread_client(client)

    def load_chats(self) -> None:
        self._run_in_thread(self._load_chats_thread)

    def _load_chats_thread(self) -> None:
        client = None
        try:
            client = self._get_client()
            client.connect()
            if not client.is_user_authorized():
                raise ValueError("Сначала авторизуйся.")
            self._set_status("Загружаю список чатов...")
            dialogs = client.get_dialogs()
            self.dialogs = dialogs
            self.all_dialogs = dialogs
            self.queue.put(("chats_loaded", dialogs))
            self._set_status(f"Чатов загружено: {len(dialogs)}")
        except Exception as exc:
            self._set_status("Не удалось загрузить чаты.")
            self._log(str(exc))
            self._notify_error(str(exc))
        finally:
            self._release_thread_client(client)

    def export_chat(self) -> None:
        selection = self.chat_list.curselection()
        if not selection:
            messagebox.showwarning("Выбор чата", "Выбери чат для экспорта.")
            return
        dialog = self.dialog_map.get(selection[0])
        if not dialog:
            messagebox.showwarning("Выбор чата", "Чат не найден.")
            return

        output_dir = self.output_dir_var.get().strip()
        if output_dir:
            output_path = os.path.join(output_dir, "result.json")
        else:
            filename = sanitize_filename(dialog.name or "chat_export")
            default_name = f"{filename}_result.json"
            output_path = filedialog.asksaveasfilename(
                defaultextension=".json",
                initialfile=default_name,
                filetypes=[("JSON files", "*.json")],
            )
            if not output_path:
                return

        self.export_thread = threading.Thread(
            target=self._export_thread, args=(dialog, output_path), daemon=True
        )
        self.export_thread.start()

    def _export_thread(self, dialog, output_path: str) -> None:
        client = None
        try:
            client = self._get_client()
            client.connect()
            if not client.is_user_authorized():
                raise ValueError("Сначала авторизуйся.")

            chat_name = dialog.name or str(dialog.id)
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            self._set_status("Экспорт запущен...")
            self._log(f"Экспортирую: {chat_name}")

            total = None
            try:
                total_list = client.get_messages(dialog, limit=0)
                total = getattr(total_list, "total", None)
            except Exception:
                total = None

            if total:
                self.queue.put(("progress", (0, total)))
            else:
                self.queue.put(("progress", (0, None)))

            with open(output_path, "w", encoding="utf-8") as file:
                file.write("{\n")
                file.write(f'  "name": {json.dumps(chat_name, ensure_ascii=False)},\n')
                file.write('  "messages": [\n')

                count = 0
                first = True
                for message in client.iter_messages(dialog, reverse=True):
                    msg_data = message_to_export(message)
                    if not first:
                        file.write(",\n")
                    else:
                        first = False
                    json.dump(msg_data, file, ensure_ascii=False)
                    count += 1
                    if total and count % 200 == 0:
                        self.queue.put(("progress", (count, total)))
                    elif not total and count % 500 == 0:
                        self._set_status(f"Экспортировано: {count} сообщений...")

                file.write("\n  ]\n}\n")

            self.queue.put(("progress_done", None))
            if total:
                self.queue.put(("progress", (total, total)))
            self._set_status(f"Готово. Сообщений: {count}")
            self._log(f"Файл сохранён: {output_path}")
        except Exception as exc:
            self.queue.put(("progress_done", None))
            self._set_status("Ошибка экспорта.")
            self._log(str(exc))
            self._notify_error(str(exc))
        finally:
            self._release_thread_client(client)


def main() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    app = ExporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
