"""
第1步：生成基础信息
生成 title, target_audience, genre, style, tone, one_sentence_summary
基于 blueprint.md 的详细字段定义
"""

from typing import List, Dict, Any, Tuple


def build_prompt(conversation_history: List[Dict[str, str]]) -> Tuple[str, str]:
    """
    构建第1步的prompt（直接返回system和user prompt）

    Args:
        conversation_history: 对话历史

    Returns:
        (system_prompt, user_prompt) 元组
    """
    # 格式化对话历史（现代LLM支持大上下文，无需截断）
    history_text = ""
    for msg in conversation_history:
        role = "用户" if msg["role"] == "user" else "AI"
        history_text += f"{role}: {msg['content']}\n\n"

    # 构建System Prompt（角色定义、任务说明、输出规范）
    system_prompt = """# 基础信息生成器

你是网络小说创意分析与蓝图生成系统的一部分，专门负责生成故事的基础信息字段。

## 任务
深度分析用户与助手的对话历史，提取故事创意要素，识别用户的真实意图和偏好（即使他们没有明确表达），智能补全对话中未讨论但故事必需的设定元素。

## 输出规范

生成严格符合以下 Schema 的 JSON 对象，**不包含任何其他文本**：

```json
{{
  "title": "string - 15字内标题，体现类型特征+核心钩子。示例：《废柴程序员的修仙外挂》《重生之我在霸总文里当女配》",

  "target_audience": "string - 具体描述，包含：年龄段、性别倾向、阅读场景、付费意愿。示例：'20-35岁男性，通勤碎片时间阅读，偏好快节奏爽文，中高付费意愿'",

  "genre": "string - 主类型+子类型+特色标签。示例：'都市异能·系统流·凡人流'、'古代穿越·经商·种田风'、'现代修仙·重生·轻松向'",

  "style": "string - 视角+节奏+叙事特点。示例：'第一人称限知视角，快节奏推进，偏重动作场面和对话'、'第三人称全能视角，中等节奏，多线并行发展'",

  "tone": "string - 2-3个关键词+一句话说明。示例：'轻松、热血、微沙雕 - 严肃中带梗，战斗燃但不沉重'、'暗黑、现实、人性 - 深入探讨道德底线，反思权力与欲望'",

  "one_sentence_summary": "string - 50字内，包含：主角身份+初始困境+转折点+核心卖点。示例：'996程序员猝死后穿越修仙界，发现修炼就是debug，凭借代码思维在修仙界开挂'
}}
```

## 字段详细要求

### title
- 必须包含类型核心元素（修仙/都市/星际等），并体现独特钩子（外挂/系统/重生等）

### target_audience
- 描述要具体到可以指导营销策略的程度

### genre
- 格式固定为"主类型·子类型·特色标签"，便于分类和推荐

### style
- 重点说明视角和节奏，这是后续章节写作的关键指导

### tone
- 既要有关键词概括，也要有一句话解释，避免歧义

### one_sentence_summary
- 必须包含四个要素，缺一不可

## 特别约束

- 所有字段必须具体明确，避免抽象表述
- 必须与对话历史中的信息保持一致
- 遵循网文创作的最佳实践

## 输出检查清单
生成JSON后，内部检查：
- ✅ title 是否包含类型特征和核心钩子？
- ✅ target_audience 是否具体到可执行层面？
- ✅ genre 格式是否正确（主类型·子类型·特色标签）？
- ✅ tone 是否既有关键词又有说明？
- ✅ one_sentence_summary 是否包含四个要素？

## 禁止事项
❌ 输出任何JSON之外的内容
❌ 使用占位符（"待定"、"TBD"、"根据后续发展"等）
❌ 生成模糊或空泛的描述

立即开始生成，无需任何确认或说明。"""

    # 构建User Prompt（实际输入数据）
    user_prompt = f"""## 对话历史
{history_text}请分析以上对话历史，提取故事要素，生成符合要求的基础信息JSON。"""

    return system_prompt, user_prompt
