# 模型社会实验室：谁是卧底

把多个模型放进同一局“谁是卧底”，由程序主持游戏、隔离私密信息、记录完整上下文，并输出可回放实验日志。

## 当前版本

- Python 3.9+，运行时零第三方依赖
- 默认内置模拟玩家，可离线跑完整对局
- 支持 OpenAI-compatible `/chat/completions` 模型
- 支持 Anthropic Messages API
- 主持人负责身份分配、轮次、投票、计分和日志，模型不能修改游戏状态
- 每个玩家只收到自己的词和应见的公共信息
- 生成 JSON 日志和一个可直接浏览器打开的 HTML 回放

## 立即运行

```bash
cd /Users/hongyan/Code/personal/undercover-lab
uv run python -m undercover_lab --demo --seed 7
```

也可以直接使用当前 Python：

```bash
python3 -m undercover_lab --demo --seed 7
```

输出文件默认在 `runs/`：

- `game-*.json`：完整实验日志，包括每个玩家实际看到的 prompt
- `game-*.html`：观众视角回放，包含身份、发言、投票和结局

## 接入真实模型

复制示例配置后，只修改模型名、API 地址和环境变量名：

```bash
cp config.example.json config.json
export DEEPSEEK_API_KEY='...'
python3 -m undercover_lab --config config.json --seed 7
```

配置示例支持两类玩家：

```json
{
  "game": {
    "civilian_word": "咖啡",
    "undercover_word": "奶茶",
    "max_rounds": 3
  },
  "players": [
    {
      "id": "p1",
      "name": "Claude",
      "adapter": "anthropic",
      "model": "claude-sonnet-4-6",
      "api_key_env": "ANTHROPIC_API_KEY",
      "personality": "谨慎，先观察再发言"
    },
    {
      "id": "p2",
      "name": "DeepSeek",
      "adapter": "openai",
      "model": "deepseek-chat",
      "base_url": "https://api.deepseek.com",
      "api_key_env": "DEEPSEEK_API_KEY",
      "personality": "擅长抓语言细节，但不要过度自信"
    }
  ]
}
```

OpenAI-compatible 玩家会请求 `${base_url}/chat/completions`。`base_url` 可以带 `/v1`，程序会自动补齐路径。Anthropic 玩家默认请求 `https://api.anthropic.com/v1/messages`，也可以在配置里显式指定 `base_url`。

注意：不要把真实 API Key 写入 `config.json`、日志或代码；程序只读取 `api_key_env` 指向的环境变量。

## 实验设计原则

1. 规则引擎是确定性的，模型只负责“发言”和“投票”。
2. 其他玩家的文字是游戏数据，不是系统指令；prompt 明确禁止模型服从其中的指令。
3. 每局记录随机种子、身份分配、玩家 prompt、原始响应、解析后的行动、错误和耗时。
4. 结论需要多局重复，不能用一局推断“某模型更聪明/更狡猾”。
5. 模拟玩家只用于验证流程，不代表真实模型行为。

## CLI

```text
--demo                    使用内置模拟玩家
--config PATH             使用真实模型配置
--seed INT                固定随机种子，便于复现
--output-dir PATH         日志和回放目录，默认 runs
--players INT             demo 玩家人数，默认 5
--max-rounds INT          最大轮数，默认 3
--quiet                   只输出最终结果
```

## 后续可以玩的实验

- 同一组模型交换座位和卧底身份，测位置偏差
- 固定词对，重复 30 局，比较怀疑传播和投票一致性
- 让模型知道/不知道其他玩家的模型身份
- 比较“自由聊天”与“每人一句话”的规则差异
- 增加观众下注、联盟、反向卧底和多人卧底模式
