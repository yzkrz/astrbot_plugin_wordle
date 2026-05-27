import random
from io import BytesIO
from PIL import Image as ImageW, ImageDraw, ImageFont
from .common import WordleBase
from .dict_manager import DictManager, load_english_words


class WordleClassic(WordleBase):
    DICT_NAME = "english"

    def __init__(self, answer: str, valid_words: list[str]):
        self._answer = answer.upper()
        self._valid_words = valid_words
        self._length = len(answer)
        self._max_attempts = self._length + 1
        self._guesses: list[str] = []
        self._feedbacks: list[list[int]] = []
        self._font = ImageFont.load_default(24)

    @classmethod
    def pick_answer(
        cls, dict_manager: DictManager, length: int
    ) -> tuple[str, list[str]] | None:
        """从启用词库选答案、从 all 词库取合法猜测集合。"""
        all_wl = dict_manager.get_all_wordlist(cls.DICT_NAME)
        active_wl = dict_manager.get_active_wordlist(cls.DICT_NAME)
        if not all_wl or not active_wl:
            return None
        valid_words = load_english_words(all_wl, length)
        if not valid_words:
            return None
        valid_set = set(valid_words)
        if active_wl.name == all_wl.name:
            answer_pool = valid_words
        else:
            answer_pool = [w for w in load_english_words(active_wl, length) if w in valid_set]
        if not answer_pool:
            return None
        return random.choice(answer_pool), valid_words

    async def gen_image(self) -> bytes:
        CELL_COLORS = {
            2: (106, 170, 100),
            1: (201, 180, 88),
            0: (120, 124, 126),
            -1: (211, 214, 218),
        }
        BACKGROUND_COLOR = (255, 255, 255)
        TEXT_COLOR = (255, 255, 255)

        CELL_SIZE = 60
        CELL_MARGIN = 5
        GRID_MARGIN = 5

        cell_stride = CELL_SIZE + CELL_MARGIN
        width = GRID_MARGIN * 2 + cell_stride * self._length - CELL_MARGIN
        height = GRID_MARGIN * 2 + cell_stride * self._max_attempts - CELL_MARGIN

        image = ImageW.new("RGB", (width, height), BACKGROUND_COLOR)
        draw = ImageDraw.Draw(image)

        for row in range(self._max_attempts):
            y = GRID_MARGIN + row * cell_stride

            for col in range(self._length):
                x = GRID_MARGIN + col * cell_stride

                if row < len(self._guesses) and col < len(self._guesses[row]):
                    letter = self._guesses[row][col].upper()
                    feedback_value = self._feedbacks[row][col]
                    cell_color = CELL_COLORS[feedback_value]
                else:
                    letter = ""
                    cell_color = CELL_COLORS[-1]

                draw.rectangle(
                    [x, y, x + CELL_SIZE, y + CELL_SIZE], fill=cell_color, outline=None
                )

                if letter:
                    draw.text(
                        (x + CELL_SIZE / 2, y + CELL_SIZE / 2),
                        letter,
                        fill=TEXT_COLOR,
                        font=self._font,
                        anchor="mm",
                    )

        with BytesIO() as output:
            image.save(output, format="PNG")
            return output.getvalue()

    async def guess(self, word: str) -> bytes:
        word = word.upper()
        self._guesses.append(word)

        feedback = [0] * self._length
        answer_char_counts: dict[str, int] = {}

        for i in range(self._length):
            if word[i] == self._answer[i]:
                feedback[i] = 2
            else:
                answer_char_counts[self._answer[i]] = (
                    answer_char_counts.get(self._answer[i], 0) + 1
                )

        for i in range(self._length):
            if feedback[i] != 2:
                char = word[i]
                if char in answer_char_counts and answer_char_counts[char] > 0:
                    feedback[i] = 1
                    answer_char_counts[char] -= 1

        self._feedbacks.append(feedback)
        result = await self.gen_image()

        return result

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
        return bool(self._guesses) and self._guesses[-1].upper() == self._answer

    def validate_input(self, msg: str) -> str | None:
        if len(msg) != self._length:
            return f"输入单词长度应该为{self._length}"
        if not msg.isalpha():
            return "输入应该是英文"
        if msg.upper() not in self._valid_words:
            return "该单词不在有效词表中，请重新输入"
        return None
