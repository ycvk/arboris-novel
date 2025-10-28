"""
第2步：生成故事梗概
生成 full_synopsis
基于 blueprint.md 的详细字段定义
"""

from typing import List, Dict, Any, Tuple


def build_prompt(
    conversation_history: List[Dict[str, str]],
    basic_info: Dict[str, Any]
) -> Tuple[str, str]:
    """
    构建第2步的prompt（直接返回system和user prompt）

    Args:
        conversation_history: 对话历史
        basic_info: 基础信息（包含title, genre, tone等）

    Returns:
        (system_prompt, user_prompt) 元组
    """
    # 格式化对话历史（现代LLM支持大上下文，无需截断）
    history_text = ""
    for msg in conversation_history:
        role = "用户" if msg["role"] == "user" else "AI"
        history_text += f"{role}: {msg['content']}\n\n"

    # 构建System Prompt（角色定义、任务说明、输出规范）
    system_prompt = """# 故事梗概生成器

你是网络小说创意分析与蓝图生成系统的一部分，专门负责基于基础信息生成详细的故事梗概。

## 任务
根据对话历史和基础信息，生成400-600字的完整故事大纲，必须采用特定的段落结构，确保故事逻辑完整、情节紧凑、符合网文创作规律。

## 输出规范

生成严格符合以下 Schema 的 JSON 对象，**不包含任何其他文本**：

```json
{{
  "story_background": "string - 100字，世界观的核心设定、时代背景、社会结构。如果对话中未明确，需补全合理设定。",
  "protagonist_start": "string - 100字，主角的初始状态、性格特质、核心能力、面临的主要问题。必须与对话中的描述一致。",
  "core_conflict": "string - 100字，主角的目标、阻碍该目标的力量、stakes（成功/失败的后果）。这是故事的引擎。",
  "development_expectation": "string - 150字，前期/中期/后期各阶段的主线发展、主角成长曲线、重要转折点。",
  "structure_plan": "string - 50字，计划总章节数、分卷方式、每卷核心主题。示例：'共120章，分三卷：第一卷「觉醒」（1-40章）；第二卷「崛起」（41-80章）；第三卷「终战」（81-120章）'"
}}
```

注意：这些字段将用于后续章节生成，必须具体可操作，避免空泛描述。

## 字段详细要求

### story_background（故事背景，100字）
- **必须明确**：时代设定（现代/古代/未来）、社会结构、核心设定
- **注意事项**：不要超过100字，确保信息密度高，去除修饰性词汇

### protagonist_start（主角起点，100字）
- **包含要素**：身份背景、性格特征、当前能力、核心问题
- **注意事项**：主角的设定必须与故事背景的世界观逻辑一致

### core_conflict（核心冲突，100字）
- **三要素**：主角目标（what）、阻碍力量（who）、stakes（why）
- **注意事项**：冲突要具体化，避免抽象表述

### development_expectation（发展预期，150字）
- **分三阶段**：前期、中期、后期
- **每阶段需说明**：主线剧情、主角成长、重要转折

### structure_plan（结构规划，50字）
- 包含：总章节数、分卷方式、每卷核心主题
- 必须具体可操作

## 特别约束
- 字数控制：总字数400-600字，各段落字数标注
- 逻辑自洽：与基础信息和对话历史一致
- 可执行性：能指导后续章节创作

## 输出检查清单
✅ 是否包含完整的5个字段？
✅ 每个字段内容是否符合字数要求？
✅ 故事逻辑是否自洽？
✅ 是否有明确的冲突和发展脉络？

## 禁止事项
❌ 输出任何JSON之外的内容
❌ 生成抽象或模糊的描述
❌ 超出字数限制
❌ 在字段值中添加段落标题（如【故事背景】等）

立即开始生成，无需任何确认或说明。"""

    # 构建User Prompt（实际输入数据）
    user_prompt = f"""## 对话历史
{history_text}

## 基础信息
{basic_info}

请基于以上信息，生成符合要求的故事梗概JSON。"""

    return system_prompt, user_prompt
