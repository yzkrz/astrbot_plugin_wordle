import os
import random
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from .common import WordleBase
from .dict_manager import DictManager, load_chengyu_full, load_chengyu_names

CELL_WIDTH = 80
CELL_HEIGHT = 80
CELL_INNER_GAP = 4
CELL_MARGIN = 8
GRID_MARGIN = 12

COLOR_GREEN = (29, 156, 156)
COLOR_ORANGE = (222, 117, 37)
COLOR_GRAY = (68, 77, 92)
COLOR_WHITE = (255, 255, 255)
COLOR_CELL_BG = (247, 248, 249)
COLOR_BG = (255, 255, 255)

GRAY_ALPHA_CHAR = 0.8
GRAY_ALPHA_PINYIN = 0.45


def _blend(fg: tuple, bg: tuple, alpha: float) -> tuple:
    return tuple(round(fg[i] * alpha + bg[i] * (1 - alpha)) for i in range(3))


def _fb_color(fb_val: int, gray_alpha: float, bg: tuple) -> tuple:
    if fb_val == 2:
        return COLOR_GREEN
    if fb_val == 1:
        return COLOR_ORANGE
    return _blend(COLOR_GRAY, bg, gray_alpha)


FONT_CHAR_SIZE = 30
FONT_PINYIN_SIZE = 16
FONT_SUP_SIZE = 12

TONE_SUPERSCRIPTS = {0: "0", 1: "1", 2: "2", 3: "3", 4: "4"}

_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fonts")
SERIF_FONT_PATH = os.path.join(_FONTS_DIR, "NotoSerifSC-Regular.ttf")
MONO_FONT_PATH = os.path.join(_FONTS_DIR, "Consolas-Regular.ttf")


def _load_font(size: int, path: str) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(path, size)
    except Exception as e:
        raise RuntimeError(f"加载字体失败 {path}: {e!s}") from e


def _match(guess: list, answer: list) -> list[int]:
    n = len(guess)
    fb = [0] * n
    counts: dict = {}
    for i in range(n):
        if guess[i] == answer[i]:
            fb[i] = 2
        else:
            counts[answer[i]] = counts.get(answer[i], 0) + 1
    for i in range(n):
        if fb[i] != 2:
            c = guess[i]
            if counts.get(c, 0) > 0:
                fb[i] = 1
                counts[c] -= 1
    return fb


class WordleHandle(WordleBase):
    DICT_NAME = "chengyu"

    def __init__(
        self,
        answer: str,
        idioms: dict[str, list[list]],
        explanation: str = "",
        source: str = "",
    ):
        if answer not in idioms:
            raise ValueError(f"answer {answer!r} not in idioms dict")
        self._answer = answer
        self._answer_pinyin = idioms[answer]
        self._idioms = idioms
        self._explanation = explanation
        self._source = source
        self._valid_words = list(idioms.keys())
        self._length = 4
        self._max_attempts = 10
        self._guesses: list[str] = []
        self._feedbacks: list[dict[str, list[int]]] = []
        self._font_char = _load_font(FONT_CHAR_SIZE, SERIF_FONT_PATH)
        self._font_pinyin = _load_font(FONT_PINYIN_SIZE, MONO_FONT_PATH)
        self._font_sup = _load_font(FONT_SUP_SIZE, MONO_FONT_PATH)

    @classmethod
    def pick_answer(
        cls, dict_manager: DictManager
    ) -> tuple[str, dict[str, list[list]], str, str] | None:
        """从启用词库选答案；合法猜测集合（含拼音）来自 all 词库。"""
        all_wl = dict_manager.get_all_wordlist(cls.DICT_NAME)
        active_wl = dict_manager.get_active_wordlist(cls.DICT_NAME)
        if not all_wl or not active_wl:
            return None
        idioms, meta = load_chengyu_full(all_wl)
        if not idioms:
            return None
        if active_wl.name == all_wl.name:
            answer_pool = list(idioms.keys())
        else:
            answer_pool = [n for n in load_chengyu_names(active_wl) if n in idioms]
        if not answer_pool:
            return None
        answer = random.choice(answer_pool)
        m = meta.get(answer, {})
        return answer, idioms, m.get("explanation", ""), m.get("source", "")

    async def guess(self, word: str) -> bytes:
        self._guesses.append(word)
        guess_pinyin = self._idioms[word]

        answer_chars = list(self._answer)
        guess_chars = list(word)
        answer_inits = [p[0] for p in self._answer_pinyin]
        answer_finals = [p[1] for p in self._answer_pinyin]
        answer_tones = [p[2] for p in self._answer_pinyin]
        guess_inits = [p[0] for p in guess_pinyin]
        guess_finals = [p[1] for p in guess_pinyin]
        guess_tones = [p[2] for p in guess_pinyin]

        self._feedbacks.append({
            "char": _match(guess_chars, answer_chars),
            "init": _match(guess_inits, answer_inits),
            "final": _match(guess_finals, answer_finals),
            "tone": _match(guess_tones, answer_tones),
        })

        return await self.gen_image()

    async def gen_image(self) -> bytes:
        cell_stride_x = CELL_WIDTH + CELL_MARGIN
        cell_stride_y = CELL_HEIGHT + CELL_MARGIN
        width = GRID_MARGIN * 2 + cell_stride_x * self._length - CELL_MARGIN
        height = GRID_MARGIN * 2 + cell_stride_y * self._max_attempts - CELL_MARGIN

        img = Image.new("RGB", (width, height), COLOR_BG)
        draw = ImageDraw.Draw(img)

        for row in range(self._max_attempts):
            for col in range(self._length):
                x = GRID_MARGIN + col * cell_stride_x
                y = GRID_MARGIN + row * cell_stride_y
                self._draw_cell(draw, x, y, row, col)

        with BytesIO() as out:
            img.save(out, format="PNG")
            return out.getvalue()

    def _draw_cell(self, draw: ImageDraw.ImageDraw, x: int, y: int, row: int, col: int) -> None:
        rect = [x, y, x + CELL_WIDTH, y + CELL_HEIGHT]

        if row >= len(self._guesses):
            draw.rectangle(rect, fill=COLOR_CELL_BG)
            return

        word = self._guesses[row]
        ch = word[col]
        ini, fin, tone = self._idioms[word][col]
        fb = self._feedbacks[row]
        fb_char = fb["char"][col]
        fb_init = fb["init"][col]
        fb_final = fb["final"][col]
        fb_tone = fb["tone"][col]
        all_green = (fb_char == 2 and fb_init == 2 and fb_final == 2 and fb_tone == 2)

        if all_green:
            bg = COLOR_GREEN
            c_char = COLOR_WHITE
            c_init = COLOR_WHITE
            c_final = COLOR_WHITE
            c_tone = COLOR_WHITE
        else:
            bg = COLOR_CELL_BG
            c_char = _fb_color(fb_char, GRAY_ALPHA_CHAR, bg)
            c_init = _fb_color(fb_init, GRAY_ALPHA_PINYIN, bg)
            c_final = _fb_color(fb_final, GRAY_ALPHA_PINYIN, bg)
            c_tone = _fb_color(fb_tone, GRAY_ALPHA_PINYIN, bg)

        draw.rectangle(rect, fill=bg)
        
        total_h = FONT_PINYIN_SIZE + CELL_INNER_GAP + FONT_CHAR_SIZE
        top = y + (CELL_HEIGHT - total_h) // 2
        pinyin_center_y = top + FONT_PINYIN_SIZE // 2
        char_center_y = top + FONT_PINYIN_SIZE + CELL_INNER_GAP + FONT_CHAR_SIZE // 2

        self._draw_pinyin(draw, x, pinyin_center_y, ini, fin, tone, c_init, c_final, c_tone)
        self._draw_char(draw, x, char_center_y, ch, c_char)

    def _text_width(self, font: ImageFont.FreeTypeFont, text: str) -> int:
        if not text:
            return 0
        try:
            return int(font.getlength(text))
        except AttributeError:
            l, _, r, _ = font.getbbox(text)
            return int(r - l)

    def _draw_pinyin(
        self, draw: ImageDraw.ImageDraw, x: int, center_y: int,
        ini: str, fin: str, tone: int,
        c_init: tuple, c_final: tuple, c_tone: tuple,
    ) -> None:
        sup = TONE_SUPERSCRIPTS.get(tone, str(tone))
        w_ini = self._text_width(self._font_pinyin, ini)
        w_fin = self._text_width(self._font_pinyin, fin)
        pinyin_width = w_ini + w_fin
        start_x = x + (CELL_WIDTH - pinyin_width) // 2

        cur = start_x
        if ini:
            draw.text((cur, center_y), ini, fill=c_init, font=self._font_pinyin, anchor="lm")
            cur += w_ini
        if fin:
            draw.text((cur, center_y), fin, fill=c_final, font=self._font_pinyin, anchor="lm")
            cur += w_fin
        sup_y = center_y - FONT_PINYIN_SIZE // 3
        draw.text((cur, sup_y), sup, fill=c_tone, font=self._font_sup, anchor="lm")

    def _draw_char(
        self, draw: ImageDraw.ImageDraw, x: int, center_y: int, ch: str, c_char: tuple,
    ) -> None:
        center_x = x + CELL_WIDTH // 2
        draw.text((center_x, center_y), ch, fill=c_char, font=self._font_char, anchor="mm")

    def validate_input(self, msg: str) -> str | None:
        msg = msg.strip()
        if len(msg) != 4:
            return "请输入 4 个汉字"
        if not all("一" <= c <= "鿿" for c in msg):
            return "请输入 4 个汉字"
        if msg not in self._idioms:
            return "该成语不在词库中"
        return None

    @property
    def answer(self) -> str:
        return self._answer

    @property
    def valid_words(self) -> list[str]:
        return self._valid_words

    @property
    def length(self) -> int:
        return self._length

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    @property
    def guesses(self) -> list[str]:
        return self._guesses

    @property
    def is_game_over(self) -> bool:
        if not self._guesses:
            return False
        return len(self._guesses) >= self._max_attempts or self.is_won

    @property
    def is_won(self) -> bool:
        return bool(self._guesses) and self._guesses[-1] == self._answer

    @property
    def explanation(self) -> str:
        return self._explanation

    @property
    def source(self) -> str:
        return self._source
