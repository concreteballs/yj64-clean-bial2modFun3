"""YJ-64 minimal base application with an embedded diagnostic agent."""

from __future__ import annotations

import json
import os
import sys
import threading
import traceback
import time
import uuid
from pathlib import Path
from kivy.graphics import Color, RoundedRectangle
from typing import Any

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.core.window import Window
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.filechooser import FileChooserListView

class ChatTranscript(BoxLayout):
    """Scrollable, individually selectable chat messages with per-message copy."""
    def __init__(self, **kwargs):
        self._text = ""
        self.message_font_size = kwargs.pop("message_font_size", 14)
        super().__init__(orientation="vertical", spacing=8, padding=(4, 5), **kwargs)

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = str(value or "")
        self._render_messages()

    def _copy(self, value):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(str(value))
        except Exception:
            pass

    def _message_parts(self):
        import re
        value = self._text.strip()
        if not value:
            return []
        chunks = re.split(r"\n\n(?=(?:Owner|Participant [123](?: \[[^\]]+\])?(?: · Раунд \d+)?|YJ-64|User|Participant):\n)", value)
        result = []
        for chunk in chunks:
            first, sep, body = chunk.partition("\n")
            role = first[:-1] if first.endswith(":") else "YJ-64"
            if not sep:
                body, role = chunk, "YJ-64"
            result.append((role, body, chunk))
        return result

    def _render_messages(self):
        self.clear_widgets()
        parts = self._message_parts()
        copy_all = FeedbackButton(text="⧉ КОПИРОВАТЬ ОБСУЖДЕНИЕ С ПОСЛЕДНЕГО СООБЩЕНИЯ ВЛАДЕЛЬЦА", size_hint_y=None, height=48, font_size="10sp", halign="center", valign="middle", background_normal="", background_color=(0.13,0.31,0.53,1), color=(1,1,1,1))
        copy_all.bind(size=lambda instance, value: setattr(instance, "text_size", (max(1, value[0]-16), max(1, value[1]-8))))
        def copy_discussion(*_):
            start = 0
            for index, (role, _body, _raw) in enumerate(parts):
                if role == "Owner":
                    start = index
            self._copy("\n\n".join(item[2] for item in parts[start:]))
        copy_all.bind(on_release=copy_discussion)
        self.add_widget(copy_all)
        for role, body, raw in parts:
            owner = role.lower() in {"owner", "user"}
            participant = role.startswith("Participant")
            import re
            identity_match = re.match(r"^(Participant [123])", role)
            identity = identity_match.group(1) if identity_match else role
            right_aligned = owner or identity == "Participant 2"
            colors = {"Participant 1": (0.04,0.32,0.66,1), "Participant 2": (0.42,0.16,0.56,1), "Participant 3": (0.04,0.43,0.29,1)}
            color = (0.56,0.31,0.04,1) if owner else colors.get(identity, (0.18,0.23,0.34,1))
            body_height = max(72, min(420, (len(body.splitlines()) + max(1, len(body)//48))*18 + 8))
            row = BoxLayout(orientation="horizontal", spacing=5, size_hint_y=None, height=body_height + 80)
            if not right_aligned:
                row.add_widget(Label(text="", size_hint_x=0.08))
            bubble = BoxLayout(orientation="vertical", spacing=4, padding=7, size_hint_x=0.92 if right_aligned else 0.84)
            with bubble.canvas.before:
                bubble_color = Color(*color)
                bubble_background = RoundedRectangle(pos=bubble.pos, size=bubble.size, radius=[10])
            bubble.bind(pos=lambda widget, value, shape=bubble_background: setattr(shape, "pos", value))
            bubble.bind(size=lambda widget, value, shape=bubble_background: setattr(shape, "size", value))
            participant_icon = {"Participant 1": "🔷", "Participant 2": "🟣", "Participant 3": "🟢"}.get(identity, "🤖")
            title = Label(text=("👤 " if owner else (participant_icon + " " if participant else "ℹ️ ")) + role, size_hint_y=None, height=24, halign="left", valign="middle", color=(0.94,0.97,1,1), bold=True, font_size="12sp")
            title.bind(size=lambda inst, val: setattr(inst, "text_size", (max(1,val[0]-4), val[1])))
            bubble.add_widget(title)
            # Give every reply its own scroll viewport so long answers remain readable
            # without copying them elsewhere. The outer chat scroll remains independent.
            message_scroll = ScrollView(
                size_hint_y=None, height=body_height,
                do_scroll_x=False, do_scroll_y=True, bar_width=4,
                scroll_type=["bars", "content"],
            )
            message = Label(
                text=body, size_hint_y=None, halign="left", valign="top",
                color=(0.96,0.97,1,1), font_size=f"{self.message_font_size}sp",
            )
            message.bind(
                width=lambda instance, value: setattr(
                    instance, "text_size", (max(1, value - 14), None)
                )
            )
            message.bind(
                texture_size=lambda instance, value: setattr(
                    instance, "height", max(body_height, value[1] + 14)
                )
            )
            message.height = max(
                body_height,
                (len(body.splitlines()) + max(1, len(body) // 42)) * 20 + 18,
            )
            message_scroll.add_widget(message)
            bubble.add_widget(message_scroll)
            copy_button = FeedbackButton(text="⧉ КОПИРОВАТЬ ОТВЕТ", size_hint_y=None, height=30, font_size="10sp", background_normal="", background_color=(0.13,0.31,0.53,1), color=(1,1,1,1))
            copy_button.bind(on_release=lambda _btn, content=body: self._copy(content))
            bubble.add_widget(copy_button)
            row.add_widget(bubble)
            if not right_aligned:
                row.add_widget(Label(text="", size_hint_x=0.08))
            else:
                row.add_widget(Label(text="", size_hint_x=0.08))
            self.add_widget(row)
        self.height = max(150, sum(child.height + self.spacing for child in self.children) + 10)

class FeedbackButton(Button):
    """Button with tactile and visual press feedback."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._feedback_base_color = tuple(self.background_color)
    def on_press(self):
        self._feedback_base_color = tuple(self.background_color)
        r, g, b, a = self._feedback_base_color
        self.background_color = (r * 0.78, g * 0.78, b * 0.78, a)
        try:
            from plyer import vibrator
            vibrator.vibrate(time=0.025)
        except Exception:
            pass
    def on_release(self):
        self.background_color = self._feedback_base_color

class DialogueControlButton(FeedbackButton):
    """Tap toggles dialogue; long press opens round settings."""
    def __init__(self, short_callback, long_callback, **kwargs):
        self._short_callback, self._long_callback = short_callback, long_callback
        self._long_press_event = None
        self._long_press_fired = False
        super().__init__(**kwargs)
        self.bind(on_press=self._start_long_press, on_release=self._finish_press)
    def _start_long_press(self, *_):
        self._long_press_fired = False
        self._long_press_event = Clock.schedule_once(self._fire_long_press, 0.55)
    def _fire_long_press(self, *_):
        self._long_press_fired = True
        self._long_callback()
    def _finish_press(self, *_):
        if self._long_press_event is not None:
            self._long_press_event.cancel()
            self._long_press_event = None
        if not self._long_press_fired:
            self._short_callback()


Window.softinput_mode = "below_target"
Window.clearcolor = (0.91, 0.95, 0.99, 1)

UI_LANGUAGES = [("ru","Русский"),("en","English"),("es","Español"),("zh","简体中文"),("hi","हिन्दी"),("ar","العربية"),("fr","Français"),("pt","Português"),("de","Deutsch"),("ja","日本語"),("ko","한국어"),("it","Italiano"),("tr","Türkçe"),("id","Bahasa Indonesia")]
UI_TEXT = {
"ru":["YJ-64","Общий чат","Участники","Напишите сообщение…","ОТПРАВИТЬ","Инструменты / монитор","Чаты","Новый чат","Прикрепить файл","Камера / медиа","Критика проекта: выкл.","Файл навыков","Удалённый участник","Практический режим: выкл.","Агенты"],
"en":["YJ-64","Common chat","Participants","Write a message…","SEND","Tools / monitor","Chats","New chat","Attach file","Camera / media","Project critique: off","Skills file","Remote participant","Practical mode: off","Agents"],
"es":["YJ-64","Chat común","Participantes","Escribe un mensaje…","ENVIAR","Herramientas / monitor","Chats","Nuevo chat","Adjuntar archivo","Cámara / medios","Crítica: desactivada","Archivo de habilidades","Participante remoto","Modo práctico: desactivado","Agentes"],
"zh":["YJ-64","公共聊天","参与者","输入消息…","发送","工具 / 监控","聊天","新建聊天","添加文件","相机 / 媒体","项目批判：关闭","技能文件","远程参与者","实践模式：关闭","智能体"],
"hi":["YJ-64","सामान्य चैट","प्रतिभागी","संदेश लिखें…","भेजें","टूल / मॉनिटर","चैट","नई चैट","फ़ाइल जोड़ें","कैमरा / मीडिया","आलोचना: बंद","स्किल फ़ाइल","रिमोट प्रतिभागी","प्रैक्टिकल मोड: बंद","एजेंट"],
"ar":["YJ-64","دردشة مشتركة","المشاركون","اكتب رسالة…","إرسال","الأدوات / المراقبة","الدردشات","دردشة جديدة","إرفاق ملف","الكاميرا / الوسائط","النقد: إيقاف","ملف المهارات","مشارك عن بُعد","الوضع العملي: إيقاف","الوكيل التجاري"],
"fr":["YJ-64","Chat commun","Participants","Écrire un message…","ENVOYER","Outils / moniteur","Chats","Nouveau chat","Joindre un fichier","Caméra / médias","Critique : désactivée","Fichier de compétences","Participant distant","Mode pratique : désactivé","Agents"],
"pt":["YJ-64","Chat comum","Participantes","Escreva uma mensagem…","ENVIAR","Ferramentas / monitor","Chats","Novo chat","Anexar arquivo","Câmara / mídia","Crítica: desligada","Arquivo de competências","Participante remoto","Modo prático: desligado","Agentes"],
"de":["YJ-64","Gemeinsamer Chat","Teilnehmer","Nachricht schreiben…","SENDEN","Werkzeuge / Monitor","Chats","Neuer Chat","Datei anhängen","Kamera / Medien","Kritik: aus","Skill-Datei","Remote-Teilnehmer","Praxismodus: aus","Agenten"],
"ja":["YJ-64","共通チャット","参加者","メッセージを入力…","送信","ツール / モニター","チャット","新しいチャット","ファイルを添付","カメラ / メディア","批評：オフ","スキルファイル","リモート参加者","実践モード：オフ","エージェント"],
"ko":["YJ-64","공용 채팅","참여자","메시지 입력…","전송","도구 / 모니터","채팅","새 채팅","파일 첨부","카메라 / 미디어","비평: 꺼짐","스킬 파일","원격 참여자","실행 모드: 꺼짐","에이전트"],
"it":["YJ-64","Chat comune","Partecipanti","Scrivi un messaggio…","INVIA","Strumenti / monitor","Chat","Nuova chat","Allega file","Fotocamera / media","Critica: disattivata","File competenze","Partecipante remoto","Modalità pratica: disattivata","Avvia implementazione"],
"tr":["YJ-64","Ortak sohbet","Katılımcılar","Mesaj yazın…","GÖNDER","Araçlar / monitör","Sohbetler","Yeni sohbet","Dosya ekle","Kamera / medya","Eleştiri: kapalı","Beceri dosyası","Uzak katılımcı","Pratik mod: kapalı","Uygulamayı başlat"],
"id":["YJ-64","Obrolan bersama","Peserta","Tulis pesan…","KIRIM","Alat / monitor","Obrolan","Obrolan baru","Lampirkan file","Kamera / media","Kritik: nonaktif","File keterampilan","Peserta jarak jauh","Mode praktik: nonaktif","Mulai implementasi"],
}

SERVICE_CLASS = "org.blackmirror.blackmirror.ServiceInternal"
MONITOR_ACTIVITY_CLASS = "org.blackmirror.blackmirror.MonitorActivity"
SERVICE_LAUNCH_FLAG = "yj64.internal_agent_launch"
REPORT_RELATIVE_PATH = Path("yj64-reports") / "yj64-report.jsonl"
TEST_COMMAND_RELATIVE_PATH = Path("yj64-test-command.json")
TEST_RESULT_RELATIVE_PATH = Path("yj64-test-result.json")


class YJ64BaseApp(App):
    def build(self):
        from message_distributor import MessageDistributor
        from chat_workspace import ChatWorkspace

        self.message_distributor = MessageDistributor()
        self.workspace = ChatWorkspace(self.user_data_dir)
        chats = self.workspace.list_chats()
        self.current_chat_id = str(chats[0]["id"])
        self.common_history: list[dict[str, str]] = self.workspace.load_messages(self.current_chat_id)
        self.private_histories: dict[str, list[dict[str, str]]] = {}
        self.practical_mode = False
        self.critique_mode = False
        self.consensus_reached = False
        self.consensus_summary = ""
        self.dialogue_round_limit = 3
        self.dialogue_stop_event = None
        self.dialogue_worker_active = False
        self.report_path = Path(self.user_data_dir) / REPORT_RELATIVE_PATH
        from yj64_persistent_core import PersistentCore
        self.persistent_core = PersistentCore(self.user_data_dir)
        self._previous_excepthook = sys.excepthook
        sys.excepthook = self._handle_uncaught_exception
        self._previous_thread_excepthook = getattr(threading, "excepthook", None)
        if hasattr(threading, "excepthook"):
            threading.excepthook = self._handle_uncaught_thread_exception
        self._archive_export_path = None
        self._archive_restore_prompt_path = Path(self.user_data_dir) / "yj64-restore-prompted.json"
        self.pid_path = Path(self.user_data_dir) / "yj64-main-process.pid"
        try:
            from android.activity import bind
            bind(on_activity_result=self._on_archive_activity_result)
        except Exception as exc:
            self._append_report("memory_archive_saf_unavailable", error=str(exc))

        self.status = Label(
            text="Starting embedded diagnostic agent...",
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=40,
        )
        self.status.bind(
            size=lambda instance, value: setattr(instance, "text_size", value)
        )

        self.ui_language = self._load_language()
        self.chat_ui_settings_path = Path(self.user_data_dir) / "yj64-workspace" / "chat-ui-settings.json"
        self.chat_ui_settings = self._load_chat_ui_settings()
        self.chat_font_size = int(self.chat_ui_settings.get("font_size", 14))
        self.participant_display_names = self.chat_ui_settings.get("participant_names", {})
        self.participant_live_status = {"Participant 1": False, "Participant 2": False, "Participant 3": False}
        Window.clearcolor = (0.025, 0.045, 0.095, 1)
        root = BoxLayout(orientation="vertical", padding=(6, 5), spacing=5)
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=44, spacing=4, padding=(1, 0))
        self.menu_button = FeedbackButton(text="☰", size_hint_x=None, width=42, background_normal="", background_down="", background_color=(0.16,0.34,0.58,1), color=(1,1,1,1), font_size="26sp", bold=True)
        self.menu_button.bind(on_release=self._open_main_menu)
        header.add_widget(self.menu_button)
        self.title_label = Label(text=self._t(0), halign="left", valign="middle", bold=True, font_size="18sp", color=(0.91,0.95,1,1))
        self.title_label.bind(size=lambda instance, value: setattr(instance, "text_size", (value[0], value[1])))
        header.add_widget(self.title_label)
        self.language_button = FeedbackButton(text="ЯЗЫК", size_hint_x=None, width=58, background_normal="", background_down="", background_color=(0.13,0.31,0.53,1), color=(1,1,1,1), font_size="11sp")
        self.language_button.bind(on_release=self._show_language_picker)
        header.add_widget(self.language_button)
        root.add_widget(header)

        self.stop_discussion_button = DialogueControlButton(
            short_callback=self._toggle_main_discussion,
            long_callback=self._open_discussion_menu,
            text=self._discussion_button_text(),
            size_hint_y=None,
            height=46,
            font_size="13sp",
            bold=True,
            background_normal="",
            background_down="",
            background_color=(0.72, 0.19, 0.22, 1),
            color=(1, 1, 1, 1),
        )
        self.stop_discussion_button.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-16), max(1, value[1]-8))))
        root.add_widget(self.stop_discussion_button)

        action_grid = GridLayout(cols=2, spacing=6, size_hint_y=None, row_default_height=62, row_force_default=True)
        action_grid.bind(minimum_height=action_grid.setter("height"))
        self.action_buttons = []
        actions = [(10,self._toggle_critique_mode),(13,self._toggle_practical_mode),(14,self._open_agents_menu)]
        for key, callback in actions:
            button = FeedbackButton(text=self._t(key), size_hint_y=None, height=62, font_size="10sp", halign="center", valign="middle", background_normal="", background_down="", background_color=(0.10,0.20,0.36,1), color=(0.91,0.95,1,1))
            button.bind(size=lambda instance,value: setattr(instance,"text_size",(max(1,value[0]-12),max(1,value[1]-8))))
            button.bind(on_release=callback)
            action_grid.add_widget(button)
            self.action_buttons.append((key,button))
            if key == 10:
                self.critique_mode_button = button
                self.critique_mode_button.background_color = (0.12,0.36,0.32,1)
            elif key == 13:
                self.practical_mode_button = button
            elif key == 14:
                self.implementation_button = button
                self.implementation_button.disabled = not bool(self._chat_target_details()["connected_participants"])
        root.add_widget(action_grid)

        self.chat_nav_row = BoxLayout(orientation="horizontal", spacing=4, size_hint_y=None, height=36)
        self.chats_button = FeedbackButton(text=self._t(6), size_hint_x=0.34, size_hint_y=None, height=34, font_size="10sp", background_normal="", background_color=(0.13,0.31,0.53,1), color=(1,1,1,1))
        self.new_chat_button = FeedbackButton(text=self._t(7), size_hint_x=0.34, size_hint_y=None, height=34, font_size="10sp", background_normal="", background_color=(0.13,0.31,0.53,1), color=(1,1,1,1))
        self.chat_top_button = FeedbackButton(text="↑", size_hint_x=0.16, size_hint_y=None, height=34, font_size="13sp", background_normal="", background_color=(0.13,0.31,0.53,1), color=(1,1,1,1))
        self.chat_bottom_button = FeedbackButton(text="↓", size_hint_x=0.16, size_hint_y=None, height=34, font_size="13sp", background_normal="", background_color=(0.13,0.31,0.53,1), color=(1,1,1,1))
        self.chats_button.bind(on_release=self._show_chats)
        self.new_chat_button.bind(on_release=self._new_chat)
        self.chat_top_button.bind(on_release=lambda *_: setattr(self.chat_scroll, "scroll_y", 1))
        self.chat_bottom_button.bind(on_release=lambda *_: setattr(self.chat_scroll, "scroll_y", 0))
        self.chat_nav_row.add_widget(self.chats_button)
        self.chat_nav_row.add_widget(self.new_chat_button)
        self.chat_nav_row.add_widget(self.chat_top_button)
        self.chat_nav_row.add_widget(self.chat_bottom_button)
        for nav_button in (self.chats_button, self.new_chat_button, self.chat_top_button, self.chat_bottom_button):
            nav_button.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-8), max(1, value[1]-6))))
        root.add_widget(self.chat_nav_row)
        self.chat_heading = Label(text=self._t(1), size_hint_y=None, height=27, color=(0.61,0.76,0.96,1), bold=True, halign="left", valign="middle", font_size="12sp")
        self.chat_heading.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-8), max(1, value[1]-4))))
        root.add_widget(self.chat_heading)
        chat_area = BoxLayout(orientation="horizontal", spacing=6)
        self.chat_scroll = ScrollView(size_hint_x=1, do_scroll_x=False, do_scroll_y=True, bar_width=8, scroll_type=["bars","content"], bar_color=(0.36,0.66,1,1), bar_inactive_color=(0.28,0.53,0.85,0.45))
        self.chat_output = ChatTranscript(size_hint_y=None, height=max(150,Window.height*0.45), message_font_size=self.chat_font_size)
        self.chat_output.text = self._render_history()
        self.chat_scroll.add_widget(self.chat_output)
        chat_area.add_widget(self.chat_scroll)

        participant_scroll = ScrollView(size_hint_x=None, width=110, do_scroll_x=False, do_scroll_y=True, bar_width=3, scroll_type=["bars", "content"])
        participant_panel = BoxLayout(orientation="vertical", size_hint_y=None, spacing=6, padding=(2, 2))
        participant_panel.bind(minimum_height=participant_panel.setter("height"))
        self.participants_heading = Label(text=self._t(2).upper(), size_hint_y=None, height=30, color=(0.61,0.76,0.96,1), bold=True, halign="center", valign="middle", font_size="9sp")
        self.participants_heading.bind(size=lambda instance, value: setattr(instance, "text_size", (max(1,value[0]-4), max(1,value[1]-4))))
        participant_panel.add_widget(self.participants_heading)
        self.participant_buttons = {}
        for participant_name in ("Participant 1", "Participant 2", "Participant 3"):
            button = FeedbackButton(text=self._participant_label(participant_name), size_hint_y=None, height=60, font_size="9sp", halign="center", valign="middle", background_normal="", background_down="", background_color=(0.10,0.20,0.36,1), color=(0.91,0.95,1,1))
            button.bind(size=lambda instance, value: setattr(instance, "text_size", (max(1,value[0]-8), max(1,value[1]-8))))
            button.bind(on_release=lambda _button, name=participant_name: self._open_participant_menu(name))
            self.participant_buttons[participant_name] = button
            participant_panel.add_widget(button)
        self.remote_participant_button = FeedbackButton(text=self._t(12), size_hint_y=None, height=64, font_size="9sp", halign="center", valign="middle", background_normal="", background_down="", background_color=(0.13,0.31,0.53,1), color=(0.91,0.95,1,1))
        self.remote_participant_button.bind(size=lambda instance, value: setattr(instance, "text_size", (max(1,value[0]-8), max(1,value[1]-8))))
        self.remote_participant_button.bind(on_release=self._open_remote_participant)
        participant_panel.add_widget(self.remote_participant_button)
        participant_scroll.add_widget(participant_panel)
        chat_area.add_widget(participant_scroll)
        root.add_widget(chat_area)

        self.chat_send_row = BoxLayout(orientation="horizontal", spacing=6, size_hint_y=None, height=44)
        self.chat_send_button = FeedbackButton(text=self._t(4), size_hint_x=1, size_hint_y=None, height=42, background_normal="", background_down="", background_color=(0.12,0.39,0.68,1), color=(1,1,1,1), font_size="13sp", bold=True)
        self.chat_send_button.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-12), max(1, value[1]-8))))
        self.chat_send_button.bind(on_release=self._send_llm_chat)
        self.chat_send_row.add_widget(self.chat_send_button)
        root.add_widget(self.chat_send_row)

        self.chat_input_row = BoxLayout(orientation="horizontal", spacing=6, size_hint_y=None, height=78)
        self.attach_menu_button = FeedbackButton(text="+", size_hint_x=None, width=46, background_normal="", background_down="", background_color=(0.13,0.31,0.53,1), color=(1,1,1,1), font_size="25sp", bold=True)
        self.attach_menu_button.bind(on_release=self._open_attachment_menu)
        self.chat_input_row.add_widget(self.attach_menu_button)
        self.chat_input = TextInput(hint_text=self._t(3), multiline=True, write_tab=False, input_type="text", keyboard_suggestions=True, size_hint_y=None, height=72, padding=(10,8), font_size="14sp", background_normal="", background_active="", background_color=(0.07,0.11,0.20,1), foreground_color=(0.95,0.97,1,1), cursor_color=(0.95,0.97,1,1))
        self.chat_input.bind(focus=self._chat_input_focus_changed, text=self._resize_chat_input)
        self.chat_input_row.add_widget(self.chat_input)
        root.add_widget(self.chat_input_row)

        self._apply_language()
        if not self.ui_language:
            Clock.schedule_once(lambda *_: self._show_language_picker(), 0.35)

        self._write_main_pid()
        self._append_report(
            "base_ui_ready",
            pid=os.getpid(),
            process_name=self._process_name(),
        )

        Clock.schedule_once(self._offer_archive_restore, 1.2)
        Clock.schedule_once(self._auto_export_download_archive, 2.0)
        Clock.schedule_once(self._ensure_service_started, 0.5)
        Clock.schedule_interval(self._refresh_status, 1.0)
        Clock.schedule_interval(self._refresh_participant_buttons, 1.0)
        Clock.schedule_interval(self._poll_test_command, 0.5)
        self._append_report(
            "workspace_opened",
            chat_id=self.current_chat_id,
            chat_count=len(self.workspace.list_chats()),
            skills_path=str(self.workspace.skills_path),
        )
        return root

    def _open_main_menu(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        popup = Popup(title="YJ-64 MENU", content=content, size_hint=(0.88, 0.62))
        actions = [
            ("СОЗДАТЬ АРХИВ ПАМЯТИ", self._create_memory_archive),
            ("ВОССТАНОВИТЬ ИЗ ZIP", self._choose_memory_archive),
            ("НАСТРОЙКИ ЧАТА: ШРИФТ И ИМЕНА", self._open_chat_appearance_settings),
            (self._t(5), self._open_tools_menu),
            (self._t(6), self._show_chats),
            (self._t(7), self._new_chat),
            (self._t(11), self._open_skills_editor),
        ]
        for label, callback in actions:
            button = FeedbackButton(text=label, size_hint_y=None, height=50, font_size="13sp",
                            background_normal="", background_down="",
                            background_color=(0.10,0.20,0.36,1), color=(0.93,0.96,1,1))
            def invoke(_button: Any, action: Any = callback) -> None:
                popup.dismiss()
                Clock.schedule_once(lambda _dt, selected=action: selected(), 0.15)
            button.bind(on_release=invoke)
            content.add_widget(button)
        close = FeedbackButton(text="ЗАКРЫТЬ", size_hint_y=None, height=42,
                       background_normal="", background_color=(0.13,0.31,0.53,1),
                       color=(1,1,1,1))
        close.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(close)
        popup.open()
        self._append_report("main_menu_opened", actions=["tools_monitor", "chats", "new_chat", "global_skills_file"])

    def _load_chat_ui_settings(self) -> dict[str, Any]:
        try:
            data = json.loads(self.chat_ui_settings_path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                names = data.get("participant_names", {})
                if not isinstance(names, dict): names = {}
                clean = {f"Participant {i}": str(names.get(f"Participant {i}", "")).strip()[:32] for i in (1, 2, 3)}
                return {"font_size": max(10, min(24, int(data.get("font_size", 14)))), "participant_names": clean}
        except (OSError, ValueError, TypeError):
            pass
        return {"font_size": 14, "participant_names": {f"Participant {i}": "" for i in (1, 2, 3)}}

    def _participant_display_name(self, participant: str) -> str:
        return str(self.participant_display_names.get(participant, "") or "").strip() or participant

    def _open_chat_appearance_settings(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        content.add_widget(Label(text="Размер шрифта сообщений (10–24 sp)", size_hint_y=None, height=32))
        font_input = TextInput(text=str(self.chat_font_size), multiline=False, input_filter="int", size_hint_y=None, height=44)
        content.add_widget(font_input)
        fields = {}
        for participant in ("Participant 1", "Participant 2", "Participant 3"):
            field = TextInput(text=str(self.participant_display_names.get(participant, "")), hint_text=f"Имя: {participant}", multiline=False, size_hint_y=None, height=44)
            content.add_widget(field); fields[participant] = field
        popup = Popup(title="НАСТРОЙКИ ЧАТА", content=content, size_hint=(0.92, 0.82), auto_dismiss=False)
        def save(*_args):
            try: size = max(10, min(24, int(font_input.text or "14")))
            except ValueError: size = 14
            names = {key: value.text.strip()[:32] for key, value in fields.items()}
            settings = {"font_size": size, "participant_names": names}
            self.chat_ui_settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.chat_ui_settings_path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
            self.chat_ui_settings = settings; self.chat_font_size = size; self.participant_display_names = names
            self.chat_output.message_font_size = size; self.chat_output.text = self._render_history()
            popup.dismiss(); self._append_report("chat_appearance_settings_saved", font_size=size)
        save_button = FeedbackButton(text="СОХРАНИТЬ", size_hint_y=None, height=46); save_button.bind(on_release=save); content.add_widget(save_button)
        close = FeedbackButton(text="ЗАКРЫТЬ", size_hint_y=None, height=40); close.bind(on_release=lambda *_: popup.dismiss()); content.add_widget(close)
        popup.open()

    def _offer_archive_restore(self, *_: Any) -> None:
        """Offer archive import once per installation; never block normal startup."""
        if self._archive_restore_prompt_path.exists():
            return
        content = BoxLayout(orientation="vertical", spacing=10, padding=12)
        content.add_widget(Label(
            text="Если у вас есть архив памяти YJ-64 (.zip), восстановите его сейчас. "
                 "Без архива можно продолжить работу и выбрать его позже в меню."
        ))
        popup = Popup(title="ВОССТАНОВЛЕНИЕ ПАМЯТИ", content=content, size_hint=(0.92, 0.42), auto_dismiss=False)
        choose = FeedbackButton(text="ВЫБРАТЬ АРХИВ ZIP", size_hint_y=None, height=48)
        later = FeedbackButton(text="ПОЗЖЕ", size_hint_y=None, height=42)
        choose.bind(on_release=lambda *_: (popup.dismiss(), self._choose_memory_archive()))
        def defer_restore(*_: Any) -> None:
            self._archive_restore_prompt_path.write_text(
                json.dumps({"prompted": True, "timestamp_ms": int(time.time() * 1000)}),
                encoding="utf-8",
            )
            popup.dismiss()
        later.bind(on_release=defer_restore)
        content.add_widget(choose)
        content.add_widget(later)
        popup.open()
        self._append_report("memory_archive_restore_offered")

    def _auto_export_download_archive(self, *_: Any) -> None:
        """Create a verified archive in public Downloads/YJ-64 without opening a picker."""
        temp_path = Path(self.user_data_dir) / "YJ-64-backup-auto.zip"
        verify_path = Path(self.user_data_dir) / "YJ-64-backup-auto-verify.zip"
        uri = None
        try:
            self._save_common_history()
            self.persistent_core.export_archive(temp_path)
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            ContentValues = autoclass("android.content.ContentValues")
            MediaStoreDownloads = autoclass("android.provider.MediaStore$Downloads")
            resolver = PythonActivity.mActivity.getContentResolver()
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
            values = ContentValues()
            values.put("display_name", "YJ-64-backup-" + stamp + ".zip")
            values.put("mime_type", "application/zip")
            values.put("relative_path", "Download/YJ-64/")
            values.put("is_pending", 1)
            uri = resolver.insert(MediaStoreDownloads.EXTERNAL_CONTENT_URI, values)
            if uri is None:
                raise IOError("Android MediaStore did not create a Downloads file")
            output = resolver.openOutputStream(uri)
            if output is None:
                raise IOError("Android could not open the Downloads archive for writing")
            copied = 0
            try:
                with temp_path.open("rb") as source:
                    while True:
                        chunk = source.read(65536)
                        if not chunk:
                            break
                        for value_byte in chunk:
                            output.write(value_byte)
                        copied += len(chunk)
                output.flush()
            finally:
                output.close()
            expected = temp_path.stat().st_size
            if copied != expected or copied <= 0:
                raise IOError(f"Downloads archive size mismatch: {copied} of {expected} bytes")
            readback = resolver.openInputStream(uri)
            if readback is None:
                raise IOError("Android could not reopen the Downloads archive")
            read_count = 0
            try:
                with verify_path.open("wb") as verify_file:
                    while True:
                        value_byte = int(readback.read())
                        if value_byte < 0:
                            break
                        verify_file.write(bytes((value_byte & 0xff,)))
                        read_count += 1
            finally:
                readback.close()
            import zipfile
            if read_count != copied or not zipfile.is_zipfile(verify_path):
                raise IOError("Downloads archive read-back or ZIP integrity check failed")
            with zipfile.ZipFile(verify_path, "r") as check_zip:
                bad_member = check_zip.testzip()
                if bad_member or "manifest.json" not in check_zip.namelist():
                    raise IOError("Downloads archive is incomplete or has a corrupt member")
            values_done = ContentValues()
            values_done.put("is_pending", 0)
            resolver.update(uri, values_done, None, None)
            self._append_report("memory_archive_auto_download_succeeded",
                                size_bytes=copied, readback_bytes=read_count,
                                location="Download/YJ-64", zip_integrity_verified=True)
            self._archive_auto_export_error = ""
        except Exception as exc:
            self._archive_auto_export_error = f"{type(exc).__name__}: {exc}"
            self._append_report("memory_archive_auto_download_failed",
                                error_type=type(exc).__name__, error=str(exc),
                                location="Download/YJ-64")
            if uri is not None:
                try:
                    from jnius import autoclass
                    PythonActivity = autoclass("org.kivy.android.PythonActivity")
                    PythonActivity.mActivity.getContentResolver().delete(uri, None, None)
                except Exception:
                    pass
        finally:
            temp_path.unlink(missing_ok=True)
            verify_path.unlink(missing_ok=True)

    def _create_memory_archive(self, *_: Any) -> None:
        """Create a portable ZIP then let Android's document picker save it outside app data."""
        try:
            self._save_common_history()
            temp_path = Path(self.user_data_dir) / "YJ-64-backup.zip"
            self.persistent_core.export_archive(temp_path)
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("application/zip")
            intent.putExtra(Intent.EXTRA_TITLE, "YJ-64-backup.zip")
            self._archive_export_path = str(temp_path)
            PythonActivity.mActivity.startActivityForResult(intent, 4701)
            self.status.text = "Выбери папку для сохранения YJ-64-backup.zip."
            self._append_report("memory_archive_export_picker_opened", archive_size=temp_path.stat().st_size)
        except Exception as exc:
            self.status.text = "Не удалось создать архив: " + str(exc)
            self._append_report("memory_archive_export_failed", error=str(exc))

    def _choose_memory_archive(self, *_: Any) -> None:
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType("application/zip")
            self._archive_restore_prompt_path.write_text(
                json.dumps({"prompted": True, "timestamp_ms": int(time.time() * 1000)}),
                encoding="utf-8",
            )
            PythonActivity.mActivity.startActivityForResult(intent, 4702)
            self.status.text = "Выбери ранее сохранённый архив YJ-64-backup.zip."
            self._append_report("memory_archive_import_picker_opened")
        except Exception as exc:
            self.status.text = "Не удалось открыть выбор архива: " + str(exc)
            self._append_report("memory_archive_import_picker_failed", error=str(exc))

    def _on_archive_activity_result(self, request_code: int, result_code: int, intent: Any) -> None:
        if request_code not in (4701, 4702):
            return
        if result_code != -1 or intent is None:
            self.status.text = "Операция с архивом отменена."
            self._append_report("memory_archive_picker_cancelled", request_code=request_code)
            return
        uri = intent.getData()
        if uri is None:
            self.status.text = "Android не вернул файл."
            self._append_report("memory_archive_uri_missing", request_code=request_code)
            return
        temp_path = Path(self.user_data_dir) / ("yj64-archive-import.zip" if request_code == 4702 else "YJ-64-backup.zip")
        try:
            from jnius import autoclass
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            resolver = PythonActivity.mActivity.getContentResolver()
            if request_code == 4701:
                from_stream = autoclass("java.io.FileInputStream")(str(self._archive_export_path))
                to_stream = resolver.openOutputStream(uri)
            else:
                from_stream = resolver.openInputStream(uri)
                to_stream = autoclass("java.io.FileOutputStream")(str(temp_path))
            if from_stream is None or to_stream is None:
                raise IOError("Android could not open the selected file")
            copied_bytes = 0
            expected_bytes = Path(self._archive_export_path).stat().st_size if request_code == 4701 else None
            try:
                # Use InputStream.read() / OutputStream.write(int), which PyJNIus
                # supports without importing the unavailable jnius.jarray helper.
                while True:
                    value = int(from_stream.read())
                    if value < 0:
                        break
                    to_stream.write(value & 0xff)
                    copied_bytes += 1
                to_stream.flush()
            finally:
                from_stream.close()
                to_stream.close()
            if request_code == 4701:
                if copied_bytes <= 0 or copied_bytes != expected_bytes:
                    raise IOError(f"Archive transfer incomplete: copied {copied_bytes} of {expected_bytes} bytes")
                verify_path = Path(self.user_data_dir) / "yj64-archive-readback.zip"
                verify_stream = resolver.openInputStream(uri)
                if verify_stream is None:
                    raise IOError("Android could not reopen the saved archive for verification")
                verify_bytes = 0
                try:
                    with verify_path.open("wb") as verify_file:
                        while True:
                            value = int(verify_stream.read())
                            if value < 0:
                                break
                            verify_file.write(bytes((value & 0xff,)))
                            verify_bytes += 1
                finally:
                    verify_stream.close()
                import zipfile
                if verify_bytes <= 0 or verify_bytes != copied_bytes:
                    raise IOError(f"Saved archive read-back mismatch: read {verify_bytes} of {copied_bytes} bytes")
                if not zipfile.is_zipfile(verify_path):
                    raise IOError("Saved file is not a valid ZIP archive")
                with zipfile.ZipFile(verify_path, "r") as check_zip:
                    bad_member = check_zip.testzip()
                    if bad_member:
                        raise IOError("Saved ZIP integrity check failed: " + bad_member)
                    if "manifest.json" not in check_zip.namelist():
                        raise IOError("Saved ZIP has no manifest.json")
                verify_path.unlink(missing_ok=True)
                self.status.text = f"Архив сохранён и проверен: {verify_bytes} байт. Проверь файл в выбранной папке."
                self._append_report("memory_archive_export_succeeded", size_bytes=copied_bytes, expected_bytes=expected_bytes, readback_bytes=verify_bytes, zip_integrity_verified=True)
            else:
                if copied_bytes <= 0:
                    raise IOError("Selected archive is empty")
                import zipfile
                if not zipfile.is_zipfile(temp_path):
                    raise IOError("Selected file is not a valid ZIP archive")
                count = self.persistent_core.import_archive(temp_path)
                from chat_workspace import ChatWorkspace
                self.workspace = ChatWorkspace(self.user_data_dir)
                chats = self.workspace.list_chats()
                if chats:
                    self.current_chat_id = str(chats[0]["id"])
                    self.common_history = self.workspace.load_messages(self.current_chat_id)
                    if hasattr(self, "chat_output"):
                        self.chat_output.text = self._render_history()
                self.private_histories = {}
                self.status.text = f"Архив восстановлен: {count} событий. Перезапусти приложение, если часть экранов ещё показывает старые данные."
                self._append_report("memory_archive_import_succeeded", event_count=count, archive=str(uri), size_bytes=copied_bytes)
                try:
                    self._archive_restore_prompt_path.write_text(
                        json.dumps({"prompted": True, "restored": True, "timestamp_ms": int(time.time() * 1000)}),
                        encoding="utf-8",
                    )
                except OSError:
                    pass
        except Exception as exc:
            self.status.text = "Ошибка архива памяти: " + str(exc)
            self._append_report("memory_archive_transfer_failed", request_code=request_code, error=str(exc))

    def _load_language(self) -> str | None:
        path = Path(self.user_data_dir) / "yj64-language.json"
        try:
            code = str(json.loads(path.read_text(encoding="utf-8")).get("language", ""))
            return code if code in UI_TEXT else None
        except (OSError, ValueError, AttributeError):
            return None

    def _t(self, index: int) -> str:
        return UI_TEXT.get(self.ui_language or "en", UI_TEXT["en"])[index]

    def _discussion_button_text(self) -> str:
        labels = {
            "ru": ("ОСТАНОВИТЬ ОБСУЖДЕНИЕ", "ВОЗОБНОВИТЬ ОБСУЖДЕНИЕ"),
            "en": ("STOP DISCUSSION", "RESUME DISCUSSION"),
            "es": ("DETENER DISCUSIÓN", "REANUDAR DISCUSIÓN"),
            "zh": ("停止讨论", "继续讨论"),
            "hi": ("चर्चा रोकें", "चर्चा फिर शुरू करें"),
            "ar": ("إيقاف النقاش", "استئناف النقاش"),
            "fr": ("ARRÊTER LA DISCUSSION", "REPRENDRE LA DISCUSSION"),
            "pt": ("PARAR DISCUSSÃO", "RETOMAR DISCUSSÃO"),
            "de": ("DISKUSSION STOPPEN", "DISKUSSION FORTSETZEN"),
            "ja": ("議論を停止", "議論を再開"),
            "ko": ("토론 중지", "토론 재개"),
            "it": ("FERMA DISCUSSIONE", "RIPRENDI DISCUSSIONE"),
            "tr": ("TARTIŞMAYI DURDUR", "TARTIŞMAYI SÜRDÜR"),
            "id": ("HENTIKAN DISKUSI", "LANJUTKAN DISKUSI"),
        }
        stop_label, resume_label = labels.get(self.ui_language or "en", labels["en"])
        return stop_label if self.message_distributor.dialogue_enabled else resume_label

    def _refresh_discussion_button(self) -> None:
        enabled = self.message_distributor.dialogue_enabled
        self.stop_discussion_button.text = self._discussion_button_text()
        self.stop_discussion_button.background_color = (
            (0.72, 0.19, 0.22, 1) if enabled else (0.12, 0.48, 0.29, 1)
        )

    def _open_discussion_menu(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical", spacing=7, padding=10)
        popup = Popup(title="УПРАВЛЕНИЕ ДИАЛОГОМ", content=content, size_hint=(0.88, 0.66))
        for label, rounds in [("1 раунд",1),("2 раунда",2),("3 раунда (обычно)",3),("5 раундов",5),("10 раундов",10),("Без ограничений — до остановки",0)]:
            button = FeedbackButton(text=("✓ " if self.dialogue_round_limit == rounds else "") + label, size_hint_y=None, height=43)
            button.bind(on_release=lambda _button, value=rounds: self._set_dialogue_rounds(value, popup))
            content.add_widget(button)
        toggle = FeedbackButton(text=("ОСТАНОВИТЬ" if self.message_distributor.dialogue_enabled else "ВОЗОБНОВИТЬ") + " ОБСУЖДЕНИЕ", size_hint_y=None, height=46)
        toggle.bind(on_release=lambda *_: (popup.dismiss(), self._toggle_main_discussion()))
        content.add_widget(toggle)
        close = FeedbackButton(text="ЗАКРЫТЬ", size_hint_y=None, height=38)
        close.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(close)
        popup.open()
        self._append_report("dialogue_control_menu_opened", round_limit=self.dialogue_round_limit)

    def _set_dialogue_rounds(self, rounds: int, popup: Popup) -> None:
        self.dialogue_round_limit = max(0, int(rounds))
        self._append_report("dialogue_round_limit_changed", round_limit=self.dialogue_round_limit, unlimited=rounds == 0)
        self.status.text = "Dialogue rounds: unlimited" if rounds == 0 else f"Dialogue rounds set to {rounds}."
        popup.dismiss()

    def _toggle_main_discussion(self, *_: Any) -> None:
        enabled = not self.message_distributor.dialogue_enabled
        if not enabled and self.dialogue_stop_event is not None:
            self.dialogue_stop_event.set()
        self.message_distributor.set_dialogue_enabled(enabled)
        self._refresh_discussion_button()
        self._append_report("main_discussion_resumed" if enabled else "main_discussion_stopped", source="main_chat_controls", active_cycle_cancel_requested=not enabled)
        self.status.text = "Discussion resumed." if enabled else "Stopping after the in-flight model request returns."

    def _open_attachment_menu(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        popup = Popup(title="ATTACH FILE / MEDIA", content=content, size_hint=(0.88, 0.34))
        for label, callback in (
            (self._t(8), self._attach_file),
            (self._t(9), self._open_live_media_placeholder),
        ):
            button = FeedbackButton(
                text=label, size_hint_y=None, height=52, font_size="14sp",
                background_normal="", background_down="",
                background_color=(0.10, 0.20, 0.36, 1), color=(0.93, 0.96, 1, 1),
            )
            button.bind(on_release=lambda _button, action=callback: (popup.dismiss(), action()))
            content.add_widget(button)
        close = FeedbackButton(text="CLOSE", size_hint_y=None, height=42)
        close.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(close)
        popup.open()
        self._append_report("attachment_menu_opened")

    def _apply_language(self) -> None:
        self.title_label.text = self._t(0)
        self.remote_participant_button.text = self._t(12) if hasattr(self, "remote_participant_button") else self._t(12)
        self.chat_heading.text = self._t(1)
        self.participants_heading.text = self._t(2).upper()
        self.language_button.text = {"ru":"ЯЗЫК","en":"LANG","es":"IDIOMA","zh":"语言","hi":"भाषा","ar":"اللغة","fr":"LANGUE","pt":"IDIOMA","de":"SPRACHE","ja":"言語","ko":"언어","it":"LINGUA","tr":"DİL","id":"BAHASA"}.get(self.ui_language or "en", "LANG")
        for name, button in getattr(self, "participant_buttons", {}).items():
            button.text = self._participant_label(name)
        self.chat_input.hint_text = self._t(3)
        self.chat_send_button.text = self._t(4)
        if hasattr(self, "attach_menu_button"):
            self.attach_menu_button.text = "+"
        for key, button in getattr(self, "action_buttons", []):
            button.text = self._t(key)
        if hasattr(self, "stop_discussion_button"):
            self._refresh_discussion_button()

    def _participant_label(self, participant_name: str) -> str:
        index = int(participant_name.rsplit(" ", 1)[-1]) - 1
        labels = {
            "ru": ("Участник 1", "Участник 2", "Участник 3"),
            "en": ("Participant 1", "Participant 2", "Participant 3"),
            "es": ("Participante 1", "Participante 2", "Participante 3"),
            "zh": ("参与者 1", "参与者 2", "参与者 3"),
            "hi": ("प्रतिभागी 1", "प्रतिभागी 2", "प्रतिभागी 3"),
            "ar": ("المشارك 1", "المشارك 2", "المشارك 3"),
            "fr": ("Participant 1", "Participant 2", "Participant 3"),
            "pt": ("Participante 1", "Participante 2", "Participante 3"),
            "de": ("Teilnehmer 1", "Teilnehmer 2", "Teilnehmer 3"),
            "ja": ("参加者 1", "参加者 2", "参加者 3"),
            "ko": ("참여자 1", "참여자 2", "참여자 3"),
            "it": ("Partecipante 1", "Partecipante 2", "Partecipante 3"),
            "tr": ("Katılımcı 1", "Katılımcı 2", "Katılımcı 3"),
            "id": ("Peserta 1", "Peserta 2", "Peserta 3"),
        }
        return labels.get(self.ui_language or "en", labels["en"])[index]

    def _choose_language(self, code: str, popup: Popup) -> None:
        self.ui_language = code
        (Path(self.user_data_dir) / "yj64-language.json").write_text(json.dumps({"language":code},ensure_ascii=False),encoding="utf-8")
        popup.dismiss()
        self._apply_language()
        self._append_report("ui_language_changed", language=code)

    def _show_language_picker(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical", spacing=7, padding=10)
        listing = ScrollView(do_scroll_x=False, do_scroll_y=True, bar_width=6)
        items = BoxLayout(orientation="vertical", spacing=5, size_hint_y=None)
        items.bind(minimum_height=items.setter("height"))
        popup = Popup(title="CHOOSE LANGUAGE / ВЫБЕРИТЕ ЯЗЫК", content=content, size_hint=(0.92,0.82))
        for code,label in UI_LANGUAGES:
            button = FeedbackButton(text=label,size_hint_y=None,height=46,background_normal="",background_color=(0.18,0.43,0.68,1),color=(1,1,1,1))
            button.bind(on_release=lambda _button,language=code:self._choose_language(language,popup))
            items.add_widget(button)
        listing.add_widget(items)
        content.add_widget(listing)
        close = FeedbackButton(text="CLOSE",size_hint_y=None,height=44)
        close.bind(on_release=lambda *_:popup.dismiss())
        content.add_widget(close)
        popup.open()

    def _resize_chat_output(self, *_: Any) -> None:
        if not hasattr(self, "chat_output") or not hasattr(self, "chat_scroll"):
            return
        was_at_bottom = self.chat_scroll.scroll_y <= 0.03
        lines = max(1, len(self.chat_output.text.splitlines()))
        self.chat_output.height = max(self.chat_scroll.height, lines * 21 + 30)
        if was_at_bottom:
            Clock.schedule_once(lambda *_: setattr(self.chat_scroll, "scroll_y", 0), 0)

    def _append_chat_text(self, text: str) -> None:
        self.chat_output.text = (self.chat_output.text + "\n\n" + text).strip()

    def _resize_chat_input(self, *_: Any) -> None:
        if not hasattr(self,"chat_input"):
            return
        height = min(330,max(72,len(self.chat_input.text.splitlines())*22+18))
        self.chat_input.height = height
        if self.chat_input.parent is not None:
            self.chat_input.parent.height = height+6

    def _open_participants_menu(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical",spacing=7,padding=10)
        listing = ScrollView(do_scroll_x=False,do_scroll_y=True,bar_width=6)
        items = BoxLayout(orientation="vertical",spacing=6,size_hint_y=None)
        items.bind(minimum_height=items.setter("height"))
        popup = Popup(title=self._t(2).upper(),content=content,size_hint=(0.92,0.72))
        for name in ("Participant 1","Participant 2","Participant 3"):
            state = self._participant_config_status(name)
            verified = bool(self.participant_live_status.get(name,False))
            state_text = "AVAILABLE — last request succeeded" if verified else "NOT VERIFIED / unavailable"
            provider = state["provider"] or "No provider"
            model = state["model"] or "No model"
            button = FeedbackButton(text=f"{name}\n{provider} / {model}\n{state_text}",size_hint_y=None,height=76,halign="left",valign="middle",background_normal="",background_color=(0.76,0.92,0.80,1) if verified else (0.87,0.89,0.92,1),color=(0.08,0.20,0.13,1) if verified else (0.22,0.25,0.29,1))
            button.bind(size=lambda instance,value:setattr(instance,"text_size",(max(1,value[0]-18),value[1]-8)))
            button.bind(on_release=lambda _button,participant=name:(popup.dismiss(),self._open_participant_menu(participant)))
            items.add_widget(button)
        remote = FeedbackButton(text="REMOTE DEVICE / ADMIN MODULE (CURRENTLY A STUB)",size_hint_y=None,height=54,background_normal="",background_color=(0.87,0.89,0.92,1),color=(0.22,0.25,0.29,1))
        remote.bind(on_release=lambda *_:(popup.dismiss(),self._open_remote_participant()))
        items.add_widget(remote)
        listing.add_widget(items)
        content.add_widget(listing)
        close = FeedbackButton(text="CLOSE",size_hint_y=None,height=44)
        close.bind(on_release=lambda *_:popup.dismiss())
        content.add_widget(close)
        popup.open()
        self._append_report("participants_dropdown_opened",participants=["Participant 1","Participant 2","Participant 3"])

    def _render_history(self) -> str:
        rendered = []
        for item in self.common_history:
            content = str(item.get("content", ""))
            if item.get("role") == "user":
                role, body = "Owner", content
            elif ": " in content and content.split(": ", 1)[0].split(" [", 1)[0].split(" · Раунд ", 1)[0] in {"Participant 1", "Participant 2", "Participant 3", "Owner"}:
                role, body = content.split(": ", 1)
            else:
                role, body = "YJ-64", content
            if role.startswith("Participant "):
                import re
                match = re.match(r"^(Participant [123])(?: \[([^\]]+)\])?(?: · Раунд (\d+))?$", role)
                if match:
                    canonical, _saved_name, round_no = match.groups()
                    role = self._participant_display_name(canonical)
                    if round_no: role += f" · Раунд {round_no}"
            rendered.append(f"{role}:\n{body}")
        return "\n\n".join(rendered) or "New chat. Write a message below."

    def _save_common_history(self) -> None:
        self.workspace.save_messages(self.current_chat_id, self.common_history)

    def _select_chat(self, chat_id: str, popup: Popup) -> None:
        popup.dismiss()
        self.current_chat_id = chat_id
        self.common_history = self.workspace.load_messages(chat_id)
        self.chat_output.text = self._render_history()
        self.consensus_reached = False
        self.implementation_button.disabled = not bool(self._chat_target_details()["connected_participants"])
        self._append_report("workspace_chat_selected", chat_id=chat_id)
        self.status.text = f"Opened chat {chat_id[:8]} with {len(self.common_history)} saved messages."

    def _show_chats(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical", spacing=8, padding=10)
        listing = ScrollView(do_scroll_x=False)
        items = BoxLayout(orientation="vertical", spacing=6, size_hint_y=None)
        items.bind(minimum_height=items.setter("height"))
        popup = Popup(title="SAVED CHATS", content=content, size_hint=(0.94, 0.86))
        for item in self.workspace.list_chats():
            title = str(item.get("title") or "Untitled chat")
            button = FeedbackButton(
                text=f"{title}\n{str(item['id'])[:8]}",
                size_hint_y=None, height=62,
            )
            button.bind(
                on_release=lambda _btn, chat_id=str(item["id"]):
                self._select_chat(chat_id, popup)
            )
            items.add_widget(button)
        listing.add_widget(items)
        content.add_widget(listing)
        branch_button = FeedbackButton(
            text="CREATE BRANCH FROM CURRENT CHAT",
            size_hint_y=None, height=52,
        )
        def create_branch(*_args: Any) -> None:
            parent = self.current_chat_id
            new_id = self.workspace.create_chat("Ветка обсуждения", parent_id=parent)
            self.workspace.save_messages(new_id, list(self.common_history))
            self._select_chat(new_id, popup)
            self._append_report("workspace_branch_created", chat_id=new_id, parent_id=parent)
        branch_button.bind(on_release=create_branch)
        content.add_widget(branch_button)
        close = FeedbackButton(text="CLOSE", size_hint_y=None, height=48)
        close.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(close)
        popup.open()

    def _new_chat(self, *_: Any) -> None:
        self._save_common_history()
        self.current_chat_id = self.workspace.create_chat("Новый чат")
        self.common_history = []
        self.chat_output.text = self._render_history()
        self.consensus_reached = False
        self.implementation_button.disabled = not bool(self._chat_target_details()["connected_participants"])
        self._append_report("workspace_chat_created", chat_id=self.current_chat_id)
        self.status.text = "New local chat created."

    def _toggle_critique_mode(self, *_: Any) -> None:
        self.critique_mode = not self.critique_mode
        self.critique_mode_button.text = (
            "CRITIQUE PROJECT: ON" if self.critique_mode else "CRITIQUE PROJECT: OFF"
        )
        self.critique_mode_button.background_color = (
            (0.85, 0.15, 0.15, 1) if self.critique_mode else (0.15, 0.65, 0.25, 1)
        )
        self._append_report("critique_mode_changed", enabled=self.critique_mode)
        self.status.text = (
            "Critique mode ON: models must identify flaws, risks, and counter-evidence."
            if self.critique_mode else "Critique mode OFF: normal instructions restored."
        )

    def _open_skills_editor(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical", spacing=8, padding=10)
        editor = TextInput(text=self.workspace.read_skills(), multiline=True)
        content.add_widget(editor)
        status = Label(text=f"Stored locally: {self.workspace.skills_path}", size_hint_y=None, height=44)
        content.add_widget(status)
        buttons = BoxLayout(size_hint_y=None, height=52, spacing=8)
        save = FeedbackButton(text="SAVE SKILLS")
        close = FeedbackButton(text="CLOSE")
        buttons.add_widget(save)
        buttons.add_widget(close)
        content.add_widget(buttons)
        popup = Popup(title="LOCAL SKILLS FILE", content=content, size_hint=(0.96, 0.9))
        def save_skills(*_args: Any) -> None:
            self.workspace.write_skills(editor.text)
            self._append_report("skills_file_saved", character_count=len(editor.text))
            status.text = "Saved locally. Instructions are added to future chat prompts."
        save.bind(on_release=save_skills)
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _attach_file(self, *_: Any) -> None:
        preferred = Path("/storage/emulated/0/Download")
        start_path = preferred if preferred.is_dir() else Path(self.user_data_dir)
        content = BoxLayout(orientation="vertical", spacing=8, padding=10)
        chooser = FileChooserListView(path=str(start_path), filters=["*"])
        content.add_widget(chooser)
        note = Label(
            text="Text files are embedded in the prompt (max 64 KB). Other files are recorded by name only; binary/multimedia transfer is not yet implemented.",
            size_hint_y=None, height=58,
        )
        content.add_widget(note)
        buttons = BoxLayout(size_hint_y=None, height=52, spacing=8)
        attach = FeedbackButton(text="ATTACH SELECTED")
        close = FeedbackButton(text="CLOSE")
        buttons.add_widget(attach)
        buttons.add_widget(close)
        content.add_widget(buttons)
        popup = Popup(title="ATTACH A FILE", content=content, size_hint=(0.97, 0.92))
        def attach_selected(*_args: Any) -> None:
            if not chooser.selection:
                note.text = "Select a file first."
                return
            path = Path(chooser.selection[0])
            if not path.is_file():
                note.text = "Select a file, not a folder."
                return
            suffix = path.suffix.lower()
            text_suffixes = {".txt", ".md", ".json", ".csv", ".py", ".yaml", ".yml", ".xml", ".log"}
            try:
                if suffix in text_suffixes:
                    with path.open("rb") as handle:
                        raw = handle.read(65537)
                    if len(raw) > 65536:
                        note.text = "Text file exceeds 64 KB; not attached. Use a smaller excerpt."
                        return
                    body = raw.decode("utf-8", errors="replace")
                    self.chat_input.text += f"\n\n[ATTACHED TEXT FILE: {path.name}]\n{body}\n[END ATTACHMENT]\n"
                    self._append_report("chat_text_file_attached", name=path.name, bytes=len(raw))
                    note.text = f"Text contents added to message: {path.name}"
                else:
                    self.chat_input.text += f"\n\n[ATTACHMENT METADATA: {path.name}; type={suffix or 'unknown'}; content not transmitted]\n"
                    self._append_report(
                        "chat_binary_attachment_selected",
                        name=path.name, suffix=suffix, transmitted=False,
                    )
                    note.text = "File name added only. This file's binary contents have NOT been sent to an LLM."
                attach.disabled = True
            except OSError as exc:
                note.text = f"Could not read file: {type(exc).__name__}: {exc}"
                self._append_report("chat_attachment_failed", path=str(path), error=str(exc))
        attach.bind(on_release=attach_selected)
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _open_tools_menu(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        popup = Popup(title="TOOLS / MONITOR / DIAGNOSTICS", content=content, size_hint=(0.92, 0.84))
        actions = [
            ("EDIT CURRENT CHAT CONTEXT", self._open_context_editor),
            ("OPEN INTERNAL MONITOR", self._open_monitor),
            ("TEST LLM API + COPY REPORT", self._test_llm_api),
            ("TEST LLM GENERATION + COPY", self._test_llm_generation),
            ("CONFIGURE LLM API / KEY", self._open_llm_settings),
            ("COPY DIAGNOSTIC REPORT", self._copy_diagnostic_report),
            ("CHATGPT BRIDGE (STUB)", self._open_chatgpt_bridge),
        ]
        for label, callback in actions:
            button = FeedbackButton(text=label, size_hint_y=None, height=54)
            def invoke(_button: Any, action: Any = callback) -> None:
                popup.dismiss()
                Clock.schedule_once(lambda _dt, selected=action: selected(), 0.15)
            button.bind(on_release=invoke)
            content.add_widget(button)
        close = FeedbackButton(text="CLOSE", size_hint_y=None, height=48)
        close.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(close)
        popup.open()
        self._append_report("tools_menu_opened", actions=[item[0] for item in actions])

    def _open_context_editor(self, *_: Any) -> None:
        """Edit the current chat context as plain text and persist it as valid JSON."""
        chat_id = str(self.current_chat_id)
        try:
            current = "\n\n".join(str(item.get("content", "")) for item in self.workspace.load_messages(chat_id))
        except Exception as exc:
            self.status.text = "Не удалось прочитать контекст: " + str(exc)
            self._append_report("context_editor_read_failed", chat_id=chat_id, error=str(exc))
            return
        content = BoxLayout(orientation="vertical", spacing=8, padding=10)
        note = Label(text="Редактируется контекст текущего чата. Сохранение заменит его одним сообщением владельца.\n" + str(self.workspace._messages_path(chat_id)), size_hint_y=None, height=64, halign="left", valign="middle")
        note.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-12), value[1]-6)))
        editor = TextInput(text=current, multiline=True, size_hint=(1, 1), write_tab=False, padding=(10, 10))
        content.add_widget(note)
        content.add_widget(editor)
        buttons = BoxLayout(size_hint_y=None, height=48, spacing=8)
        save = FeedbackButton(text="СОХРАНИТЬ КОНТЕКСТ")
        close = FeedbackButton(text="ОТМЕНА")
        buttons.add_widget(save)
        buttons.add_widget(close)
        content.add_widget(buttons)
        popup = Popup(title="YJ-64 — РЕДАКТОР КОНТЕКСТА", content=content, size_hint=(0.96, 0.90))
        def save_context(*_args: Any) -> None:
            try:
                value = editor.text
                messages = [{"role": "user", "content": value}] if value.strip() else []
                self.workspace.save_messages(chat_id, messages)
                if self.workspace.load_messages(chat_id) != messages:
                    raise IOError("Контекст не прошёл проверку после сохранения")
                self.current_chat_id = chat_id
                self.common_history = messages
                self.chat_output.text = self._render_history()
                self.status.text = f"Контекст сохранён и проверен: {len(value)} символов."
                self._append_report("context_editor_saved", chat_id=chat_id, character_count=len(value), history_count=len(messages), path=str(self.workspace._messages_path(chat_id)))
                popup.dismiss()
            except Exception as exc:
                self.status.text = "Ошибка сохранения контекста: " + str(exc)
                self._append_report("context_editor_save_failed", chat_id=chat_id, error=str(exc))
        save.bind(on_release=save_context)
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()
        self._append_report("context_editor_opened", chat_id=chat_id, character_count=len(current), path=str(self.workspace._messages_path(chat_id)))

    def _copy_diagnostic_report(self, *_: Any) -> None:
        report = self._read_report_text()
        self._copy_to_clipboard(report)
        self.status.text = f"Diagnostic report copied from {self.report_path}"
        self._append_report("diagnostic_report_copy_requested", path=str(self.report_path))

    def _open_chatgpt_bridge(self, *_: Any) -> None:
        from chatgpt_bridge import get_status
        state = get_status()
        content = BoxLayout(orientation="vertical", spacing=10, padding=12)
        content.add_widget(Label(
            text="CHATGPT BRIDGE — PLACEHOLDER ONLY\n\n" + state.message
                 + "\n\nNo browser session is read, no credentials are captured, "
                   "and no content is sent to ChatGPT from this screen."
        ))
        close = FeedbackButton(text="CLOSE", size_hint_y=None, height=52)
        content.add_widget(close)
        popup = Popup(title="CHATGPT BRIDGE", content=content, size_hint=(0.94, 0.62))
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()
        self._append_report("chatgpt_bridge_placeholder_opened", connected=False)

    def _open_live_media_placeholder(self, *_: Any) -> None:
        content = BoxLayout(orientation="vertical", spacing=10, padding=12)
        content.add_widget(Label(
            text="CAMERA / LIVE MEDIA\n\n"
                 "This build can select files, but it does not yet capture or stream live "
                 "camera video, and binary image/audio/video contents are not uploaded to "
                 "the LLM. A real implementation needs Android capture permissions, a "
                 "supported real-time transport, and explicit user controls."
        ))
        close = FeedbackButton(text="CLOSE", size_hint_y=None, height=52)
        content.add_widget(close)
        popup = Popup(title="CAMERA / LIVE MEDIA", content=content, size_hint=(0.94, 0.6))
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()
        self._append_report("live_media_placeholder_opened", capture_started=False, streaming_started=False)

    def _open_remote_participant(self, *_: Any) -> None:
        from remote_participant import RemoteParticipantClient

        if not hasattr(self, "remote_participant_client"):
            self.remote_participant_client = RemoteParticipantClient(
                on_event=self._remote_participant_event
            )

        content = BoxLayout(orientation="vertical", spacing=6, padding=(8, 6))
        details_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False, do_scroll_y=True, bar_width=5, scroll_type=["bars", "content"])
        details_content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=7, padding=(2, 2))
        details_content.bind(minimum_height=details_content.setter("height"))
        form = GridLayout(cols=1, spacing=7, size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))
        form_title = Label(
            text="Подключение к удалённому участнику",
            size_hint_y=None, height=48, halign="center", valign="middle",
            font_size="14sp", color=(0.91,0.95,1,1)
        )
        form_title.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1,value[0]-12), max(1,value[1]-8))))
        form.add_widget(form_title)
        self.remote_url_input = TextInput(
            hint_text="Адрес сервера: wss://…", text=getattr(self, "remote_saved_url", ""),
            multiline=False, size_hint_y=None, height=48, write_tab=False, padding=(8, 8)
        )
        self.remote_name_input = TextInput(
            hint_text="Имя участника", text=getattr(self, "remote_saved_name", "Owner"),
            multiline=False, size_hint_y=None, height=48, write_tab=False, padding=(8, 8)
        )
        self.remote_token_input = TextInput(
            hint_text="Токен доступа (секретный)", password=True, multiline=False,
            size_hint_y=None, height=48, write_tab=False, padding=(8, 8)
        )
        form.add_widget(self.remote_url_input)
        form.add_widget(self.remote_name_input)
        form.add_widget(self.remote_token_input)
        details_content.add_widget(form)

        self.remote_connection_status = Label(
            text="Не подключено. Введите адрес сервера и токен.",
            size_hint_y=None, height=60, halign="left", valign="middle",
            font_size="12sp", color=(0.91,0.95,1,1)
        )
        self.remote_connection_status.bind(
            size=lambda w, value: setattr(w, "text_size", (max(1, value[0]-8), max(1, value[1]-8)))
        )
        details_content.add_widget(self.remote_connection_status)

        self.remote_messages = TextInput(
            text="Здесь появятся сообщения удалённого участника.",
            readonly=True, multiline=True, size_hint_y=None, height=180, padding=(8, 8),
            background_color=(0.045,0.075,0.14,1), foreground_color=(0.91,0.95,1,1)
        )
        details_content.add_widget(self.remote_messages)

        send_row = BoxLayout(orientation="horizontal", spacing=6, size_hint_y=None, height=50)
        self.remote_message_input = TextInput(
            hint_text="Сообщение удалённому участнику…", multiline=False, write_tab=False,
            size_hint_y=None, height=46, padding=(8, 8)
        )
        send_row.add_widget(self.remote_message_input)
        send_button = FeedbackButton(
            text="ОТПРАВИТЬ", size_hint_x=None, width=94, size_hint_y=None, height=46,
            font_size="10sp", halign="center", valign="middle",
            background_normal="", background_color=(0.13,0.31,0.53,1)
        )
        send_button.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-8), max(1, value[1]-6))))
        send_button.bind(on_release=self._send_remote_participant_message)
        send_row.add_widget(send_button)
        details_content.add_widget(send_row)
        details_scroll.add_widget(details_content)
        content.add_widget(details_scroll)

        actions = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=52)
        self.remote_connect_button = FeedbackButton(
            text="ПОДКЛЮЧИТЬСЯ", size_hint_y=None, height=48, font_size="10sp",
            halign="center", valign="middle", background_normal="", background_color=(0.12,0.45,0.28,1)
        )
        self.remote_connect_button.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1,value[0]-10), max(1,value[1]-8))))
        self.remote_connect_button.bind(on_release=self._connect_remote_participant)
        actions.add_widget(self.remote_connect_button)
        disconnect = FeedbackButton(
            text="ОТКЛЮЧИТЬСЯ", size_hint_y=None, height=48, font_size="10sp",
            halign="center", valign="middle", background_normal="", background_color=(0.45,0.20,0.20,1)
        )
        disconnect.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1,value[0]-10), max(1,value[1]-8))))
        disconnect.bind(on_release=lambda *_: self.remote_participant_client.disconnect())
        actions.add_widget(disconnect)
        content.add_widget(actions)
        close = FeedbackButton(text="ЗАКРЫТЬ", size_hint_y=None, height=44, font_size="11sp", background_normal="")
        content.add_widget(close)

        popup = Popup(title="REMOTE PARTICIPANT", content=content, size_hint=(0.96, 0.90))
        close.bind(on_release=lambda *_: popup.dismiss())
        self.remote_participant_popup = popup
        popup.open()
        self._append_report("remote_participant_connection_ui_opened", connected=self.remote_participant_client.connected)

    def _connect_remote_participant(self, *_: Any) -> None:
        url = self.remote_url_input.text.strip()
        name = self.remote_name_input.text.strip()
        token = self.remote_token_input.text
        if not url or not name or not token:
            self.remote_connection_status.text = "Заполните адрес сервера, имя и токен."
            return
        self.remote_saved_url = url
        self.remote_saved_name = name
        self.remote_connection_status.text = "Подключение…"
        self.remote_connect_button.disabled = True
        self._append_report("remote_participant_connect_requested", url=url, participant_name=name, token_present=bool(token))
        self.remote_participant_client.connect(url, name, token)

    def _remote_participant_event(self, event: str, data: dict[str, Any]) -> None:
        def apply_event(_dt: float = 0) -> None:
            if event == "connected":
                self.remote_connection_status.text = "ПОДКЛЮЧЕНО: " + str(data.get("name", "участник"))
                self.remote_connect_button.disabled = False
                self.remote_connect_button.text = "ПОДКЛЮЧЕНО"
                self.remote_participant_button.background_color = (0.12,0.55,0.28,1)
                self._append_report("remote_participant_connected", participant_id=data.get("participant_id"), participant_name=data.get("name"))
            elif event == "message":
                line = "[{}] {}".format(data.get("name", "участник"), data.get("text", ""))
                current = self.remote_messages.text
                self.remote_messages.text = ("" if current.startswith("Здесь появятся") else current + "\n") + line
                self._append_report("remote_participant_message_received", participant_name=data.get("name"), message=str(data.get("text", ""))[:12000])
            elif event == "disconnected":
                self.remote_connection_status.text = str(data.get("message", "Соединение закрыто."))
                self.remote_connect_button.disabled = False
                self.remote_connect_button.text = "ПОДКЛЮЧИТЬСЯ"
                self.remote_participant_button.background_color = (0.13,0.31,0.53,1)
                self._append_report("remote_participant_disconnected", reason=data.get("message", ""))
            elif event == "error":
                self.remote_connection_status.text = "Ошибка: " + str(data.get("message", "неизвестная ошибка"))
                self.remote_connect_button.disabled = False
                self.remote_connect_button.text = "ПОДКЛЮЧИТЬСЯ"
                self._append_report("remote_participant_connection_failed", error=str(data.get("message", "")))
        Clock.schedule_once(apply_event, 0)

    def _send_remote_participant_message(self, *_: Any) -> None:
        message = self.remote_message_input.text.strip()
        if not message:
            return
        if self.remote_participant_client.send_message(message):
            self.remote_messages.text += "\n[Я] " + message
            self.remote_message_input.text = ""
            self._append_report("remote_participant_message_sent", message=message[:12000])
        else:
            self.remote_connection_status.text = "Нет активного соединения. Сначала подключитесь."

    def _toggle_practical_mode(self, *_: Any) -> None:
        self.practical_mode = not self.practical_mode
        self.consensus_reached = False
        self.consensus_summary = ""
        self.implementation_button.disabled = not bool(self._chat_target_details()["connected_participants"])
        self.practical_mode_button.text = (
            "ПРАКТИЧЕСКИЕ ДЕЙСТВИЯ: ON — ОЖИДАЕМ КОНСЕНСУС"
            if self.practical_mode
            else "ПЕРЕЙТИ К ПРАКТИЧЕСКИМ ДЕЙСТВИЯМ: OFF"
        )
        self.practical_mode_button.background_color = (
            (0.15, 0.65, 0.25, 1) if self.practical_mode else (1, 1, 1, 1)
        )
        self._append_report(
            "practical_mode_changed",
            enabled=self.practical_mode,
            consensus_reached=False,
        )
        if self.practical_mode:
            self.status.text = (
                "Practical mode enabled. Each connected model will receive "
                "action-oriented rules before the next question."
            )
        else:
            self.status.text = "Practical mode disabled; normal chat instructions restored."

    def _open_agents_menu(self, *_: Any) -> None:
        agents = self.workspace.list_agents()
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        note = Label(text="Короткое нажатие: запустить с инструкциями моделей.\nДолгое нажатие: настройки и личный чат.", size_hint_y=None, height=58)
        content.add_widget(note)
        popup = Popup(title="АГЕНТЫ", content=content, size_hint=(0.94, 0.86))
        for agent in agents:
            agent_id = str(agent["id"])
            button = DialogueControlButton(
                short_callback=lambda aid=agent_id: (popup.dismiss(), self._launch_agent_with_models(aid)),
                long_callback=lambda aid=agent_id: (popup.dismiss(), self._open_agent_settings(aid)),
                text=str(agent.get("name") or "Агент"),
                size_hint_y=None, height=58, font_size="13sp",
                background_normal="", background_color=(0.15, 0.28, 0.48, 1),
                color=(1, 1, 1, 1),
            )
            button.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-12), max(1, value[1]-8))))
            content.add_widget(button)
        create = FeedbackButton(text="＋ СОЗДАТЬ НОВОГО АГЕНТА", size_hint_y=None, height=58, background_normal="", background_color=(0.12, 0.43, 0.29, 1), color=(1, 1, 1, 1))
        create.bind(on_release=lambda *_: (popup.dismiss(), self._create_agent_popup()))
        close = FeedbackButton(text="ЗАКРЫТЬ", size_hint_y=None, height=48)
        close.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(create)
        content.add_widget(close)
        popup.open()
        self._append_report("agents_menu_opened", agent_count=len(agents))

    def _create_agent_popup(self) -> None:
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        name_input = TextInput(text="", hint_text="Название агента", multiline=False, size_hint_y=None, height=48)
        instructions = TextInput(text="", hint_text="Опиши задачу и инструкции для нового агента", multiline=True)
        note = Label(text="Модели подготовят код-кандидат. Произвольный код не исполняется и не публикуется автоматически.", size_hint_y=None, height=64)
        buttons = BoxLayout(orientation="horizontal", spacing=8, size_hint_y=None, height=52)
        create = FeedbackButton(text="СОЗДАТЬ", size_hint_x=0.6)
        close = FeedbackButton(text="ОТМЕНА", size_hint_x=0.4)
        buttons.add_widget(create)
        buttons.add_widget(close)
        content.add_widget(name_input)
        content.add_widget(instructions)
        content.add_widget(note)
        content.add_widget(buttons)
        popup = Popup(title="СОЗДАТЬ АГЕНТА", content=content, size_hint=(0.96, 0.9), auto_dismiss=False)
        def create_agent(*_args: Any) -> None:
            prompt = instructions.text.strip()
            if not prompt:
                note.text = "Сначала введи инструкции для агента."
                return
            name = name_input.text.strip() or "Новый агент"
            details = self._chat_target_details()
            configured = list(details.get("connected_participants") or [])
            runner = configured[0] if configured else "Participant 1"
            agent = self.workspace.create_agent(name, prompt, runner=runner)
            self.workspace.save_agent_message(agent["id"], "owner", prompt)
            self._append_report("agent_created", agent_id=agent["id"], name=name, runner=runner, model_count=len(configured), code_execution_enabled=False, public_release=False)
            popup.dismiss()
            self.status.text = f"Агент «{name}» создан. Подготавливается код-кандидат и статическая проверка."
            self._generate_agent_code(agent["id"])
        create.bind(on_release=create_agent)
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _generate_agent_code(self, agent_id: str) -> None:
        from threading import Thread
        agent = self.workspace.load_agent(agent_id)
        if not agent:
            return
        participants = list(self._chat_target_details().get("connected_participants") or [])
        def worker() -> None:
            candidates = []
            errors = []
            for participant in participants:
                status = self._participant_config_status(participant)
                request = (
                    "Create a reviewable Python implementation candidate for this YJ-64 agent. "
                    "Return only Python code in one fenced python block. The code is UNTRUSTED and must not "
                    "perform network, filesystem, subprocess, shell, payment, credential, publication, or "
                    "self-modification actions. Do not include imports except json, math, re, datetime, "
                    "statistics, or collections. Provide pure functions with explicit inputs/outputs. "
                    "Agent instructions:\n" + str(agent.get("instructions") or "")
                )
                try:
                    result = self.message_distributor.dispatch_message(
                        self.user_data_dir, participant, request, mode=status["mode"],
                        history=[{"role": "user", "content": request}],
                        report=lambda event, _p=participant, **data: self._append_report("agent_codegen_"+event, participant=_p, agent_id=agent_id, **data),
                    )
                    candidates.append((participant, str(result.get("response") or "")))
                except Exception as exc:
                    errors.append(f"{participant}: {type(exc).__name__}: {exc}")
            combined = "\n\n".join(f"# Candidate from {name}\n{body}" for name, body in candidates)
            import ast
            import re
            blocks = re.findall(r"```(?:python)?\s*([\s\S]*?)```", combined, re.IGNORECASE)
            code = "\n\n".join(blocks).strip() if blocks else ""
            status_value = "candidate_unvalidated"
            reason = "No fenced Python code returned by connected models."
            if code:
                try:
                    tree = ast.parse(code)
                    blocked_names = {"exec", "eval", "open", "compile", "__import__", "input", "globals", "locals", "getattr", "setattr", "delattr", "socket", "requests", "subprocess", "urllib", "os", "sys", "pathlib", "shutil", "pickle", "ctypes", "importlib"}
                    found = sorted({node.name for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id in blocked_names})
                    bad_imports = sorted({alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for alias in (node.names if isinstance(node, ast.Import) else [type("Alias", (), {"name": node.module or ""})()]) if alias.name.split(".")[0] not in {"json", "math", "re", "datetime", "statistics", "collections"}})
                    if found or bad_imports:
                        status_value = "blocked_by_static_policy"
                        reason = "Disallowed names/imports: " + ", ".join(found + bad_imports)
                    else:
                        status_value = "static_check_passed_not_executed"
                        reason = "Python syntax and import/name checks passed. Candidate was not executed; isolated runtime tests and public release remain disabled."
                except SyntaxError as exc:
                    status_value = "blocked_invalid_python"
                    reason = f"Syntax check failed at line {exc.lineno}: {exc.msg}"
            latest = self.workspace.load_agent(agent_id) or agent
            latest["code_candidate"] = combined[:50000]
            latest["sandbox_status"] = status_value
            latest["sandbox_note"] = reason
            self.workspace.save_agent(latest)
            self._append_report("agent_code_candidate_reviewed", agent_id=agent_id, participants=participants, candidate_count=len(candidates), error_count=len(errors), sandbox_status=status_value, sandbox_note=reason, executed=False, public_release=False, errors=errors)
            Clock.schedule_once(lambda _dt: setattr(self.status, "text", f"Агент «{latest.get('name')}»: {status_value}. Код не исполнялся и не опубликован."), 0)
        Thread(target=worker, name="yj64-agent-codegen", daemon=True).start()

    def _open_agent_settings(self, agent_id: str) -> None:
        agent = self.workspace.load_agent(agent_id)
        if not agent:
            self.status.text = "Агент не найден."
            return
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        content.add_widget(Label(text=f"{agent.get('name')}\nСостояние кода: {agent.get('sandbox_status', 'pending')}\nИсполнитель: {agent.get('runner', 'Participant 1')}", size_hint_y=None, height=76))
        popup = Popup(title="НАСТРОЙКИ АГЕНТА", content=content, size_hint=(0.94, 0.82))
        actions = [
            ("ЛИЧНЫЙ ЧАТ", lambda: self._open_agent_private_chat(agent_id)),
            ("НАСТРОИТЬ API-КЛЮЧ / МОДЕЛЬ", lambda: self._open_participant_settings(str(agent.get("runner") or "Participant 1"))),
            ("ПОСМОТРЕТЬ КОД И РЕЗУЛЬТАТЫ ПРОВЕРКИ", lambda: self._show_agent_code(agent_id)),
        ]
        for runner_name in ("Participant 1", "Participant 2", "Participant 3"):
            selected = str(agent.get("runner") or "Participant 1") == runner_name
            runner_button = FeedbackButton(
                text=("✓ ИСПОЛНИТЕЛЬ: " if selected else "СДЕЛАТЬ ИСПОЛНИТЕЛЕМ: ") + runner_name,
                size_hint_y=None, height=46,
                background_normal="",
                background_color=(0.12, 0.43, 0.29, 1) if selected else (0.15, 0.28, 0.48, 1),
                color=(1, 1, 1, 1),
            )
            def select_runner(_button: Any, name: str = runner_name) -> None:
                current = self.workspace.load_agent(agent_id)
                if current:
                    current["runner"] = name
                    self.workspace.save_agent(current)
                    self._append_report("agent_runner_selected", agent_id=agent_id, runner=name)
                popup.dismiss()
                self._open_agent_settings(agent_id)
            runner_button.bind(on_release=select_runner)
            content.add_widget(runner_button)
        for label, callback in actions:
            button = FeedbackButton(text=label, size_hint_y=None, height=54)
            button.bind(on_release=lambda _b, action=callback: (popup.dismiss(), action()))
            content.add_widget(button)
        close = FeedbackButton(text="ЗАКРЫТЬ", size_hint_y=None, height=48)
        close.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(close)
        popup.open()
        self._append_report("agent_settings_opened", agent_id=agent_id, runner=agent.get("runner"))

    def _show_agent_code(self, agent_id: str) -> None:
        agent = self.workspace.load_agent(agent_id)
        if not agent:
            return
        content = BoxLayout(orientation="vertical", spacing=8, padding=10)
        details = Label(text=f"Статус: {agent.get('sandbox_status', 'pending')}\n{agent.get('sandbox_note', 'Проверка ещё не выполнялась.')}", size_hint_y=None, height=80)
        code = TextInput(text=str(agent.get("code_candidate") or "Код-кандидат ещё не получен."), readonly=True, multiline=True)
        close = FeedbackButton(text="ЗАКРЫТЬ", size_hint_y=None, height=48)
        content.add_widget(details)
        content.add_widget(code)
        content.add_widget(close)
        popup = Popup(title="КОД-КАНДИДАТ АГЕНТА", content=content, size_hint=(0.96, 0.92))
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _open_agent_private_chat(self, agent_id: str) -> None:
        agent = self.workspace.load_agent(agent_id)
        if not agent:
            return
        content = BoxLayout(orientation="vertical", spacing=7, padding=10)
        output = TextInput(readonly=True, multiline=True, size_hint_y=0.62)
        prompt = TextInput(hint_text="Личное сообщение или инструкция агенту…", multiline=True, size_hint_y=None, height=88)
        controls = BoxLayout(orientation="horizontal", spacing=6, size_hint_y=None, height=52)
        send = FeedbackButton(text="ОТПРАВИТЬ", size_hint_x=0.5)
        run = FeedbackButton(text="ЗАПУСТИТЬ АГЕНТА", size_hint_x=0.5, background_normal="", background_color=(0.10, 0.46, 0.28, 1), color=(1, 1, 1, 1))
        close = FeedbackButton(text="ЗАКРЫТЬ", size_hint_y=None, height=46)
        controls.add_widget(send)
        controls.add_widget(run)
        content.add_widget(output)
        content.add_widget(prompt)
        content.add_widget(controls)
        content.add_widget(close)
        popup = Popup(title=f"ЛИЧНЫЙ ЧАТ: {agent.get('name')}", content=content, size_hint=(0.96, 0.92))
        def refresh() -> None:
            current = self.workspace.load_agent(agent_id) or agent
            lines = []
            for item in current.get("private_messages", []):
                role = str(item.get("role") or "agent")
                lines.append(f"{role}:\n{item.get('content', '')}")
            output.text = "\n\n".join(lines) or "Личный чат агента. Здесь видны твои инструкции и сообщения моделей."
            output.cursor = (0, 0)
        def send_private(*_args: Any) -> None:
            message = prompt.text.strip()
            if not message:
                return
            prompt.text = ""
            self.workspace.save_agent_message(agent_id, "owner", message)
            self._append_report(
                "agent_private_owner_message",
                agent_id=agent_id,
                message=message[:12000],
                executed=False,
                model_instructions_requested=False,
            )
            refresh()
            self.status.text = "Сообщение сохранено в личном чате. Агент не запущен; нажми «ЗАПУСТИТЬ АГЕНТА», когда будешь готов."
        send.bind(on_release=send_private)
        run.bind(on_release=lambda *_: self._run_agent(agent_id, owner_only=True, on_complete=refresh))
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()
        refresh()

    def _launch_agent_with_models(self, agent_id: str) -> None:
        from threading import Thread
        agent = self.workspace.load_agent(agent_id)
        if not agent:
            return
        participants = list(self._chat_target_details().get("connected_participants") or [])
        if not participants:
            self.status.text = "Нельзя запустить агента: ни одна модель не подключена."
            self._append_report("agent_launch_rejected", agent_id=agent_id, reason="no_connected_participants")
            return
        self.status.text = f"Модели готовят инструкции для агента «{agent.get('name')}»…"
        def worker() -> None:
            generated = []
            for participant in participants:
                status = self._participant_config_status(participant)
                request = (
                    "Write a concise private instruction message for this agent. Do not address the owner, "
                    "do not send this message to another model, and do not claim to execute actions. "
                    "Identify one concrete next step and relevant safety limits.\nAgent: "
                    + str(agent.get("name") or "") + "\nOwner instructions: "
                    + str(agent.get("instructions") or "")
                )
                try:
                    result = self.message_distributor.dispatch_message(
                        self.user_data_dir, participant, request, mode=status["mode"],
                        history=[{"role": "user", "content": request}],
                        report=lambda event, _p=participant, **data: self._append_report("agent_instruction_"+event, participant=_p, agent_id=agent_id, **data),
                    )
                    body = str(result.get("response") or "").strip()
                    if body:
                        self.workspace.save_agent_message(agent_id, "model: "+participant, body)
                        generated.append((participant, body))
                except Exception as exc:
                    err = f"{type(exc).__name__}: {exc}"
                    self.workspace.save_agent_message(agent_id, "model error: "+participant, err)
                    self._append_report("agent_instruction_generation_failed", agent_id=agent_id, participant=participant, error=err)
            if generated:
                instruction_text = "\n\n".join(f"{name}: {body}" for name, body in generated)
                self._run_agent(agent_id, owner_only=False, model_instructions=instruction_text)
            else:
                Clock.schedule_once(lambda _dt: setattr(self.status, "text", "Модели не предоставили инструкции; агент не запущен."), 0)
        Thread(target=worker, name="yj64-agent-instruction-generation", daemon=True).start()

    def _run_agent(self, agent_id: str, owner_only: bool = True, extra_owner_message: str = "", model_instructions: str = "", on_complete: Any = None) -> None:
        from threading import Thread
        agent = self.workspace.load_agent(agent_id)
        if not agent:
            return
        runner = str(agent.get("runner") or "Participant 1")
        status = self._participant_config_status(runner)
        if not status.get("configured"):
            self._append_report("agent_run_rejected", agent_id=agent_id, runner=runner, reason="runner_not_configured")
            self.status.text = f"Модель-исполнитель {runner} не настроена. Открой настройки агента."
            if on_complete:
                Clock.schedule_once(lambda _dt: on_complete(), 0)
            return
        owner_messages = [str(item.get("content") or "") for item in agent.get("private_messages", []) if str(item.get("role") or "") == "owner"]
        if extra_owner_message and (not owner_messages or owner_messages[-1] != extra_owner_message):
            owner_messages.append(extra_owner_message)
        task_parts = [
            "YJ-64 PROMPT-DRIVEN AGENT. Treat the owner's instructions as the task. "
            "Do not claim code execution, network access, publication, or external actions unless a separately verified tool actually performed them. "
            "If a request appears dangerous or irreversible, stop and ask the owner.\nAgent name: " + str(agent.get("name") or ""),
            "Base instructions:\n" + str(agent.get("instructions") or ""),
            "Owner's private instructions (authoritative):\n" + "\n\n".join(owner_messages),
        ]
        if not owner_only and model_instructions:
            task_parts.append("Model-provided instruction notes (visible in private chat):\n" + model_instructions)
        task = "\n\n".join(part for part in task_parts if part.strip())
        self._append_report("agent_run_started", agent_id=agent_id, runner=runner, owner_only=owner_only, model_instructions_included=bool(not owner_only and model_instructions), code_executed=False, public_release=False)
        self.status.text = f"Агент «{agent.get('name')}» выполняет запрос через {runner}…"
        def worker() -> None:
            try:
                result = self.message_distributor.dispatch_message(
                    self.user_data_dir, runner, task, mode=status["mode"],
                    history=[{"role": "user", "content": task}],
                    report=lambda event, **data: self._append_report("agent_run_"+event, agent_id=agent_id, runner=runner, **data),
                )
                response = str(result.get("response") or "").strip()
                if not response:
                    raise RuntimeError("Пустой ответ агента")
                self.workspace.save_agent_message(agent_id, "agent", response)
                self._append_report("agent_run_completed", agent_id=agent_id, runner=runner, response=response, code_executed=False, public_release=False)
                message = f"Агент «{agent.get('name')}» завершил ответ."
            except Exception as exc:
                response = f"{type(exc).__name__}: {exc}"
                self.workspace.save_agent_message(agent_id, "agent error", response)
                self._append_report("agent_run_failed", agent_id=agent_id, runner=runner, error=response)
                message = f"Агент «{agent.get('name')}» завершился с ошибкой."
            def finish(_dt: float) -> None:
                self.status.text = message
                if on_complete:
                    on_complete()
            Clock.schedule_once(finish, 0)
        Thread(target=worker, name="yj64-agent-run", daemon=True).start()

    def _start_agent_implementation(self, *_: Any) -> None:
        target_details = self._chat_target_details()
        participants = list(target_details["connected_participants"])
        if not participants:
            self._append_report("commercial_agent_launch_rejected", reason="no_connected_participants")
            self.status.text = "Коммерческий агент не запущен: сначала подключите хотя бы одну модель."
            return
        self.practical_mode = True
        self.practical_mode_button.text = "КОММЕРЧЕСКИЙ АГЕНТ: РЫНОЧНОЕ ИССЛЕДОВАНИЕ"
        self.practical_mode_button.background_color = (0.15, 0.65, 0.25, 1)
        self.consensus_reached = True
        self.consensus_summary = "Read-only commercial research session; no financial or external actions authorized."
        request = (
            "COMMERCIAL RESEARCH AGENT — READ-ONLY MODE.\n"
            "Investigate the commercial opportunity described by the owner. Identify customer need, target segments, competitors, pricing, distribution channels, platform fees, startup and operating costs, plausible revenue scenarios, key assumptions, legal/operational risks, and measurable validation steps. Cite sources and dates for factual claims when available; clearly label unknowns and estimates. Do not invent live market facts.\n"
            "STRICT PERMISSION BOUNDARY: research and analysis only. Do not buy anything, spend money, publish listings, contact people, place trades, make transactions, modify code or files, or claim to have performed any of those actions. Do not treat estimated revenue as actual profit. Present benefits, risks, uncertainties, evidence, a proposed next step, and explicit stop conditions. Ask the owner before any action that creates an external commitment.\n"
            "Owner's request: "
        )
        if self.chat_input.text.strip():
            request += self.chat_input.text.strip()
        else:
            request += "Propose and compare low-cost small commercial opportunities that can be validated without spending money. Begin with research and a validation plan only."
        self._append_report("commercial_agent_launch_requested", participants=participants, mode="read_only", spending_authorized=False, external_actions_authorized=False)
        self.chat_input.text = request
        self._send_llm_chat()

    def _practical_instructions(self, prompt: str, implementation: bool = False) -> str:
        sections: list[str] = []
        if self.critique_mode:
            sections.append(
                "YJ-64 CRITIQUE PROJECT MODE: critically inspect assumptions, identify "
                "failure modes and counter-evidence, separate facts from speculation, "
                "and suggest tests that could disprove the proposal. Be constructive."
            )
        if self.practical_mode:
            if implementation:
                sections.append(
                    "YJ-64 PRACTICAL ACTION PROTOCOL. Phase: IMPLEMENTATION DRAFT. "
                    "Provide exact files, complete patches, integration points, tests, "
                    "rollback steps, and unknowns. Do not claim repository edits or execution "
                    "without evidence. No verified repository-writing agent is installed. "
                    "End with [IMPLEMENTATION DRAFT]."
                )
            else:
                sections.append(
                    "YJ-64 PRACTICAL ACTION PROTOCOL. Give ordered actionable steps, files/tools, "
                    "dependencies, risks, and testable completion criteria. Separate verified "
                    "facts from assumptions. End with [CONSENSUS: APPROVE] only when you agree "
                    "with no unresolved blocker, otherwise [CONSENSUS: OBJECT]. Do not imitate "
                    "another participant's vote without independent assessment."
                )
        try:
            skills = self.workspace.read_skills().strip()
        except (OSError, AttributeError):
            skills = ""
        if skills:
            sections.append("YJ-64 LOCAL SKILLS (user-editable instructions):\n" + skills[:12000])
        if not sections:
            return prompt
        return "\n\n".join(sections) + "\n\nUSER TASK:\n" + prompt

    def _toggle_request_mode(self, *_: Any) -> None:
        mode = self.message_distributor.toggle_mode()
        self.mode_button.text = f"REQUEST MODE: {mode.upper()}"
        self._append_report(
            "message_mode_changed",
            mode=mode,
            note=(
                "Agent mode selected; each participant uses its own configured Agent ID."
                if mode == "agent" else "Text mode selected."
            ),
        )
        self.status.text = (
            "Text mode selected."
            if mode == "text"
            else "Agent mode selected; each participant uses its own configured Agent ID."
        )

    def _participant_config_status(self, participant_name: str) -> dict[str, str | bool]:
        from llm_api import load_config, route_config_exists

        route_id = self.message_distributor.route_for_participant(participant_name)
        configured = route_config_exists(self.user_data_dir, route_id)
        config = load_config(self.user_data_dir, route_id=route_id) if configured else {}
        mode = "agent" if str(config.get("agent_id") or "").strip() else "text"
        return {
            "configured": configured,
            "mode": mode,
            "route_id": route_id,
            "provider": str(config.get("provider") or ""),
            "model": str(config.get("model") or ""),
        }

    def _refresh_participant_buttons(self, *_: Any) -> None:
        # Green means a real request succeeded; a configured key alone is not a connection.
        for name, button in getattr(self, "participant_buttons", {}).items():
            verified = bool(self.participant_live_status.get(name, False))
            button.background_color = (0.18,0.55,0.32,1) if verified else (0.78,0.84,0.90,1)
            button.color = (1,1,1,1) if verified else (0.10,0.20,0.30,1)
            button.text = self._participant_label(name)

    def _open_participant_menu(self, participant_name: str) -> None:
        status = self._participant_config_status(participant_name)
        self._append_report(
            "participant_menu_opened",
            participant=participant_name,
            configured=status["configured"],
            mode=status["mode"],
            provider=status["provider"],
            model=status["model"],
        )

        content = BoxLayout(
            orientation="vertical",
            spacing=8,
            padding=12,
        )
        title = Label(
            text=f"{participant_name}\n"
                 f"{status['provider'] or 'not configured'} / "
                 f"{status['model'] or 'no model'}",
            size_hint_y=None,
            height=70,
        )
        title.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-12), max(1, value[1]-8))))
        content.add_widget(title)

        write_button = FeedbackButton(text="WRITE / GET ANSWER", size_hint_y=None, height=56)
        write_button.bind(
            on_release=lambda *_: (
                popup.dismiss(),
                self._open_participant_chat(participant_name),
            )
        )
        content.add_widget(write_button)

        remote_button = FeedbackButton(text="REMOTE DEVICE / ADMIN MODULE", size_hint_y=None, height=50)
        remote_button.bind(on_release=lambda *_: (popup.dismiss(), self._open_remote_participant()))
        content.add_widget(remote_button)

        settings_button = FeedbackButton(text="SETTINGS", size_hint_y=None, height=56)
        settings_button.bind(
            on_release=lambda *_: (
                popup.dismiss(),
                self._open_participant_settings(participant_name),
            )
        )
        content.add_widget(settings_button)

        close_button = FeedbackButton(text="CLOSE", size_hint_y=None, height=56)
        close_button.bind(on_release=lambda *_: popup.dismiss())
        content.add_widget(close_button)
        for action_button in (write_button, remote_button, settings_button, close_button):
            action_button.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-12), max(1, value[1]-8))))

        popup = Popup(
            title=participant_name,
            content=content,
            size_hint=(0.9, 0.72),
        )
        popup.open()

    def _open_participant_settings(self, participant_name: str) -> None:
        self._append_report(
            "participant_settings_opened",
            participant=participant_name,
        )
        from llm_settings import LLMSettingsPopup
        route_id = self.message_distributor.route_for_participant(participant_name)
        LLMSettingsPopup(
            self.user_data_dir,
            route_id=route_id,
            on_report=lambda event, **data: self._append_report(
                "router_" + event,
                **{"participant": participant_name, **data},
            ),
            on_copy=self._copy_to_clipboard,
        ).open()

    def _open_participant_chat(self, participant_name: str) -> None:
        status = self._participant_config_status(participant_name)
        route_id = status["route_id"]
        mode = status["mode"]
        self._append_report(
            "participant_chat_opened",
            participant=participant_name,
            configured=status["configured"],
            mode=mode,
            provider=status["provider"],
            model=status["model"],
        )

        history = self.private_histories.setdefault(
            participant_name, self.workspace.load_named_history(participant_name)
        )
        output_lines = [
            f"{'You' if item.get('role') == 'user' else participant_name}:\n{item.get('content', '')}"
            for item in history
        ]
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        output = TextInput(
            text="\n\n".join(output_lines) or f"{participant_name} private conversation.",
            readonly=True,
            multiline=True,
        )
        prompt = TextInput(
            hint_text=f"Private message to {participant_name}...",
            multiline=True,
            size_hint_y=None,
            height=110,
            write_tab=False,
        )
        send = FeedbackButton(text="SEND PRIVATELY", size_hint_y=None, height=54)
        publish = FeedbackButton(
            text="PUBLISH LAST EXCHANGE TO COMMON CHAT",
            size_hint_y=None,
            height=48,
        )
        close = FeedbackButton(text="CLOSE", size_hint_y=None, height=54)
        for action_button in (send, publish, close):
            action_button.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-12), max(1, value[1]-8))))
        content.add_widget(output)
        content.add_widget(prompt)
        content.add_widget(send)
        content.add_widget(publish)
        content.add_widget(close)
        popup = Popup(
            title=f"{participant_name} PRIVATE CHAT",
            content=content,
            size_hint=(0.94, 0.88),
        )
        last_exchange: dict[str, Any] = {}

        def publish_last_exchange(*_args: Any) -> None:
            exchange = last_exchange.get("messages")
            if not exchange:
                output.text += "\n\nNo completed private exchange to publish."
                return
            if last_exchange.get("published"):
                output.text += "\n\nThis exchange was already published."
                return
            self.common_history.extend(exchange)
            rendered = "\n\n".join(
                f"{'Owner' if item['role'] == 'user' else participant_name}:\n{item['content']}"
                for item in exchange
            )
            self.chat_output.text += f"\n\n[PUBLISHED FROM {participant_name} PRIVATE CHAT]\n{rendered}"
            last_exchange["published"] = True
            self._append_report(
                "participant_private_exchange_published",
                participant=participant_name,
                route_id=route_id,
                message_count=len(exchange),
            )
            self.status.text = f"Last private exchange from {participant_name} published to common chat."

        def send_message(*_args: Any) -> None:
            message = prompt.text.strip()
            if not message:
                return
            if not self.message_distributor.dialogue_enabled:
                self._append_report(
                    "participant_request_rejected",
                    participant=participant_name,
                    reason="dialogue_stopped",
                )
                output.text = "Dialogue is stopped. Resume it before sending new LLM requests."
                return
            prompt.text = ""
            send.disabled = True
            output.text += f"\n\nYou: {message}\n\nSending privately..."
            common_context = list(self.common_history)
            private_context = list(self.private_histories.get(participant_name, []))
            request_message = self._practical_instructions(message)
            request_history = common_context + private_context + [
                {"role": "user", "content": request_message}
            ]
            self._append_report(
                "participant_request_started",
                participant=participant_name,
                route_id=route_id,
                mode=mode,
                prompt=message,
                provider=status["provider"],
                model=status["model"],
                common_history_count=len(common_context),
                private_history_count=len(private_context),
            )

            def run_chat() -> None:
                try:
                    self._append_report(
                        "participant_api_request_sent",
                        participant=participant_name,
                        route_id=route_id,
                        mode=mode,
                        provider=status["provider"],
                        model=status["model"],
                        history_count=len(request_history),
                    )
                    result = self._dispatch_with_rate_limit_retry(
                        self.user_data_dir,
                        participant_name,
                        request_message,
                        mode=mode,
                        history=request_history,
                        report=lambda event, **data: self._append_report(
                            "participant_" + event,
                            **{"participant": participant_name, **data},
                        ),
                    )
                    response = result["response"]
                    event = (
                        "participant_api_response_received",
                        {
                            "participant": participant_name,
                            "route_id": route_id,
                            "mode": mode,
                            "provider": result["provider"],
                            "model": result["model"],
                            "response": response,
                        },
                    )
                    text_value = response
                except Exception as exc:
                    event = (
                        "participant_request_failed",
                        {
                            "participant": participant_name,
                            "route_id": route_id,
                            "mode": mode,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    text_value = f"FAILED: {type(exc).__name__}: {exc}"

                def finish(*_finish_args: Any) -> None:
                    self._append_report(event[0], **event[1])
                    self.participant_live_status[participant_name] = (event[0] == "participant_api_response_received")
                    self._refresh_participant_buttons()
                    if event[0] == "participant_api_response_received":
                        exchange = [
                            {"role": "user", "content": message},
                            {"role": "assistant", "content": text_value},
                        ]
                        self.private_histories.setdefault(participant_name, []).extend(exchange)
                        self.workspace.save_named_history(
                            participant_name, self.private_histories[participant_name]
                        )
                        last_exchange["messages"] = exchange
                        last_exchange["published"] = False
                        history_text = "\n\n".join(
                            f"{'You' if item['role'] == 'user' else participant_name}:\n{item['content']}"
                            for item in self.private_histories[participant_name]
                        )
                        output.text = history_text
                    else:
                        output.text += f"\n\n{text_value}"
                    send.disabled = False

                Clock.schedule_once(finish, 0)

            from threading import Thread
            Thread(
                target=run_chat,
                name=f"yj64-{participant_name.lower().replace(' ', '-')}-chat",
                daemon=True,
            ).start()

        send.bind(on_release=send_message)
        publish.bind(on_release=publish_last_exchange)
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _open_group_dialogue(self, *_: Any) -> None:
        self.message_distributor.set_private_participant(None)
        participants = [
            name
            for name in ("Participant 1", "Participant 2", "Participant 3")
            if self._participant_config_status(name)["configured"]
        ]
        if len(participants) < 2:
            self._append_report(
                "group_dialogue_start_rejected",
                reason="at_least_two_participants_required",
                participants=participants,
            )
            self.status.text = "Configure at least two participants first."
            return

        self.message_distributor.reset_queue()
        self._append_report(
            "group_dialogue_opened",
            participants=participants,
            mode=self.message_distributor.mode,
            route_ids={
                name: self.message_distributor.route_for_participant(name)
                for name in participants
            },
        )
        content = BoxLayout(orientation="vertical", spacing=8, padding=12)
        output = TextInput(
            text="Group dialogue is ready.\n",
            readonly=True,
            multiline=True,
        )
        prompt = TextInput(
            hint_text="Your question to the participants...",
            multiline=True,
            size_hint_y=None,
            height=110,
            write_tab=False,
        )
        cycle_row = BoxLayout(spacing=8, size_hint_y=None, height=48)
        rounds_label = Label(text="Rounds per participant:", size_hint_x=0.65, halign="left", valign="middle")
        rounds_label.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-6), max(1, value[1]-6))))
        cycle_row.add_widget(rounds_label)
        cycles_input = TextInput(
            text="3", multiline=False, input_filter="int", size_hint_x=0.35,
        )
        cycle_row.add_widget(cycles_input)
        controls = BoxLayout(
            spacing=8,
            size_hint_y=None,
            height=54,
        )
        toggle = FeedbackButton(
            text="START GROUP DIALOGUE",
            size_hint_x=1,
            background_color=(0.85, 0.2, 0.2, 1),
        )
        controls.add_widget(toggle)
        close = FeedbackButton(text="CLOSE", size_hint_y=None, height=54)
        for action_button in (toggle, close):
            action_button.bind(size=lambda widget, value: setattr(widget, "text_size", (max(1, value[0]-12), max(1, value[1]-8))))
        content.add_widget(output)
        content.add_widget(prompt)
        content.add_widget(cycle_row)
        content.add_widget(controls)
        content.add_widget(close)

        popup = Popup(
            title="GROUP DIALOGUE",
            content=content,
            size_hint=(0.95, 0.90),
            auto_dismiss=False,
        )

        state = {
            "running": False,
            "stop_requested": False,
        }

        def append_chat(text_value: str) -> None:
            output.text = output.text.rstrip() + "\n" + text_value + "\n"

        def request_stop(*_args: Any) -> None:
            state["stop_requested"] = True
            self.message_distributor.set_dialogue_enabled(False)
            toggle.text = "START GROUP DIALOGUE"
            toggle.background_color = (0.85, 0.2, 0.2, 1)
            self._append_report("group_dialogue_stop_requested")
            append_chat("[STOP REQUESTED] Waiting for the current request to finish.")

        def run_dialogue(question: str, max_cycles: int) -> None:
            messages: list[dict[str, str]] = [
                {"speaker": "Owner", "text": question}
            ]
            seen_by = {name: 0 for name in participants}
            turn = 0
            self._append_report(
                "group_dialogue_started",
                participants=participants,
                question=question,
                max_cycles=max_cycles,
                max_turns=max_cycles * len(participants),
            )

            while (
                turn < max_cycles * len(participants)
                and not state["stop_requested"]
                and self.message_distributor.dialogue_enabled
            ):
                participant = self.message_distributor.next_participant(participants)
                status = self._participant_config_status(participant)
                history: list[dict[str, str]] = []
                for item in messages:
                    role = "assistant" if item["speaker"] == participant else "user"
                    history.append({
                        "role": role,
                        "content": f"{item['speaker']}: {item['text']}",
                    })
                request_text = self._practical_instructions(messages[-1]["text"])
                if history:
                    history[-1]["content"] = request_text
                new_count = len(messages) - seen_by[participant]
                self._append_report(
                    "group_dialogue_turn_started",
                    participant=participant,
                    turn=turn + 1,
                    new_messages=new_count,
                )
                Clock.schedule_once(
                    lambda _dt, p=participant: append_chat(f"\n[{p} is thinking...]"),
                    0,
                )
                try:
                    result = self.message_distributor.dispatch_message(
                        self.user_data_dir,
                        participant,
                        request_text,
                        history=history,
                        report=lambda event, **data: self._append_report(
                            "group_dialogue_" + event,
                            **{"participant": participant, **data},
                        ),
                    )
                    response = result["response"]
                    messages.append({"speaker": participant, "text": response})
                    seen_by[participant] = len(messages)
                    self._append_report(
                        "group_dialogue_turn_completed",
                        participant=participant,
                        turn=turn + 1,
                        response=response,
                        unseen_messages=new_count,
                    )
                    Clock.schedule_once(
                        lambda _dt, p=participant, r=response:
                        append_chat(f"{p}:\n{r}"),
                        0,
                    )
                except Exception as exc:
                    self._append_report(
                        "group_dialogue_turn_failed",
                        participant=participant,
                        turn=turn + 1,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
                    Clock.schedule_once(
                        lambda _dt, p=participant, e=exc:
                        append_chat(f"{p} FAILED: {type(e).__name__}: {e}"),
                        0,
                    )
                    break
                turn += 1
            state["running"] = False
            self.message_distributor.set_dialogue_enabled(False)
            def finish_dialogue_ui(_dt: float) -> None:
                toggle.text = "START GROUP DIALOGUE"
                toggle.background_color = (0.85, 0.2, 0.2, 1)
            Clock.schedule_once(finish_dialogue_ui, 0)
            self._append_report(
                "group_dialogue_stopped",
                participants=participants,
                turns=turn,
                stop_requested=state["stop_requested"],
            )

        def start_dialogue(*_args: Any) -> None:
            if state["running"]:
                request_stop()
                return
            question = prompt.text.strip()
            if not question:
                return
            try:
                max_cycles = int(cycles_input.text or "3")
            except ValueError:
                cycles_input.text = "3"
                self.status.text = "Dialogue rounds must be a number from 1 to 20."
                return
            if not 1 <= max_cycles <= 20:
                self.status.text = "Dialogue rounds must be between 1 and 20."
                return
            self.message_distributor.set_dialogue_enabled(True)
            state["running"] = True
            state["stop_requested"] = False
            prompt.text = ""
            toggle.text = "STOP GROUP DIALOGUE"
            toggle.background_color = (0.2, 0.7, 0.3, 1)
            output.text = "Group dialogue started.\n"
            from threading import Thread
            Thread(
                target=run_dialogue,
                args=(question, max_cycles),
                name="yj64-group-dialogue",
                daemon=True,
            ).start()

        toggle.bind(on_release=start_dialogue)
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def _process_name(self) -> str:
        try:
            from jnius import autoclass
            return str(autoclass("android.os.Process").myProcessName())
        except Exception:
            return "unknown"

    def _write_main_pid(self) -> None:
        try:
            self.pid_path.parent.mkdir(parents=True, exist_ok=True)
            self.pid_path.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass

    def _append_report(self, event: str, **data: Any) -> None:
        try:
            self.report_path.parent.mkdir(parents=True, exist_ok=True)
            record = {
                "schema": "yj64.diagnostic.v1",
                "agent": "yj64-base-application",
                "event": event,
                "timestamp_ms": int(time.time() * 1000),
                "monotonic_ns": time.monotonic_ns(),
                "message_id": f"APP-{uuid.uuid4().hex}",
                "data": data,
            }
            with self.report_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                self.persistent_core.record_event(event, data)
            except Exception:
                # SQLite is secondary to the primary diagnostic JSONL; never block UI.
                pass
        except OSError:
            pass

    def _handle_uncaught_exception(self, exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
        try:
            formatted = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
            self._append_report(
                "python_uncaught_exception",
                error_type=getattr(exc_type, "__name__", str(exc_type)),
                message=str(exc_value),
                traceback=formatted[-24000:],
                pid=os.getpid(),
                process_name=self._process_name(),
                thread_name=threading.current_thread().name,
            )
        except Exception:
            pass
        previous = getattr(self, "_previous_excepthook", None)
        if previous is not None and previous is not self._handle_uncaught_exception:
            previous(exc_type, exc_value, exc_tb)

    def _handle_uncaught_thread_exception(self, args: Any) -> None:
        try:
            formatted = "".join(traceback.format_exception(
                args.exc_type, args.exc_value, args.exc_traceback
            ))
            self._append_report(
                "python_uncaught_thread_exception",
                error_type=getattr(args.exc_type, "__name__", str(args.exc_type)),
                message=str(args.exc_value),
                traceback=formatted[-24000:],
                pid=os.getpid(),
                process_name=self._process_name(),
                thread_name=getattr(args.thread, "name", "unknown"),
            )
        except Exception:
            pass
        previous = getattr(self, "_previous_thread_excepthook", None)
        if previous is not None:
            previous(args)

    def _open_monitor(self, *_: Any) -> None:
        self._append_report(
            "internal_monitor_window_requested",
            main_pid=os.getpid(),
            main_process_name=self._process_name(),
        )
        try:
            from jnius import autoclass
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            monitor_activity = autoclass(MONITOR_ACTIVITY_CLASS)
            intent = autoclass("android.content.Intent")(activity, monitor_activity)
            # Keep the monitor in its own Android task.  The base app task
            # remains alive in the background and can be returned to from Recents.
            intent.addFlags(
                0x10000000  # FLAG_ACTIVITY_NEW_TASK
                | 0x00020000  # FLAG_ACTIVITY_REORDER_TO_FRONT
            )
            activity.startActivity(intent)
            self.status.text = "Internal Monitor window requested."
        except Exception as exc:
            self.status.text = (
                "Internal Monitor window failed: "
                f"{type(exc).__name__}: {exc}"
            )

    def _open_llm_settings(self, *_: Any) -> None:
        self._append_report("llm_settings_open_requested")
        try:
            self._append_report("llm_settings_import_started")
            from llm_settings import LLMSettingsPopup
            self._append_report("llm_settings_import_succeeded")
            popup = LLMSettingsPopup(
                self.user_data_dir,
                route_id="route_owner",
                on_report=lambda event, **data: self._append_report(
                    "router_settings_" + event, **data
                ),
                on_copy=self._copy_to_clipboard,
            )
            self._append_report("llm_settings_popup_created")
            popup.open()
            self._append_report("llm_settings_popup_opened")
        except Exception as exc:
            import traceback
            self._append_report(
                "llm_settings_open_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                traceback=traceback.format_exc(),
            )
            self.status.text = (
                "LLM settings failed: "
                f"{type(exc).__name__}: {exc}"
            )

    def _test_llm_api(self, *_: Any) -> None:
        self._append_report("llm_api_test_started", scope="configured_participants")
        self.status.text = "Testing all configured participant connections..."

        def run_test() -> None:
            try:
                from llm_api import test_all_routes
                result = test_all_routes(
                    self.user_data_dir,
                    include_owner=False,
                    report=lambda event, **data: self._append_report(
                        "llm_api_" + event, **data
                    ),
                )
                report = result["report"]
                passed = sum(1 for item in result["results"] if item["status"] == "PASS")
                failed = len(result["results"]) - passed
                event = (
                    "llm_api_test_completed",
                    {
                        "scope": "configured_participants",
                        "tested_count": len(result["results"]),
                        "passed": passed,
                        "failed": failed,
                        "route_ids": [item["route_id"] for item in result["results"]],
                    },
                )
            except Exception as exc:
                report = (
                    "YJ-64 LLM API TEST — ALL PARTICIPANTS\n"
                    "Result: FAILED\n"
                    f"Error: {type(exc).__name__}: {exc}"
                )
                event = (
                    "llm_api_test_failed",
                    {
                        "scope": "configured_participants",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            def finish(*_args: Any) -> None:
                self._append_report(event[0], **event[1])
                self._copy_to_clipboard(report)
                self.status.text = report

            Clock.schedule_once(finish, 0)

        from threading import Thread
        Thread(target=run_test, name="yj64-llm-api-test-all-participants", daemon=True).start()

    def _test_llm_generation(self, *_: Any) -> None:
        prompt = "Reply with exactly: YJ64_OK"
        if not self.message_distributor.dialogue_enabled:
            self._append_report(
                "llm_generation_test_rejected",
                reason="dialogue_stopped",
                prompt=prompt,
            )
            self.status.text = "Dialogue is stopped. Resume it before sending new LLM requests."
            return

        target = self._chat_target_details()
        participant = target["participant"]
        route_id = target["route_id"]
        if not target["connected_participants"]:
            report_text = (
                "YJ-64 LLM GENERATION TEST — COMMON CHAT\n"
                "Result: FAILED\n"
                "Error: No configured participant connection is available."
            )
            self._append_report(
                "llm_generation_test_failed",
                scope="common_chat",
                route_id=route_id,
                error="No configured participant connection is available.",
            )
            self._copy_to_clipboard(report_text)
            self.chat_output.text += f"\n\n{report_text}"
            self.status.text = report_text
            return

        from llm_api import load_config
        config = load_config(self.user_data_dir, route_id=route_id)
        mode = "agent" if (config.get("agent_id") or "").strip() else "text"
        # Select mode for this route only; tests must not mutate the global chat mode.
        self._append_report(
            "llm_generation_test_chat_mode_selected",
            participant=participant,
            route_id=route_id,
            mode=mode,
            reason="match_configured_connection_test",
        )
        self._append_report(
            "llm_generation_test_started",
            scope="common_chat",
            prompt=prompt,
            participant=participant,
            route_id=route_id,
            mode=mode,
            connected_participants=target["connected_participants"],
            reason=target["reason"],
        )
        self.chat_output.text += (
            f"\n\nUser: {prompt}\nParticipant: {participant}\n"
            f"Route: {route_id} / {mode}\nTest request sent..."
        )
        self.status.text = f"Sending generation test through chat: {participant} / {route_id} / {mode}..."

        def run_test() -> None:
            try:
                result = self.message_distributor.dispatch_message(
                    self.user_data_dir,
                    participant,
                    prompt,
                    mode=mode,
                    report=lambda event, **data: self._append_report(
                        "llm_generation_chat_" + event, **data
                    ),
                )
                report_text = (
                    "YJ-64 LLM GENERATION TEST — COMMON CHAT\n"
                    f"Participant: {participant}\n"
                    f"Route: {route_id}\n"
                    f"Mode: {mode}\n"
                    f"Provider: {result['provider']}\n"
                    f"Model: {result['model']}\n"
                    f"Prompt: {prompt}\n"
                    "Result: SUCCESS\n"
                    f"Response: {result['response']}"
                )
                event = (
                    "llm_generation_test_completed",
                    {
                        "scope": "common_chat",
                        "participant": participant,
                        "route_id": route_id,
                        "mode": mode,
                        "provider": result["provider"],
                        "model": result["model"],
                        "prompt": prompt,
                        "response": result["response"],
                    },
                )
                chat_result = f"{participant}: {result['response']}"
            except Exception as exc:
                report_text = (
                    "YJ-64 LLM GENERATION TEST — COMMON CHAT\n"
                    f"Participant: {participant}\n"
                    f"Route: {route_id}\n"
                    f"Mode: {mode}\n"
                    f"Prompt: {prompt}\n"
                    "Result: FAILED\n"
                    f"Error: {type(exc).__name__}: {exc}"
                )
                event = (
                    "llm_generation_test_failed",
                    {
                        "scope": "common_chat",
                        "participant": participant,
                        "route_id": route_id,
                        "mode": mode,
                        "prompt": prompt,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
                chat_result = f"{participant}: FAILED — {type(exc).__name__}: {exc}"

            def finish(*_args: Any) -> None:
                self._append_report(event[0], **event[1])
                self._copy_to_clipboard(report_text)
                self.chat_output.text += f"\n{chat_result}"
                self.status.text = report_text

            Clock.schedule_once(finish, 0)

        from threading import Thread
        Thread(
            target=run_test,
            name="yj64-llm-generation-test-common-chat",
            daemon=True,
        ).start()

    def _chat_input_focus_changed(self, _instance: Any, focused: bool) -> None:
        self._append_report("llm_chat_input_focus_changed", focused=focused)

    def _chat_target_details(self) -> dict[str, Any]:
        from llm_api import route_config_exists

        connected = [
            name for name in ("Participant 1", "Participant 2", "Participant 3")
            if self._participant_config_status(name)["configured"]
        ]
        owner_connected = route_config_exists(self.user_data_dir, "route_owner")
        preferred = self.message_distributor.active_participant
        if preferred and self._participant_config_status(preferred)["configured"]:
            participant = preferred
            reason = "preferred_configured_participant"
        elif connected:
            participant = connected[0]
            reason = "first_configured_participant"
        else:
            participant = "Owner"
            reason = "owner_fallback"
        return {
            "participant": participant,
            "route_id": self.message_distributor.route_for_participant(participant),
            "connected_participants": connected,
            "owner_connected": owner_connected,
            "preferred": preferred,
            "reason": reason,
        }

    def _test_llm_chat_route(self, *_: Any) -> None:
        prompt = "Reply with exactly: YJ64_OK"
        if not self.message_distributor.dialogue_enabled:
            self._append_report(
                "llm_chat_route_test_rejected",
                reason="dialogue_stopped",
                prompt=prompt,
            )
            self.status.text = "Dialogue is stopped. Resume it before sending new LLM requests."
            return

        target = self._chat_target_details()
        participant = target["participant"]
        route_id = target["route_id"]
        mode = self._participant_config_status(participant)["mode"]
        self._append_report(
            "llm_chat_route_test_started",
            prompt=prompt,
            participant=participant,
            route_id=route_id,
            mode=mode,
            connected_participants=target["connected_participants"],
            owner_connected=target["owner_connected"],
            preferred=target["preferred"],
            reason=target["reason"],
        )
        self.status.text = f"Testing common-chat route: {participant} / {route_id} / {mode}..."

        def run_test() -> None:
            try:
                result = self.message_distributor.dispatch_message(
                    self.user_data_dir,
                    participant,
                    prompt,
                    mode=mode,
                    report=lambda event, **data: self._append_report(
                        "llm_chat_route_test_" + event, **data
                    ),
                )
                report_text = (
                    "YJ-64 COMMON CHAT ROUTE TEST\n"
                    f"Participant: {participant}\n"
                    f"Route: {route_id}\n"
                    f"Mode: {mode}\n"
                    f"Provider: {result['provider']}\n"
                    f"Model: {result['model']}\n"
                    f"Prompt: {prompt}\n"
                    "Result: SUCCESS\n"
                    f"Response: {result['response']}"
                )
                event = (
                    "llm_chat_route_test_succeeded",
                    {
                        "participant": participant,
                        "route_id": route_id,
                        "mode": mode,
                        "provider": result["provider"],
                        "model": result["model"],
                        "prompt": prompt,
                        "response": result["response"],
                    },
                )
            except Exception as exc:
                report_text = (
                    "YJ-64 COMMON CHAT ROUTE TEST\n"
                    f"Participant: {participant}\n"
                    f"Route: {route_id}\n"
                    f"Mode: {mode}\n"
                    f"Prompt: {prompt}\n"
                    "Result: FAILED\n"
                    f"Error: {type(exc).__name__}: {exc}"
                )
                event = (
                    "llm_chat_route_test_failed",
                    {
                        "participant": participant,
                        "route_id": route_id,
                        "mode": mode,
                        "prompt": prompt,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            def finish(*_args: Any) -> None:
                self._append_report(event[0], **event[1])
                self._copy_to_clipboard(report_text)
                self.chat_output.text = report_text
                self.status.text = report_text

            Clock.schedule_once(finish, 0)

        from threading import Thread
        Thread(
            target=run_test,
            name="yj64-common-chat-route-test",
            daemon=True,
        ).start()

    def _dispatch_with_rate_limit_retry(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Retry one rate-limited provider request after a short backoff, preserving its route."""
        try:
            return self.message_distributor.dispatch_message(*args, **kwargs)
        except Exception as exc:
            detail = (type(exc).__name__ + " " + str(exc)).lower()
            rate_limited = any(marker in detail for marker in ("429", "rate_limit", "rate limited", "too many requests", "1300"))
            if not rate_limited:
                raise
            participant = str(args[1]) if len(args) > 1 else "unknown"
            self._append_report("llm_rate_limit_backoff_started", participant=participant, delay_seconds=45, error=str(exc))
            time.sleep(45)
            self._append_report("llm_rate_limit_retry_started", participant=participant, attempt=2)
            return self.message_distributor.dispatch_message(*args, **kwargs)

    def _send_llm_chat(self, *_: Any) -> None:
        prompt = self.chat_input.text.strip()
        if not prompt:
            return
        if not self.message_distributor.dialogue_enabled:
            self._append_report("llm_chat_send_rejected", reason="dialogue_stopped", prompt=prompt)
            self.status.text = "Dialogue is stopped. Resume it before sending new LLM requests."
            return
        if self.dialogue_worker_active:
            self.status.text = "A dialogue is already running. Stop it before starting another."
            return
        target_details = self._chat_target_details()
        participants = list(target_details["connected_participants"])
        if not participants and target_details["owner_connected"]:
            participants = ["Owner"]
        if not participants:
            self._append_report("llm_chat_send_rejected", reason="no_configured_connections", prompt=prompt)
            self._append_chat_text(f"Owner: {prompt}\nNo configured participant connections are available.")
            self.status.text = "No configured participant connections are available."
            self.chat_input.text = ""
            return

        implementation_request = prompt.startswith("IMPLEMENTATION PHASE.")
        request_prompt = self._practical_instructions(prompt, implementation=implementation_request)
        targets = []
        for name in participants:
            details = self._participant_config_status(name)
            targets.append({
                "participant": name,
                "route_id": str(details["route_id"]),
                "mode": str(details["mode"]),
                "provider": str(details["provider"]),
                "model": str(details["model"]),
            })

        round_limit = self.dialogue_round_limit
        from threading import Event, Thread
        stop_event = Event()
        self.dialogue_stop_event = stop_event
        self.dialogue_worker_active = True
        self.chat_input.text = ""
        self.common_history.append({"role": "user", "content": prompt})
        self._save_common_history()
        self.chat_output.text = self._render_history()
        self._append_report(
            "llm_chat_dialogue_started",
            prompt=prompt,
            participants=participants,
            round_limit=round_limit,
            unlimited=round_limit == 0,
            history_count=len(self.common_history),
            policy="collect_all_participant_results_then_close_if_any_participant_failed",
        )
        self.status.text = "Sequential dialogue started: " + ", ".join(participants)

        def run_chat() -> None:
            successful = failed = rounds_completed = 0
            stop_reason = "round_limit_reached"
            try:
                round_number = 0
                while not stop_event.is_set() and self.message_distributor.dialogue_enabled:
                    round_number += 1
                    if round_limit and round_number > round_limit:
                        break
                    rounds_completed = round_number
                    successful_this_round = 0
                    failed_this_round = 0
                    self._append_report(
                        "llm_chat_round_started",
                        round_number=round_number,
                        history_count=len(self.common_history),
                    )

                    # Attempt every configured participant before deciding whether the
                    # session can continue. One provider failure must not suppress others.
                    for target in targets:
                        if stop_event.is_set() or not self.message_distributor.dialogue_enabled:
                            stop_reason = "owner_stopped"
                            break
                        name = target["participant"]
                        turn_prompt = (
                            request_prompt if round_number == 1 else
                            "Continue the common dialogue. Consider the owner's original request and replies from other participants. "
                            "Add your next contribution without repeating the whole conversation."
                        )

                        # Exclude the target participant's own prior answers from its context.
                        history_snapshot = []
                        for item in self.common_history:
                            content = str(item.get("content") or "")
                            if item.get("role") == "assistant" and content.startswith(name + ":"):
                                continue
                            history_snapshot.append(dict(item))

                        # Agent/Conversations endpoints require the final input item to be
                        # a user message. This request-only copy does not mutate shared history.
                        if target["mode"] == "agent":
                            if history_snapshot and str(history_snapshot[-1].get("role") or "").lower() == "user":
                                last_content = str(history_snapshot[-1].get("content") or "")
                                if turn_prompt not in last_content:
                                    history_snapshot[-1]["content"] = (last_content + "\n\n" + turn_prompt).strip()
                            else:
                                history_snapshot.append({"role": "user", "content": turn_prompt})

                        self._append_report(
                            "llm_chat_participant_turn_started",
                            participant=name,
                            round_number=round_number,
                            route_id=target["route_id"],
                            provider=target["provider"],
                            model=target["model"],
                            history_count=len(history_snapshot),
                            own_previous_answers_excluded=True,
                        )
                        try:
                            result = self._dispatch_with_rate_limit_retry(
                                self.user_data_dir,
                                name,
                                turn_prompt,
                                mode=target["mode"],
                                history=history_snapshot,
                                report=lambda event, _p=name, _r=round_number, **data:
                                    self._append_report("llm_chat_" + event, **{"participant": _p, "round_number": _r, **data}),
                            )
                            returned_route = str(result.get("route_id") or "")
                            if returned_route and returned_route != target["route_id"]:
                                raise RuntimeError(
                                    f"{name} route mismatch: requested {target['route_id']}, "
                                    f"received {returned_route}; refusing to display a substituted response"
                                )
                            response = str(result.get("response") or "").strip()
                            if not response:
                                raise RuntimeError("Provider returned an empty response; turn marked as failed.")
                            display_name = self._participant_display_name(name)
                            self.common_history.append({"role": "assistant", "content": f"{name} [{display_name}] · Раунд {round_number}: {response}"})
                            self._save_common_history()
                            successful += 1
                            successful_this_round += 1
                            self.participant_live_status[name] = True
                            self._append_report(
                                "llm_chat_participant_turn_completed",
                                participant=name,
                                round_number=round_number,
                                route_id=result.get("route_id", target["route_id"]),
                                provider=result.get("provider", target["provider"]),
                                model=result.get("model", target["model"]),
                                response=response,
                                history_count=len(self.common_history),
                            )
                            Clock.schedule_once(
                                lambda _dt, speaker=name, body=response, rn=round_number:
                                    self._append_chat_text(f"{speaker} [{self._participant_display_name(speaker)}] · Раунд {rn}: {body}"),
                                0,
                            )
                        except Exception as exc:
                            failed += 1
                            failed_this_round += 1
                            self.participant_live_status[name] = False
                            err = f"{type(exc).__name__}: {exc}"
                            self.common_history.append({"role": "assistant", "content": f"{name} [{self._participant_display_name(name)}] · Раунд {round_number}: ERROR: {err}"})
                            self._save_common_history()
                            self._append_report(
                                "llm_chat_participant_turn_failed",
                                participant=name,
                                round_number=round_number,
                                route_id=target["route_id"],
                                provider=target["provider"],
                                model=target["model"],
                                error_type=type(exc).__name__,
                                error=str(exc),
                            )
                            Clock.schedule_once(
                                lambda _dt, speaker=name, body=err, rn=round_number:
                                    self._append_chat_text(f"{speaker}: ERROR — round {rn}:\n{body}"),
                                0,
                            )

                    self._append_report(
                        "llm_chat_round_completed",
                        round_number=round_number,
                        successful=successful_this_round,
                        failed=failed_this_round,
                        stopped=stop_event.is_set() or not self.message_distributor.dialogue_enabled,
                    )
                    if stop_event.is_set() or not self.message_distributor.dialogue_enabled:
                        stop_reason = "owner_stopped"
                        break
                    if successful_this_round == 0:
                        stop_reason = "all_participants_failed"
                        self._append_report("llm_chat_session_closed", reason=stop_reason, round_number=round_number)
                        break
                    if failed_this_round:
                        stop_reason = "participant_unavailable_after_retries"
                        self._append_report(
                            "llm_chat_session_closed",
                            reason=stop_reason,
                            round_number=round_number,
                            successful_this_round=successful_this_round,
                            failed_this_round=failed_this_round,
                        )
                        break
                else:
                    if stop_event.is_set() or not self.message_distributor.dialogue_enabled:
                        stop_reason = "owner_stopped"
            finally:
                def finish(*_args: Any) -> None:
                    self.dialogue_worker_active = False
                    self.dialogue_stop_event = None
                    self._save_common_history()
                    self.chat_output.text = self._render_history()
                    stopped = stop_event.is_set() or not self.message_distributor.dialogue_enabled
                    self._append_report(
                        "llm_chat_dialogue_completed",
                        rounds_completed=rounds_completed,
                        successful_turns=successful,
                        failed_turns=failed,
                        stopped=stopped,
                        stop_reason=stop_reason,
                        round_limit=round_limit,
                    )
                    self.status.text = (
                        f"Dialogue {'stopped' if stopped else 'completed'} after {rounds_completed} round(s): "
                        f"{successful} replies, {failed} errors. Reason: {stop_reason}."
                    )
                Clock.schedule_once(finish, 0)

        Thread(target=run_chat, name="yj64-sequential-dialogue", daemon=True).start()
    def _copy_to_clipboard(self, text: str) -> None:
        try:
            from jnius import autoclass
            context = autoclass("org.kivy.android.PythonActivity").mActivity
            clipboard = context.getSystemService(
                autoclass("android.content.Context").CLIPBOARD_SERVICE
            )
            clip = autoclass("android.content.ClipData").newPlainText(
                "YJ-64 LLM API report", text
            )
            clipboard.setPrimaryClip(clip)
        except Exception as exc:
            self._append_report(
                "llm_api_clipboard_failed",
                error_type=type(exc).__name__,
                error=str(exc),
            )

    def _poll_test_command(self, *_: Any) -> None:
        command_path = Path(self.user_data_dir) / TEST_COMMAND_RELATIVE_PATH
        if not command_path.is_file():
            return
        try:
            command = json.loads(command_path.read_text(encoding="utf-8"))
            command_path.unlink()
        except (OSError, ValueError):
            return
        if command.get("action") != "full_test":
            return
        test_id = str(command.get("test_id") or uuid.uuid4().hex)
        self._run_full_function_test(test_id)

    def _run_full_function_test(self, test_id: str) -> None:
        from threading import Thread

        def step(name: str, action: Any) -> tuple[bool, str]:
            self._append_report("full_test_step_started", test_id=test_id, step=name)
            try:
                result = action()
                self._append_report(
                    "full_test_step_completed",
                    test_id=test_id,
                    step=name,
                    result=result,
                )
                return True, str(result)
            except Exception as exc:
                self._append_report(
                    "full_test_step_failed",
                    test_id=test_id,
                    step=name,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return False, f"{type(exc).__name__}: {exc}"

        def worker() -> None:
            self._append_report("full_test_started", test_id=test_id)
            results: list[str] = []

            ok, value = step("report_storage", lambda: f"report_exists={self.report_path.is_file()}")
            results.append(f"report_storage: {'PASS' if ok else 'FAIL'} ({value})")

            ok, value = step(
                "process_identity",
                lambda: f"pid={os.getpid()},process={self._process_name()}",
            )
            results.append(f"process_identity: {'PASS' if ok else 'FAIL'} ({value})")

            def config_check() -> str:
                from llm_api import load_config
                config = load_config(self.user_data_dir)
                if not config.get("api_key"):
                    raise RuntimeError("LLM API key is not configured")
                if not config.get("model"):
                    raise RuntimeError("LLM model is not configured")
                return f"provider={config.get('provider')},model={config.get('model')}"

            ok, value = step("llm_config", config_check)
            results.append(f"llm_config: {'PASS' if ok else 'FAIL'} ({value})")

            def api_check() -> str:
                from llm_api import test_llm_api
                return str(test_llm_api(
                    self.user_data_dir,
                    report=lambda event, **data: self._append_report(
                        "full_test_llm_api_" + event,
                        test_id=test_id,
                        **data,
                    ),
                )["result"])

            ok, value = step("llm_api", api_check)
            results.append(f"llm_api: {'PASS' if ok else 'FAIL'} ({value})")

            def generation_check() -> str:
                from llm_api import generate_test_response
                result = generate_test_response(
                    self.user_data_dir,
                    report=lambda event, **data: self._append_report(
                        "full_test_llm_generation_" + event,
                        test_id=test_id,
                        **data,
                    ),
                )
                return str(result["response"])

            ok, value = step("llm_generation", generation_check)
            results.append(f"llm_generation: {'PASS' if ok else 'FAIL'} ({value})")

            ok, value = step(
                "diagnostic_agent_status",
                lambda: (
                    "status_file_present"
                    if (Path(self.user_data_dir) / "diagnostic-agent-status.json").is_file()
                    else "status_file_missing"
                ),
            )
            results.append(f"diagnostic_agent_status: {'PASS' if ok else 'FAIL'} ({value})")

            summary = "YJ-64 FULL FUNCTION TEST\n" + "\n".join(results)
            self._append_report("full_test_completed", test_id=test_id, summary=summary)
            result_path = Path(self.user_data_dir) / TEST_RESULT_RELATIVE_PATH
            try:
                result_path.write_text(
                    json.dumps(
                        {
                            "test_id": test_id,
                            "completed": True,
                            "summary": summary,
                            "timestamp_ms": int(time.time() * 1000),
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except OSError as exc:
                self._append_report(
                    "full_test_result_write_failed",
                    test_id=test_id,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )

            def finish(_dt: float) -> None:
                self._copy_to_clipboard(str(self.report_path))
                self.status.text = summary
            Clock.schedule_once(finish, 0)

        Thread(target=worker, name="yj64-full-function-test", daemon=True).start()

    def _read_report_text(self) -> str:
        try:
            return self.report_path.read_text(encoding="utf-8")
        except OSError as exc:
            return f"YJ-64 REPORT READ FAILED: {type(exc).__name__}: {exc}"

    def _ensure_service_started(self, *_: Any) -> None:
        """Start diagnostics alongside Base without closing or relaunching its UI."""
        try:
            from jnius import autoclass
            service_class = autoclass(SERVICE_CLASS)
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            service_class.start(activity, "")
            self._append_report(
                "internal_diagnostic_service_start_requested",
                pid=os.getpid(),
                process_name=self._process_name(),
                base_ui_kept_open=True,
            )
            self.status.text = (
                "Diagnostic agent requested. YJ-64 Base remains open while "
                "diagnostic events are forwarded to Monitor."
            )
        except Exception as exc:
            self._append_report(
                "internal_diagnostic_service_start_failed",
                error_type=type(exc).__name__,
                error=str(exc),
                pid=os.getpid(),
            )
            self.status.text = (
                "Diagnostic service start failed: "
                f"{type(exc).__name__}: {exc}"
            )

    def _refresh_status(self, *_: Any) -> None:
        path = Path(self.user_data_dir) / "diagnostic-agent-status.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.status.text = (
            "Embedded diagnostic agent\n"
            f"Bridge: {data.get('bridge_status', 'unknown')}\n"
            f"Self-diagnostic: {data.get('self_diagnostic', 'unknown')}\n"
            f"Base app: {data.get('target_launch', 'unknown')}\n"
            f"Last event: {data.get('event', 'unknown')}"
        )

    def on_start(self) -> None:
        self._append_report(
            "base_activity_started",
            pid=os.getpid(),
            process_name=self._process_name(),
        )

    def on_resume(self) -> None:
        self._append_report("base_activity_resumed")

    def on_pause(self) -> bool:
        self._append_report("base_activity_paused")
        try:
            self._save_common_history()
            self._auto_export_download_archive()
        except Exception as exc:
            self._append_report("memory_archive_auto_pause_failed", error_type=type(exc).__name__, error=str(exc))
        return True

    def on_stop(self) -> None:
        self._append_report("base_activity_stopped")


YJ64BaseApp().run()
