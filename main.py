import json
import os
import re

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.star.filter.event_message_type import EventMessageType

from .games.common import WordleBase
from .games.dict_manager import DictManager
from .games.wordle_classic import WordleClassic
from .games.worlde_octordle import WordleOctordle
from .games.wordle_handle import WordleHandle

IGNORGE_MSG = [
    "wordle start",
    "wordle octordle",
    "wordle handle",
    "wordle stop",
    "wordle rank",
    "wordle dict",
]


class PluginWordle(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.game_sessions: dict[str, WordleBase] = {}
        plugin_root = os.path.dirname(os.path.abspath(__file__))
        self.data_root = os.path.join(plugin_root, "data")
        self.dict_config_path = os.path.join(plugin_root, "dict_config.json")
        self.scores_path = os.path.join(plugin_root, "scores.json")
        self.scores: dict[str, dict[str, dict]] = self._load_scores()
        self.dict_manager = DictManager(self.data_root, self.dict_config_path)

    def _load_scores(self) -> dict[str, dict[str, dict]]:
        try:
            if os.path.exists(self.scores_path):
                with open(self.scores_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载积分失败: {e!s}")
        return {}

    def _save_scores(self) -> None:
        try:
            with open(self.scores_path, "w", encoding="utf-8") as f:
                json.dump(self.scores, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存积分失败: {e!s}")

    def _idiom_extra(self, game: WordleBase) -> str:
        if not isinstance(game, WordleHandle):
            return ""
        parts = []
        if game.explanation:
            parts.append(f"\n释义: {game.explanation}")
        if game.source:
            parts.append(f"\n出处: {game.source}")
        return "".join(parts)

    def _record_guess(
        self, group_id: str, user_id: str, user_name: str, won: bool
    ) -> None:
        group_scores = self.scores.setdefault(group_id, {})
        record = group_scores.setdefault(
            user_id, {"name": user_name, "guesses": 0, "wins": 0}
        )
        if user_name:
            record["name"] = user_name
        record["guesses"] += 1
        if won:
            record["wins"] += 1
        self._save_scores()

    def _dict_banner(self, dict_name: str) -> str:
        d = self.dict_manager.get_dict(dict_name)
        wl = self.dict_manager.get_active_wordlist(dict_name)
        if not d or not wl:
            return ""
        return f"[词典: {d.display_name} / 词库: {wl.display_name}]"

    @filter.command_group("wordle")
    def wordle(self):
        """Wordle 游戏相关命令"""
        pass

    @wordle.command("start")
    async def start_wordle(self, event: AstrMessageEvent, length: int = 5):
        """开始一局游戏，例如 `wordle start 5`"""
        session_id = event.unified_msg_origin

        if session_id in self.game_sessions:
            del self.game_sessions[session_id]

        result = WordleClassic.pick_answer(self.dict_manager, length)
        if not result:
            yield event.plain_result(f"未找到长度为{length}的单词")
            return

        answer, valid_words = result
        game = WordleClassic(answer, valid_words)
        self.game_sessions[session_id] = game
        banner = self._dict_banner(WordleClassic.DICT_NAME)
        yield event.plain_result(f"Wordle 游戏已开始 {banner}，请输入猜测".strip())
        logger.info(f"{session_id} 的答案是：{answer}")

    @wordle.command("octordle")
    async def start_octordle(self, event: AstrMessageEvent):
        """开始一局 Octordle（同时进行 8 局 Wordle）游戏"""
        session_id = event.unified_msg_origin

        if session_id in self.game_sessions:
            del self.game_sessions[session_id]

        result = WordleOctordle.pick_answers(self.dict_manager)
        if not result:
            yield event.plain_result("未找到足够的单词")
            return

        answers, valid_words = result
        game = WordleOctordle(answers, valid_words)
        self.game_sessions[session_id] = game
        banner = self._dict_banner(WordleOctordle.DICT_NAME)
        yield event.plain_result(f"Octordle 游戏已开始 {banner}，请输入猜测".strip())
        logger.info(f"{session_id} 的答案是：{answers}")

    @wordle.command("handle")
    async def start_handle(self, event: AstrMessageEvent):
        """开始一局汉兜（中文成语 Wordle）游戏"""
        session_id = event.unified_msg_origin

        if session_id in self.game_sessions:
            del self.game_sessions[session_id]

        result = WordleHandle.pick_answer(self.dict_manager)
        if not result:
            yield event.plain_result("成语词库未加载，无法开始汉兜游戏")
            return

        answer, idioms, explanation, source = result
        game = WordleHandle(answer, idioms, explanation=explanation, source=source)
        self.game_sessions[session_id] = game
        banner = self._dict_banner(WordleHandle.DICT_NAME)
        yield event.plain_result(f"汉兜游戏已开始 {banner}，请输入猜测".strip())
        logger.info(f"{session_id} 的答案是：{answer}")

    @wordle.command("stop")
    async def stop_wordle(self, event: AstrMessageEvent):
        """终止游戏"""
        session_id = event.unified_msg_origin
        if session_id in self.game_sessions:
            yield event.plain_result("已结束当前游戏，正确答案是: " + self.game_sessions[session_id].answer)
            del self.game_sessions[session_id]
        else:
            yield event.plain_result("当前未开始游戏")

    @wordle.command("dict")
    async def manage_dict(
        self,
        event: AstrMessageEvent,
        dict_name: str = "",
        action: str = "",
        target: str = "",
    ):
        """词典管理：`wordle dict` 列出全部；`wordle dict <name>` 列出词库；
        `wordle dict <name> set <wordlist>` 切换启用词库。
        """
        if not dict_name:
            dicts = self.dict_manager.dictionaries
            if not dicts:
                yield event.plain_result("未找到任何词典")
                return
            lines = ["可用词典："]
            for d in dicts.values():
                active = self.dict_manager.get_active(d.name) or "-"
                active_wl = d.wordlists.get(active)
                active_disp = active_wl.display_name if active_wl else active
                lines.append(
                    f"- {d.name} ({d.display_name}) 当前词库: {active} ({active_disp})"
                )
            yield event.plain_result("\n".join(lines))
            return

        d = self.dict_manager.get_dict(dict_name)
        if not d:
            yield event.plain_result(f"未找到词典: {dict_name}")
            return

        if not action:
            active = self.dict_manager.get_active(d.name)
            lines = [f"词典 {d.name} ({d.display_name}) 的词库："]
            for wl in d.wordlists.values():
                mark = " *" if wl.name == active else ""
                lines.append(f"- {wl.name} ({wl.display_name}){mark}")
            lines.append("（标 * 为当前启用；用 `wordle dict <name> set <wordlist>` 切换）")
            yield event.plain_result("\n".join(lines))
            return

        if action != "set":
            yield event.plain_result(f"未知操作: {action}，可用：set")
            return

        if not target:
            yield event.plain_result("用法：wordle dict <name> set <wordlist>")
            return

        if not self.dict_manager.set_active(d.name, target):
            yield event.plain_result(f"词库 {target} 不存在于词典 {d.name}")
            return

        wl = self.dict_manager.get_wordlist(d.name, target)
        yield event.plain_result(
            f"已将词典 {d.name} ({d.display_name}) 的启用词库切换为 {target} ({wl.display_name if wl else target})"
        )

    @wordle.command("rank")
    async def show_rank(self, event: AstrMessageEvent, scope: str = ""):
        """查看排行榜"""
        if scope == "global":
            target: dict[str, dict] = {}
            for group_scores in self.scores.values():
                for uid, info in group_scores.items():
                    agg = target.setdefault(
                        uid, {"name": info["name"], "guesses": 0, "wins": 0}
                    )
                    agg["name"] = info["name"]
                    agg["guesses"] += info["guesses"]
                    agg["wins"] += info["wins"]
            title = "Wordle 全局排行榜"
        else:
            if event.is_private_chat():
                yield event.plain_result(
                    "私聊不参与排行榜，使用 wordle rank global 查看全局排行榜"
                )
                return
            group_id = event.get_group_id()
            target = self.scores.get(group_id, {})
            title = "Wordle 群排行榜"

        if not target:
            yield event.plain_result("当前还没有任何记录")
            return

        sorted_users = sorted(
            target.items(),
            key=lambda kv: (-kv[1]["wins"], kv[1]["guesses"]),
        )

        lines = [title]
        for idx, (_uid, info) in enumerate(sorted_users[:10], 1):
            lines.append(
                f"{idx}. {info['name']} - 猜对 {info['wins']} 次 / 共猜 {info['guesses']} 次"
            )
        yield event.plain_result("\n".join(lines))

    @filter.event_message_type(EventMessageType.ALL)
    async def on_all_message(self, event: AstrMessageEvent):
        msg = event.get_message_str()
        session_id = event.unified_msg_origin
        if session_id in self.game_sessions and event.is_at_or_wake_command:
            game = self.game_sessions[session_id]

            for ignore in IGNORGE_MSG:
                if ignore in msg:
                    return

            err = game.validate_input(msg)
            if err:
                yield event.plain_result(err)
                return

            image_result = await game.guess(msg)

            if not event.is_private_chat():
                sender_id = event.get_sender_id()
                sender_name = event.get_sender_name() or sender_id
                group_id = event.get_group_id()
                self._record_guess(
                    group_id, sender_id, sender_name, won=bool(game.is_won)
                )

            session_id_ps = re.sub(r'[\\/:*?"<>|!]', "_", session_id)
            img_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                f"{session_id_ps}_{len(game.guesses)}_wordle.png",
            )
            with open(img_path, "wb") as f:
                f.write(image_result)

            if game.is_won:
                sender_info = (
                    event.get_sender_name()
                    if event.get_sender_name()
                    else event.get_sender_id()
                )
                game_status = f"恭喜 {sender_info} 猜对了！正确答案是: {game.answer}"
                game_status += self._idiom_extra(game)
                del self.game_sessions[session_id]
            elif game.is_game_over:
                game_status = f"游戏结束。正确答案是: {game.answer}"
                game_status += self._idiom_extra(game)
                del self.game_sessions[session_id]
            else:
                game_status = f"已猜测 {len(game.guesses)}/{game.max_attempts} 次"

            await event.send(MessageChain().file_image(img_path).message(game_status))

            os.remove(img_path)
