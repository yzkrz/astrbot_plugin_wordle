# astrbot_plugin_wordle

Astrbot Wordle 游戏

命令：
- `wordle start [位数]` - 开始一局游戏，例如 `wordle start 5`
- `wordle octordle` - 开始一局 Octordle（同时进行 8 局 Wordle）游戏
- `wordle handle` - 开始一局汉兜（中文成语 Wordle）游戏
- `wordle stop` - 终止游戏
- `wordle rank` - 查看排行榜
- `wordle dict` - 列出所有词典
- `wordle dict <name>` - 列出某词典下的所有词库
- `wordle dict <name> set <wordlist>` - 切换某词典的启用词库

## 词典与词库

词典数据放在 `data/<dict>/<wordlist>/` 下，每一层都需要一个 `meta.json` 描述显示名：

```
data/
  english/
    meta.json           # {"display_name": "英文单词"}
    all/                # 必须存在的全量词库
      meta.json
      *_letters_words.txt
    gaokao/             # 可选的子词库
      meta.json         # {"display_name": "高考3500词"}
      gaokao.txt
  chengyu/
    meta.json           # {"display_name": "四字成语"}
    all/
      meta.json
      chengyu.json
```

每种游戏绑定一个词典：经典 Wordle / Octordle 使用 `english`，汉兜使用 `chengyu`。
出题只在启用词库中抽取，但合法猜测集合始终来自 `all` 词库，因此玩家可猜任何在 `all` 中的词。

启用词库通过 `wordle dict <name> set <wordlist>` 切换，结果持久化在 `dict_config.json`。
